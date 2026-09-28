"""
组织上下文管理模块

使用 ContextVar 管理当前请求的组织上下文，实现多组织数据隔离。

三态语义（spec 143「租户查询强制隔离」）：

- 租户 id（``set_current_tenant_id`` 注入或 ``with_tenant(tid)`` scope）：
  租户模型查询自动附加 ``tenant_id=<ctx>``。
- 显式 scope：``with_tenant(tid)`` 视同以指定组织身份执行（仍被过滤到该组织）；
  ``unscoped(reason=...)`` 全放行（跨组织旁路，激活时写结构化日志；
  若发生在请求态且有已认证操作者，额外写 ``core_operation_logs`` 审计记录）。
- 无上下文且不在 scope 内：查询租户模型即失败关闭（``TenantContextError``），
  不返回空集、不静默放行。

scope 使用嵌套安全的 ContextVar 栈实现：内层 scope 优先于外层 scope 与请求级
ambient 上下文；``unscoped`` 只影响查询机制的过滤注入，不改变
``get_current_tenant_id()`` 返回的操作者身份（避免 unscoped 内写入的数据丢失
tenant_id 归属）。
"""

import asyncio
from contextvars import ContextVar
from typing import Optional, Tuple

from loguru import logger

# 组织上下文变量（使用 ContextVar 实现线程/协程级别的上下文隔离）
_tenant_context: ContextVar[Optional[int]] = ContextVar("tenant_context", default=None)

# 显式 scope 栈（嵌套安全）：元素为 (kind, payload)
#   kind == "tenant"   → payload 为组织 id（with_tenant）
#   kind == "unscoped" → payload 为 (reason, )，表示放行旁路
# 内层（栈尾）优先；栈非空时优先于 ambient _tenant_context 参与「查询过滤」判定。
_scope_stack: ContextVar[Tuple[tuple, ...]] = ContextVar("tenant_scope_stack", default=())

# 请求态操作者（kind, actor_id, actor_tenant_id），由认证依赖设置。
# 仅用于「请求态用户显式跨组织」的审计落点；不用于过滤判定。
_request_actor: ContextVar[Optional[tuple]] = ContextVar("tenant_request_actor", default=None)

_SCOPE_TENANT = "tenant"
_SCOPE_UNSCOPED = "unscoped"


class _UnscopedSentinel:
    """查询过滤态哨兵：表示显式 unscoped 放行。"""

    def __repr__(self) -> str:  # pragma: no cover - 调试可读性
        return "UNSCOPED"


UNSCOPED = _UnscopedSentinel()


class TenantContextError(RuntimeError):
    """
    无组织上下文访问租户模型（失败关闭）。

    触发条件：对「有 tenant_id 字段且未声明 Meta.tenant_isolation="platform"」的
    模型执行查询/更新/删除时，既无 ambient 组织上下文，也不在任何显式 scope 内。
    """


def get_current_tenant_id() -> Optional[int]:
    """
    获取当前请求的组织 ID

    从上下文变量中获取当前请求关联的组织 ID。
    如果未设置，则返回 None。

    注意（spec 143）：``with_tenant(tid)`` scope 内返回该 scope 的组织 id
    （视同以该组织身份执行）；``unscoped`` scope 不影响本函数返回值——
    unscoped 只放开查询过滤，不抹去操作者身份，避免 scope 内写入丢失归属。

    Returns:
        Optional[int]: 当前组织 ID，如果未设置则返回 None

    Example:
        >>> tenant_id = get_current_tenant_id()
        >>> if tenant_id:
        ...     users = await User.filter(tenant_id=tenant_id).all()
    """
    for kind, payload in reversed(_scope_stack.get()):
        if kind == _SCOPE_TENANT:
            return payload
    return _tenant_context.get()


def set_current_tenant_id(tenant_id: Optional[int]) -> None:
    """
    设置当前请求的组织 ID

    将组织 ID 设置到上下文变量中，用于后续的数据库查询自动过滤。

    Args:
        tenant_id: 组织 ID，如果为 None 则清除当前组织上下文

    Example:
        >>> set_current_tenant_id(1)
        >>> tenant_id = get_current_tenant_id()  # 返回 1
    """
    _tenant_context.set(tenant_id)


def clear_tenant_context() -> None:
    """
    清除当前组织上下文

    将组织上下文设置为 None，用于清理上下文状态。
    """
    _tenant_context.set(None)


async def require_tenant_context() -> int:
    """
    要求必须有组织上下文

    获取当前组织 ID，如果未设置则抛出异常。
    用于需要组织上下文的场景（如业务数据查询）。

    Returns:
        int: 当前组织 ID

    Raises:
        ValueError: 当组织上下文未设置时抛出

    Example:
        >>> try:
        ...     tenant_id = await require_tenant_context()
        ...     users = await User.filter(tenant_id=tenant_id).all()
        ... except ValueError:
        ...     # 处理未设置组织上下文的情况
    """
    tenant_id = get_current_tenant_id()
    if tenant_id is None:
        raise ValueError("组织上下文未设置，无法执行需要组织隔离的操作")
    return tenant_id


def resolve_tenant_for_query():
    """
    解析「查询过滤」生效的组织态（供强制隔离 QuerySet 使用）。

    Returns:
        int: 注入 ``tenant_id=<该值>``
        UNSCOPED: 不注入（显式 unscoped scope）
        None: 无上下文 —— 调用方应失败关闭（raise TenantContextError）
    """
    for kind, payload in reversed(_scope_stack.get()):
        if kind == _SCOPE_UNSCOPED:
            return UNSCOPED
        return payload  # kind == _SCOPE_TENANT
    return _tenant_context.get()


