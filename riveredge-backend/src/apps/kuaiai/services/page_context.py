"""抽屉页上下文短摘要（KR-F4/F6，spec 135 AC7 + spec 204 扩展）。

服务端只信白名单 ``screen`` 映射出的页名，单据侧只信按 ``resource_key`` /
``record_id`` 经既有 service 查到的单号/状态/数量；客户端传来的
``screen_label`` / ``record_label`` **永远不进返回值**。未知 screen /
resource、无对应业务读权限、查询异常一律返回 ``None``（省略摘要，不 500）。
全宽 ``/apps/kuaiai/chat`` 不传这套页上下文，由上游决定是否拼接。

spec 204：每个 reader 在取数前先复核**行级数据范围**——客户端可伪造任意
``record_id``，仅校验功能权限不足以防越权读摘要。service 自带
``current_user`` 行级校验的（销售订单详情）沿 service 路径；不接收
``current_user`` 的在此经 ``scene_tools._scoped_row_ids`` 套
DataScopeService 收口，范围外按“不存在”处理（返回 ``None``，不泄露存在性）。
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext
from core.services.authorization.user_permission_service import (
    UserPermissionService,
)

# 白名单 screen（前端路由 path）→ 服务端认定的页名。
# 真源：riveredge-frontend useRegisterAiContext 注册的 location.pathname；
# 路径取自 kuaizhizao manifest menu_config（spec 204 T1）。
_SCREEN_PAGE_NAMES = {
    "/apps/kuaizhizao/production-execution/work-orders": "工单管理",
    "/apps/kuaizhizao/production-execution/reporting": "报工管理",
    "/apps/kuaizhizao/production-execution/dashboard": "生产执行看板",
    "/apps/kuaizhizao/sales-management/sales-orders": "销售订单",
    "/apps/kuaizhizao/purchase-management/purchase-orders": "采购订单",
    "/apps/kuaizhizao/production-execution/quality-exceptions": "质量异常",
    "/apps/kuaizhizao/production-execution/material-shortage-exceptions": "缺料异常",
    "/apps/kuaizhizao/warehouse-management/inventory-alert": "库存预警",
}

# 行级数据范围资源键：工单/销售/采购取 manifest reference_resources
# data_scope_key；异常与预警页 manifest 未声明 data_scope_key，用页面功能
# 资源键（DataScopeService 内部「无策略=全部」，未授予该资源的角色 id=-1 拒绝）。
_SCOPE_WORK_ORDER = "kuaizhizao:work-order"
_SCOPE_PURCHASE_ORDER = "kuaizhizao:purchase-order"
_SCOPE_QUALITY_EXCEPTION = "kuaizhizao:production-execution-quality-exceptions"
_SCOPE_MATERIAL_SHORTAGE = (
    "kuaizhizao:production-execution-material-shortage-exceptions"
)
_SCOPE_INVENTORY_ALERT = "kuaizhizao:warehouse-management-inventory-alert"


async def _row_in_scope(
    ctx: AiRuntimeContext, model: Any, resource: str, record_id: Any
) -> bool:
    """单行数据范围复核（复用 ``scene_tools._scoped_row_ids`` 机制）。

    非法 id / 范围外 / 范围解析异常一律失败关闭（按不存在处理）。
    """
    try:
        rid = int(record_id)
    except (TypeError, ValueError):
        return False
    if rid <= 0:
        return False
    try:
        from apps.kuaiai.services.scene_tools import _scoped_row_ids

        return rid in await _scoped_row_ids(model, ctx, resource, {rid})
    except Exception as exc:
        logger.warning(
            "页上下文数据范围解析失败 resource={} error_type={}",
            resource,
            type(exc).__name__,
        )
        return False


async def _work_order_in_scope(ctx: AiRuntimeContext, record_id: Any) -> bool:
    """工单行级范围（与 ``chat_tools._work_order_in_scope`` 同资源键）。"""
    from apps.kuaizhizao.models.work_order import WorkOrder

    return await _row_in_scope(ctx, WorkOrder, _SCOPE_WORK_ORDER, record_id)


async def _work_order_summary(ctx: AiRuntimeContext, record_id: int) -> str | None:
    from apps.kuaiai.services.chat_tools import _fmt_work_order_row
    from apps.kuaizhizao.services.work_order_service import WorkOrderService

    if not await _work_order_in_scope(ctx, record_id):
        return None
    wo = await WorkOrderService().get_work_order_by_id(
        ctx.tenant_id, record_id
    )
    return _fmt_work_order_row(wo)


async def _sales_order_summary(
    ctx: AiRuntimeContext, record_id: int
) -> str | None:
    from apps.kuaiai.services.tools.sales_purchase import _fmt_sales_order_row
    from apps.kuaizhizao.services.sales_order_service import SalesOrderService

    # 既有 service 行级校验唯一路径：get_sales_order_by_id 对 current_user 跑
    # assert_sales_order_row_visible_or_quality_linked；范围外抛 403/404，
    # 由上层按“不存在”省略摘要。
    order = await SalesOrderService().get_sales_order_by_id(
        ctx.tenant_id, record_id, current_user=ctx.user
    )
    # AC4：与 query_sales_orders 行格式化同一函数同一口径
    return _fmt_sales_order_row(order)


async def _purchase_order_summary(
    ctx: AiRuntimeContext, record_id: int
) -> str | None:
    """采购订单摘要：``_row_in_scope`` 复核后经
    ``list_purchase_orders(current_user)`` 取行（service 内已套采购单数据
    范围），格式化复用 ``scene_tools._fmt_purchase_order_row`` 与
    ``query_purchase_followup`` Tool 同口径。"""
    from apps.kuaiai.services.scene_tools import _fmt_purchase_order_row
    from apps.kuaizhizao.models.purchase_order import PurchaseOrder
    from apps.kuaizhizao.schemas.purchase import PurchaseOrderListParams
    from apps.kuaizhizao.services.purchase_service import PurchaseService

    if not await _row_in_scope(
        ctx, PurchaseOrder, _SCOPE_PURCHASE_ORDER, record_id
    ):
        return None
    order = await PurchaseOrder.get_or_none(
        id=record_id, tenant_id=ctx.tenant_id, deleted_at__isnull=True
    )
    if order is None:
        return None
    result = await PurchaseService().list_purchase_orders(
        ctx.tenant_id,
        PurchaseOrderListParams(
            order_code=getattr(order, "order_code", "") or None, limit=20
        ),
        current_user=ctx.user,
    )
    row = next(
        (
            r
            for r in (result or {}).get("data") or []
            if int(getattr(r, "id", 0) or 0) == record_id
        ),
        None,
    )
    if row is None:
        return None
    return _fmt_purchase_order_row(row)


async def _quality_exception_summary(
    ctx: AiRuntimeContext, record_id: int
) -> str | None:
    """质量异常摘要：异常自身资源范围 + 关联工单范围求交（spec 197 口径）。

    AC4：行格式化复用 ``tools.kitting_exceptions._fmt_quality_exception_row``，
    与 ``query_quality_exceptions`` Tool 同口径。"""
    from apps.kuaiai.services.tools.kitting_exceptions import (
        _fmt_quality_exception_row,
    )
    from apps.kuaizhizao.models.quality_exception import QualityException
    from apps.kuaizhizao.services.exception_service import ExceptionService

    if not await _row_in_scope(
        ctx, QualityException, _SCOPE_QUALITY_EXCEPTION, record_id
    ):
        return None
    exc = await ExceptionService().get_quality_exception(
        ctx.tenant_id, record_id
    )
    work_order_id = getattr(exc, "work_order_id", None)
    if work_order_id and not await _work_order_in_scope(ctx, work_order_id):
        return None
    return _fmt_quality_exception_row(exc)


async def _material_shortage_summary(
    ctx: AiRuntimeContext, record_id: int
) -> str | None:
    """缺料异常摘要：异常自身资源范围 + 关联工单范围求交（spec 197 口径）。

    AC4：行格式化复用 ``tools.kitting_exceptions._fmt_material_shortage_row``，
    与 ``query_material_shortages`` Tool 同口径。"""
    from apps.kuaiai.services.tools.kitting_exceptions import (
        _fmt_material_shortage_row,
    )
    from apps.kuaizhizao.models.material_shortage_exception import (
        MaterialShortageException,
    )
    from apps.kuaizhizao.services.exception_service import ExceptionService

    if not await _row_in_scope(
        ctx, MaterialShortageException, _SCOPE_MATERIAL_SHORTAGE, record_id
    ):
        return None
    exc = await ExceptionService().get_material_shortage_exception(
        ctx.tenant_id, record_id
    )
    # work_order_id 为必填字段；缺关联或工单越界一律按不存在处理
    work_order_id = getattr(exc, "work_order_id", None)
    if not work_order_id or not await _work_order_in_scope(
        ctx, work_order_id
    ):
        return None
    return _fmt_material_shortage_row(exc)


async def _inventory_alert_summary(
    ctx: AiRuntimeContext, record_id: int
) -> str | None:
    """库存预警摘要：预警自身资源范围 + 库存资源 (material, warehouse) 可见对求交
    （与 ``scene_tools.query_inventory_balance`` 的 ``_inventory_visible_pairs``
    同口径）。

    AC4：行格式化复用 ``tools.inventory_alerts._fmt_inventory_alert_row``，
    与 ``query_inventory_alerts`` Tool 同口径。"""
    from apps.kuaiai.services.scene_tools import _inventory_visible_pairs
    from apps.kuaiai.services.tools.inventory_alerts import (
        _fmt_inventory_alert_row,
    )
    from apps.kuaizhizao.models.inventory_alert import InventoryAlert
    from apps.kuaizhizao.services.inventory_alert_service import (
        InventoryAlertService,
    )

    if not await _row_in_scope(
        ctx, InventoryAlert, _SCOPE_INVENTORY_ALERT, record_id
    ):
        return None
    alert = await InventoryAlertService().get_alert_by_id(
        ctx.tenant_id, record_id
    )
    pair = (
        getattr(alert, "material_id", None),
        getattr(alert, "warehouse_id", None),
    )
    # 只反查该预警行的可见对，不全量扫两类存量源
    visible_pairs = await _inventory_visible_pairs(ctx, {pair})
    if pair not in visible_pairs:
        return None
    return _fmt_inventory_alert_row(alert)


# 白名单 resource_key → (读权限码, 摘要函数)
# 摘要函数签名：``(ctx: AiRuntimeContext, record_id: int) -> str | None``；
# 返回 None / 抛异常一律省略摘要（范围外按不存在处理）。
_RESOURCE_READERS: dict[
    str, tuple[str, Callable[[AiRuntimeContext, int], Awaitable[Optional[str]]]]
] = {
    "kuaizhizao:work_order": (
        "kuaizhizao:work-order:read",
        _work_order_summary,
    ),
    "kuaizhizao:sales_order": (
        "kuaizhizao:sales-order:read",
        _sales_order_summary,
    ),
    "kuaizhizao:purchase_order": (
        "kuaizhizao:purchase-order:read",
        _purchase_order_summary,
    ),
    "kuaizhizao:quality_exception": (
        "kuaizhizao:production-execution-quality-exceptions:read",
        _quality_exception_summary,
    ),
    "kuaizhizao:material_shortage": (
        "kuaizhizao:production-execution-material-shortage-exceptions:read",
        _material_shortage_summary,
    ),
    "kuaizhizao:inventory_alert": (
        "kuaizhizao:warehouse-management-inventory-alert:read",
        _inventory_alert_summary,
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
        if record_id <= 0:
            return None
        if not await _has_read_permission(user, tenant_id, permission):
            return None  # 无对应业务读权限不拼单据摘要
        ctx = AiRuntimeContext(
            tenant_id=tenant_id,
            user=user,
            is_infra_admin=bool(getattr(user, "is_infra_admin", False)),
            is_tenant_admin=bool(getattr(user, "is_tenant_admin", False)),
        )
        try:
            record_summary = await fetch(ctx, record_id)
        except Exception as exc:
            logger.warning(
                "页上下文单据摘要查询失败 resource={} error_type={}",
                resource_key,
                type(exc).__name__,
            )
            return None
        if not record_summary:
            # 行级范围外 / 不存在：省略整个摘要，不泄露存在性
            return None

    if page_name and record_summary:
        return f"用户当前位于「{page_name}」页面，正在查看{record_summary}。"
    if page_name:
        return f"用户当前位于「{page_name}」页面。"
    return record_summary
