"""库存过账的事务去重，以及单据确认/撤回的串行边界。"""
import hashlib
import inspect
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import wraps
from uuid import uuid4

from loguru import logger

from tortoise.transactions import in_transaction
from tortoise import connections
from tortoise.backends.base.client import BaseTransactionWrapper
from tortoise.queryset import Q

_posting_scope: ContextVar[str | None] = ContextVar("stock_posting_scope", default=None)


@asynccontextmanager
async def reuse_or_begin_transaction():
    """
    复用外层事务，否则开启新事务。

    Tortoise 0.21 嵌套 in_transaction 走 NestedTransactionPooledContext：
    - `_trxlock` 不可重入，嵌套调用会死锁；
    - 内层主动 rollback 会连带回滚外层未提交写入（P2-18）。
    因此复用分支只 yield，异常交由外层事务处理；独立新建分支仍用 in_transaction。
    """
    conn = connections.get("default")
    if isinstance(conn, BaseTransactionWrapper):
        yield conn
    else:
        async with in_transaction() as conn:
            yield conn


# 兼容旧名：库存原子装饰器内部仍用此别名
_stock_transaction = reuse_or_begin_transaction


def atomic_stock_change(func):
    @wraps(func)
    async def wrapped(*args, **kwargs):
        async with reuse_or_begin_transaction():
            return await func(*args, **kwargs)
    return wrapped


async def _lock(conn, key: str) -> None:
    lock_id = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big", signed=True)
    await conn.execute_query("SELECT pg_advisory_xact_lock($1)", [lock_id])


def idempotent_stock_change(func):
    """先锁定幂等操作，再查流水；余额和全部拆批流水与此检查同事务提交。

    spec 141（KR-CL2）：幂等键失败关闭——空/缺 `idempotency_key` 直接拒绝，
    禁止无键静默直跑（无键路径重试会双过账）。
    """
    signature = inspect.signature(func)

    @wraps(func)
    async def wrapped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        key = bound.arguments.get("idempotency_key")
        if not key or not str(key).strip():
            from infra.exceptions.exceptions import ValidationError

            raise ValidationError(
                f"库存过账缺少幂等键 idempotency_key: {getattr(func, '__name__', func)}"
            )
        bound.arguments["idempotency_key"] = str(key).strip()
        key = bound.arguments["idempotency_key"]
        tenant_id = bound.arguments["tenant_id"]
        scope = _posting_scope.get()
        if scope:
            # 确认→撤回→再次确认是新过账，不能沿用历史单据明细键。
            key = f"{key}@{scope}"
            bound.arguments["idempotency_key"] = key
        from apps.kuaizhizao.models.material_stock_movement import MaterialStockMovement

        async with reuse_or_begin_transaction() as conn:
            await _lock(conn, f"stock-posting:{tenant_id}:{key}")
            # 预检：精确键或任意分片（#p{n}/#neg{n}）。
            # P2-21：分片与主过账同处 advisory lock + 同一事务，部分成功窗口仅理论上存在于
            # 历史异常数据；命中任一分片即视为整键已完成，避免重试双计。运营侧用补偿工具修残留。
            existing = await MaterialStockMovement.filter(
                Q(tenant_id=tenant_id)
                & (Q(idempotency_key=key) | Q(idempotency_key__startswith=f"{key}#")),
            ).using_db(conn).values_list("idempotency_key", flat=True)
            if existing:
                # 幂等命中须可观测：返回既有结果，不重复过账（便于对账）
                logger.info(
                    "stock posting idempotent hit: tenant={} key={} existing={}",
                    tenant_id,
                    key,
                    list(existing),
                )
                return True
            return await func(*bound.args, **bound.kwargs)

    return wrapped


def serialize_stock_document(document_type: str, id_parameter: str):
    """同一单据的确认和撤回互斥；锁内重新读取并校验状态。

    IDEM-03：新建路径若随后立刻确认，应在拿到单据 id 后尽早进入本装饰器
    （或与确认同事务），避免「新建未落定 + 并发确认」竞态。
    """
    def decorate(func):
        signature = inspect.signature(func)

        @wraps(func)
        async def wrapped(*args, **kwargs):
            values = signature.bind(*args, **kwargs).arguments
            async with reuse_or_begin_transaction() as conn:
                await _lock(conn, f"stock-document:{document_type}:{values['tenant_id']}:{values[id_parameter]}")
                token = _posting_scope.set(uuid4().hex)
                try:
                    return await func(*args, **kwargs)
                finally:
                    _posting_scope.reset(token)
        return wrapped
    return decorate


@asynccontextmanager
async def stock_document_guard(document_type: str, tenant_id: int, document_id):
    """单据级串行边界 + 单次过账尝试隔离，供不能把整函数包进过账事务的路径使用。

    与 `serialize_stock_document` 同语义但不接管事务边界——必须在已开启的
    事务内作为第二个上下文使用：

        async with in_transaction(), stock_document_guard("sales_return", tenant_id, return_id):
            ...

    - 咨询锁与装饰器同名 `stock-document:{type}:{tenant}:{id}`，同一单据的
      确认/撤回互斥；随当前事务提交/回滚释放（含复用外层事务的调用）。
    - `_posting_scope` 每次进入生成新 UUID，保证「确认→撤回→再确认」是新过账
      尝试，明细幂等键带新后缀、不被流水查重吞掉。
    """
    conn = connections.get("default")
    if not isinstance(conn, BaseTransactionWrapper):
        # 失败关闭：锁落在非事务连接上随语句结束即释放，等同失去单据互斥
        from infra.exceptions.exceptions import ValidationError

        raise ValidationError(
            f"stock_document_guard 必须在活动事务内使用: {document_type}:{document_id}"
        )
    await _lock(conn, f"stock-document:{document_type}:{tenant_id}:{document_id}")
    token = _posting_scope.set(uuid4().hex)
    try:
        yield
    finally:
        _posting_scope.reset(token)


def serialize_stock_create(document_type: str):
    """新建→确认短窗口串行：按租户+单据类型加锁（无 id 前的创建路径）。"""
    def decorate(func):
        signature = inspect.signature(func)

        @wraps(func)
        async def wrapped(*args, **kwargs):
            values = signature.bind(*args, **kwargs).arguments
            tenant_id = values["tenant_id"]
            async with reuse_or_begin_transaction() as conn:
                await _lock(conn, f"stock-document-create:{document_type}:{tenant_id}")
                token = _posting_scope.set(uuid4().hex)
                try:
                    return await func(*args, **kwargs)
                finally:
                    _posting_scope.reset(token)
        return wrapped
    return decorate