def set_request_actor(kind: str, actor_id: Optional[int], tenant_id: Optional[int]) -> None:
    """
    记录请求态操作者（认证依赖调用，供跨组织审计判定）。

    Args:
        kind: 操作者类型（"user" / "infra_superadmin" / "open_api"）
        actor_id: 操作者 ID（平台超管为 admin id）
        tenant_id: 操作者所属组织 ID（平台超管为 0 哨兵或 None）
    """
    _request_actor.set((kind, actor_id, tenant_id))


def get_request_actor() -> Optional[tuple]:
    """返回 (kind, actor_id, tenant_id) 或 None。"""
    return _request_actor.get()


def clear_request_actor() -> None:
    _request_actor.set(None)


async def _write_scope_audit_row(actor: tuple, kind: str, reason: str, target_tenant_id: Optional[int]) -> None:
    """
    「请求态用户显式跨组织」审计：复用 core_operation_logs 专用 operation_type。

    注意：OperationLogMiddleware 只记非 GET 请求，跨组织读的审计只能落在
    scope 激活点。失败不阻断业务（降级为结构化日志）。
    """
    actor_kind, actor_id, actor_tenant_id = actor
    try:
        from core.models.operation_log import OperationLog

        await OperationLog.create(
            tenant_id=actor_tenant_id or 0,
            user_id=actor_id or 0,
            operation_type="tenant_scope_bypass",
            operation_module="tenant_isolation",
            operation_object_type="tenant_scope",
            operation_object_id=target_tenant_id,
            operation_content=(
                f"scope={kind}; reason={reason}; "
                f"actor_kind={actor_kind}; actor_tenant_id={actor_tenant_id}"
            ),
        )
    except Exception as e:  # noqa: BLE001 - 审计写库失败不得阻断 scope
        logger.warning("租户 scope 审计写入失败（已降级为结构化日志）: {}", e)


def _emit_scope_audit(kind: str, reason: str, target_tenant_id: Optional[int]) -> None:
    """
    scope 激活点统一审计：

    - 始终写 loguru 结构化日志（unscoped 为安全事件级别 warning）。
    - 请求态操作者存在且确属跨组织可见（unscoped，或 with_tenant 目标组织
      与操作者组织不同）时，异步写 core_operation_logs 专用记录。
    """
    actor = _request_actor.get()
    if kind == _SCOPE_UNSCOPED:
        logger.warning(
            "tenant_scope_unscoped reason={} actor={}",
            reason,
            actor,
        )
    else:
        logger.debug(
            "tenant_scope_with_tenant target_tenant_id={} reason={} actor={}",
            target_tenant_id,
            reason,
            actor,
        )

    need_audit_row = False
    if actor is not None:
        actor_tenant_id = actor[2]
        if kind == _SCOPE_UNSCOPED:
            need_audit_row = True
        elif actor_tenant_id != target_tenant_id:
            need_audit_row = True

    if not need_audit_row:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_write_scope_audit_row(actor, kind, reason, target_tenant_id))


class TenantScope:
    """
    显式租户 scope（同步/异步上下文管理器两用）。

    - ``with_tenant(tid)``：以指定组织身份执行，查询仍被过滤到该组织。
    - ``unscoped(reason=...)``：全放行旁路，reason 必填，激活时审计。

    嵌套安全：ContextVar 栈 + token 还原，内层覆盖外层。
    """

    def __init__(self, kind: str, reason: str, target_tenant_id: Optional[int] = None):
        self._entry = (kind, target_tenant_id if kind == _SCOPE_TENANT else (reason,))
        self._reason = reason
        self._target_tenant_id = target_tenant_id
        self._token = None

    def __enter__(self) -> "TenantScope":
        self._token = _scope_stack.set(_scope_stack.get() + (self._entry,))
        _emit_scope_audit(self._entry[0], self._reason, self._target_tenant_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._token is not None:
            _scope_stack.reset(self._token)
            self._token = None
        return False

    async def __aenter__(self) -> "TenantScope":
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        return self.__exit__(exc_type, exc_val, exc_tb)


def with_tenant(tenant_id: int, *, reason: str = "") -> TenantScope:
    """
    以指定组织身份执行（查询仍被过滤到该组织）。

    Args:
        tenant_id: 目标组织 ID
        reason: 可选说明（跨组织激活时记入审计内容）

    Example:
        >>> async with with_tenant(3, reason="定时任务按事件组织执行"):
        ...     rows = await Order.all()   # 仅返回 tenant_id=3 的行
    """
    return TenantScope(_SCOPE_TENANT, reason or "with_tenant", int(tenant_id))


def unscoped(*, reason: str) -> TenantScope:
    """
    放开租户过滤的显式旁路（跨组织）。

    Args:
        reason: 必填；写结构化日志与（请求态）core_operation_logs 审计记录。

    Example:
        >>> async with unscoped(reason="登录前按账号跨组织解析候选用户"):
        ...     users = await User.filter(...).all()
    """
    if not reason or not str(reason).strip():
        raise ValueError("unscoped 必须提供 reason")
    return TenantScope(_SCOPE_UNSCOPED, str(reason).strip())
