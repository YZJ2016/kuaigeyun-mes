"""抽屉页上下文短摘要（KR-F4/F6，spec 135 AC7）。

服务端只信白名单 ``screen`` 映射出的页名，单据侧只信按 ``resource_key`` /
``record_id`` 经既有 service 查到的单号/状态/数量；客户端传来的
``screen_label`` / ``record_label`` **永远不进返回值**。未知 screen /
resource、无对应业务读权限、查询异常一律返回 ``None``（省略摘要，不 500）。
全宽 ``/apps/kuaiai/chat`` 不传这套页上下文，由上游决定是否拼接。
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from loguru import logger

from core.services.authorization.user_permission_service import (
    UserPermissionService,
)

# 白名单 screen（前端路由 path）→ 服务端认定的页名。
# 真源：riveredge-frontend useRegisterAiContext 注册的 location.pathname。
_SCREEN_PAGE_NAMES = {
    "/apps/kuaizhizao/production-execution/work-orders": "工单管理",
    "/apps/kuaizhizao/production-execution/reporting": "报工管理",
    "/apps/kuaizhizao/production-execution/dashboard": "生产执行看板",
}


async def _work_order_summary(tenant_id: int, record_id: int) -> str:
    from apps.kuaizhizao.services.work_order_service import WorkOrderService

    wo = await WorkOrderService().get_work_order_by_id(tenant_id, record_id)
    return (
        f"工单 {wo.code}"
        f"（{wo.name or '未命名'}）：产品 {wo.product_name}，"
        f"状态 {wo.status}，计划 {wo.quantity}，"
        f"已完成 {wo.completed_quantity}"
    )


# 白名单 resource_key → (读权限码, 摘要函数)
_RESOURCE_READERS: dict[str, tuple[str, Callable[[int, int], Awaitable[str]]]] = {
    "kuaizhizao:work_order": (
        "kuaizhizao:work-order:read",
        _work_order_summary,
    ),
}


async def _has_read_permission(
    user: Any, tenant_id: int, permission: str
) -> bool:
    if getattr(user, "is_infra_admin", False) or getattr(
        user, "is_tenant_admin", False
    ):
        return True
    user_id = getattr(user, "id", None)
    if user_id is None:
        return False
    return bool(
        await UserPermissionService.has_permission(user_id, tenant_id, permission)
    )


async def build_page_context_summary(
    context: dict | None,
    *,
    tenant_id: int,
    user: Any,
) -> str | None:
    """抽屉页上下文 → 一两句中文短摘要；不可解析/无权限/异常 → ``None``。"""
    if not isinstance(context, dict) or not context:
        return None
    if not tenant_id or getattr(user, "id", None) is None:
        return None

    screen = str(context.get("screen") or "").strip()
    page_name: Optional[str] = None
    if screen:
        page_name = _SCREEN_PAGE_NAMES.get(screen)
        if page_name is None:
            # 未知 screen 当无页上下文处理（KR-F4：不认客户端 label）
            return None

    resource_key = str(context.get("resource_key") or "").strip()
    record_summary: Optional[str] = None
    if resource_key:
        reader = _RESOURCE_READERS.get(resource_key)
        if reader is None:
            return None  # 未知 resource 省略摘要
        permission, fetch = reader
        raw_id = context.get("record_id")
        try:
            record_id = int(raw_id)
        except (TypeError, ValueError):
            return None
        if not await _has_read_permission(user, tenant_id, permission):
            return None  # 无对应业务读权限不拼单据摘要
        try:
            record_summary = await fetch(tenant_id, record_id)
        except Exception as exc:
            logger.warning(
                "页上下文单据摘要查询失败 resource={} error_type={}",
                resource_key,
                type(exc).__name__,
            )
            return None

    if page_name and record_summary:
        return f"用户当前位于「{page_name}」页面，正在查看{record_summary}。"
    if page_name:
        return f"用户当前位于「{page_name}」页面。"
    return record_summary
