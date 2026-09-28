"""
工作流函数租户隔离装饰器。

spec 143：装饰器改用 ``with_tenant(tid)`` 显式 scope（ContextVar 栈，
嵌套安全、退出时还原先前态），替代原先 set/clear ambient 的写法——
旧写法在嵌套调用或外层已有 ambient 上下文时会破坏外层状态。
"""

from functools import wraps
from typing import Any, Callable

from core.tasks.event_compat import Event
from infra.domain.tenant_context import with_tenant
from infra.models.tenant import Tenant
from loguru import logger


def _extract_event(args: tuple, kwargs: dict):
    ctx = (args[0] if args else None) or kwargs.get("ctx")
    event = getattr(ctx, "event", None) if ctx is not None else None
    if not event:
        event = kwargs.get("event")
    return event


def _extract_tenant_id(func_name: str, event) -> tuple[int | None, dict | None]:
    data = event.data or {}
    tenant_id = data.get("tenant_id")
    if not tenant_id:
        logger.error(f"工作流函数 {func_name} 缺少 tenant_id")
        return None, {"success": False, "error": "缺少必要参数：tenant_id"}
    if not isinstance(tenant_id, int):
        try:
            tenant_id = int(tenant_id)
        except (ValueError, TypeError):
            logger.error(f"工作流函数 {func_name} tenant_id 类型错误: {tenant_id}")
            return None, {"success": False, "error": f"tenant_id 类型错误: {tenant_id}"}
    return tenant_id, None


async def _validate_tenant(func_name: str, tenant_id: int) -> dict | None:
    try:
        tenant = await Tenant.get_or_none(id=tenant_id)
        if not tenant:
            logger.error(f"工作流函数 {func_name} 租户不存在: {tenant_id}")
            return {"success": False, "error": f"租户不存在: {tenant_id}"}
        if hasattr(tenant, "is_active") and not tenant.is_active:
            logger.warning(f"工作流函数 {func_name} 租户已禁用: {tenant_id}")
            return {"success": False, "error": f"租户已禁用: {tenant_id}"}
    except Exception as e:
        logger.error(f"工作流函数 {func_name} 验证租户失败: {e}")
        return {"success": False, "error": f"验证租户失败: {str(e)}"}
    return None


def with_tenant_isolation(func: Callable) -> Callable:
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        event = _extract_event(args, kwargs)
        if not event:
            logger.error(f"工作流函数 {func.__name__} 缺少 event 参数")
            return {"success": False, "error": "缺少必要参数：event"}

        tenant_id, error = _extract_tenant_id(func.__name__, event)
        if error is not None:
            return error

        error = await _validate_tenant(func.__name__, tenant_id)
        if error is not None:
            return error

        try:
            filtered_kwargs = {k: v for k, v in kwargs.items() if k not in ("ctx", "step")}
            async with with_tenant(
                tenant_id, reason=f"工作流函数 {func.__name__} 按事件组织执行"
            ):
                return await func(event, **filtered_kwargs)
        except Exception as e:
            logger.error(f"工作流函数 {func.__name__} 执行失败: [租户 {tenant_id}] {e}")
            return {"success": False, "error": str(e)}

    return wrapper


def with_tenant_isolation_optional(func: Callable) -> Callable:
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        event = _extract_event(args, kwargs)
        if not event:
            logger.error(f"工作流函数 {func.__name__} 缺少 event 参数")
            return {"success": False, "error": "缺少必要参数：event"}

        data = event.data or {}
        tenant_id = data.get("tenant_id")
        scope = None
        if tenant_id is not None:
            if not isinstance(tenant_id, int):
                try:
                    tenant_id = int(tenant_id)
                except (ValueError, TypeError):
                    logger.error(f"工作流函数 {func.__name__} tenant_id 类型错误: {tenant_id}")
                    return {"success": False, "error": f"tenant_id 类型错误: {tenant_id}"}
            error = await _validate_tenant(func.__name__, tenant_id)
            if error is not None:
                return error
            scope = with_tenant(
                tenant_id, reason=f"工作流函数 {func.__name__} 按事件组织执行"
            )

        # spec 143：无 tenant_id 时不伪造上下文——函数内若访问租户模型
        # 将按三态规则失败关闭（或函数自行声明 unscoped）。
        try:
            filtered_kwargs = {k: v for k, v in kwargs.items() if k not in ("ctx", "step")}
            if scope is not None:
                async with scope:
                    return await func(event, **filtered_kwargs)
            return await func(event, **filtered_kwargs)
        except Exception as e:
            logger.error(f"工作流函数 {func.__name__} 执行失败: [租户 {tenant_id}] {e}")
            return {"success": False, "error": str(e)}

    return wrapper


__all__ = ["with_tenant_isolation", "with_tenant_isolation_optional", "Event"]
