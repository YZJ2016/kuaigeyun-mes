"""KU-AI 场景只读 Tool：销售订单与采购到货预警（spec 195）。

Tool 名：``query_sales_orders`` / ``query_purchase_arrival_warnings``。

- ``query_sales_orders``：``SalesOrderService.list_sales_orders`` 走
  ``view="options"`` 轻量路径——完整路径在返回前会对状态/审核不一致行做
  「批量状态同步」回写（``sales_order_service.py`` 约 2804–2816 行），
  只读 Tool 不写库故必须走 options；交货进度缺省不返回，适配层用同一
  service 的 ``_merged_delivery_progress`` + ``_shipped_qty_by_sales_order``
  计算，口径与列表一致。数据范围经 service 内
  ``_apply_sales_order_list_scope(current_user)``（kuaizhizao:sales-order）。
- ``query_purchase_arrival_warnings``：``PurchaseArrivalWarningService``
  ``.list_warnings``，service 内 ``_scoped_po_query(current_user)`` 套
  ``kuaizhizao:purchase-order`` 数据范围；行 ``warning_level`` /
  ``processing_status`` 全由 service 给出，LLM 不判定。
- 不输出客户/供应商联系人、电话、地址、单价、金额等商务敏感字段。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List, Optional

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"

# 视图闭集：summary 表头摘要；lines 输出明细行（material/数量/行交期）
_SALES_ORDER_VIEWS = frozenset({"summary", "lines"})

# status 闭集：apps.kuaizhizao.constants.DemandStatus（销售订单 status 字段
# 的 schema 枚举；存量中文值为读兼容，Tool 参数只收枚举值）
_SALES_ORDER_STATUSES = frozenset(
    {
        "DRAFT",
        "PENDING_REVIEW",
        "AUDITED",
        "REJECTED",
        "CONFIRMED",
        "CLOSED",
        "CANCELLED",
        "COMPLETED",
    }
)

# warning_level 闭集：apps.kuaizhizao.utils.purchase_arrival_warning
# WARNING_LEVEL_NORMAL/IMMINENT/OVERDUE
_ARRIVAL_WARNING_LEVELS = frozenset({"normal", "imminent", "overdue"})

# processing_status 闭集：resolve_arrival_processing_status 全部返回值
# （与前端 PurchaseArrivalProcessingStatus 类型一致）
_ARRIVAL_PROCESSING_STATUSES = frozenset(
    {
        "unprocessed",
        "reported",
        "pending_review",
        "approved",
        "change_pending",
        "changed",
        "rejected",
    }
)

_WARNING_LEVEL_ZH = {
    "normal": "正常",
    "imminent": "临期",
    "overdue": "逾期",
}

# 明细行输出上限（view=lines 每单最多展开的明细条数）
_LINES_PER_ORDER_MAX = 20


def _ct():
    """chat_tools 私有助手延迟借用（与 scene_tools 同模式，避免循环导入）。"""
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _parse_date(value: Any):
    """YYYY-MM-DD → date；非法返回 None（复用 scene_tools 实现）。"""
    from apps.kuaiai.services import scene_tools

    return scene_tools._parse_date(value)


def _fmt_progress(value: Any) -> str:
    """交货进度百分比（0-100 float）转可读文本。"""
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "0%"


def _fmt_sales_order_row(order: Any, progress: Any = None) -> str:
    """销售订单行摘要（Tool 与页上下文 reader 共用口径，spec 204 AC4）。

    ``progress`` 为 0-100 交货进度值；缺省不输出进度段。
    不含客户联系人/电话/金额等敏感字段。
    """
    text = (
        f"订单 {getattr(order, 'order_code', '') or ''}："
        f"客户 {getattr(order, 'customer_name', '') or '未知'}，"
        f"状态 {getattr(order, 'status', '') or '未知'}"
        f"/{getattr(order, 'review_status', '') or '未审'}，"
        f"交货期 {getattr(order, 'delivery_date', '') or '未定'}"
    )
    if progress is not None:
        text += f"，交货进度 {_fmt_progress(progress)}"
    text += f"（id={getattr(order, 'id', '')}）"
    return text


async def _delivery_progress_map(
    service: Any, tenant_id: int, orders: List[Any]
) -> dict:
    """对 options 响应订单批量算交货进度（与列表 ``_merged_delivery_progress``
    同口径：明细已交合计与已出库出库数量取较大比例）。"""
    order_ids = [int(o.id) for o in orders if getattr(o, "id", None)]
    shipped = await service._shipped_qty_by_sales_order(tenant_id, order_ids)
    progress: dict = {}
    for order in orders:
        items = [
            SimpleNamespace(
                order_quantity=getattr(it, "required_quantity", None),
                delivered_quantity=getattr(it, "delivered_quantity", None),
            )
            for it in (getattr(order, "items", None) or [])
        ]
        progress[int(order.id)] = service._merged_delivery_progress(
            order, items, shipped.get(int(order.id))
        )
    return progress


async def query_sales_orders(
    view: str = "summary",
    order_code: Optional[str] = None,
    customer_name: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """销售订单交付进度摘要（view=summary 表头 / view=lines 明细行）。

    数据范围由 ``list_sales_orders(current_user=ctx.user)`` 内
    ``_apply_sales_order_list_scope`` 保证；options 轻量路径无写副作用。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    resolved_view = str(view or "summary").strip()
    if resolved_view not in _SALES_ORDER_VIEWS:
        return "view 仅支持 summary|lines"
    status_norm = (str(status).strip() or None) if status else None
    if status_norm is not None and status_norm not in _SALES_ORDER_STATUSES:
        return (
            "status 仅支持 DRAFT/PENDING_REVIEW/AUDITED/REJECTED/"
            "CONFIRMED/CLOSED/CANCELLED/COMPLETED"
        )
    start_d = _parse_date(start_date) if start_date else None
    if start_date and start_d is None:
        return "start_date 须为 YYYY-MM-DD 格式的日期"
    end_d = _parse_date(end_date) if end_date else None
    if end_date and end_d is None:
        return "end_date 须为 YYYY-MM-DD 格式的日期"
    try:
        from apps.kuaizhizao.services.sales_order_service import SalesOrderService

        service = SalesOrderService()
        result = await service.list_sales_orders(
            ctx.tenant_id,
            skip=0,
            limit=_ct()._clamp_limit(limit),
            status=status_norm,
            start_date=start_d,
            end_date=end_d,
            customer_name=(str(customer_name).strip() or None)
            if customer_name
            else None,
            order_code=(str(order_code).strip() or None) if order_code else None,
            # 交货进度需明细行参与计算，两视图都取轻量明细
            include_items=True,
            view="options",
            current_user=ctx.user,
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_sales_orders 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询销售订单失败，请稍后重试"

    orders = list(getattr(result, "data", None) or [])
    total = int(getattr(result, "total", None) or len(orders))
    if not orders:
        return "当前用户数据范围内未查询到符合条件的销售订单"

    if resolved_view == "lines":
        lines = [
            f"共 {total} 张销售订单（当前用户数据范围内），返回前 {len(orders)} 张明细："
        ]
        for order in orders:
            items = list(getattr(order, "items", None) or [])
            if not items:
                lines.append(
                    f"订单 {getattr(order, 'order_code', '') or ''}"
                    f"（{getattr(order, 'customer_name', '') or '未知客户'}）：无明细行"
                )
                continue
            lines.append(
                f"订单 {getattr(order, 'order_code', '') or ''}"
                f"（{getattr(order, 'customer_name', '') or '未知客户'}）"
                f"共 {len(items)} 行："
            )
            for it in items[:_LINES_PER_ORDER_MAX]:
                lines.append(
                    f"  物料 {getattr(it, 'material_code', '') or ''}"
                    f"（{getattr(it, 'material_name', '') or '未命名'}）："
                    f"数量 {_ct()._fmt_num(getattr(it, 'required_quantity', None))}，"
                    f"已交 {_ct()._fmt_num(getattr(it, 'delivered_quantity', None))}，"
                    f"行交期 {getattr(it, 'delivery_date', '') or '未定'}，"
                    f"交货状态 {getattr(it, 'delivery_status', '') or '未知'}"
                )
            if len(items) > _LINES_PER_ORDER_MAX:
                lines.append(f"  ……另有 {len(items) - _LINES_PER_ORDER_MAX} 行未展开")
        return "\n".join(lines)

    try:
        progress = await _delivery_progress_map(service, ctx.tenant_id, orders)
    except Exception as exc:
        logger.warning(
            "AI tool query_sales_orders 交货进度计算失败 error_type={}",
            type(exc).__name__,
        )
        return "查询销售订单失败，请稍后重试"
    lines = [
        f"共 {total} 张销售订单（当前用户数据范围内），返回前 {len(orders)} 张："
    ]
    for order in orders:
        lines.append(
            _fmt_sales_order_row(order, progress.get(int(order.id)))
        )
    return "\n".join(lines)


async def query_purchase_arrival_warnings(
    warning_level: Optional[str] = None,
    supplier_id: Optional[int] = None,
    order_code: Optional[str] = None,
    processing_status: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """采购到货预警摘要（行级 required_date + 未收数量，与预警页同口径）。

    数据范围由 ``list_warnings(current_user=ctx.user)`` 内
    ``_scoped_po_query`` 保证；预警级别与处理状态取 service 结果。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    level = (str(warning_level).strip() or None) if warning_level else None
    if level is not None and level not in _ARRIVAL_WARNING_LEVELS:
        return "warning_level 仅支持 normal/imminent/overdue"
    proc = (
        (str(processing_status).strip() or None) if processing_status else None
    )
    if proc is not None and proc not in _ARRIVAL_PROCESSING_STATUSES:
        return (
            "processing_status 仅支持 unprocessed/reported/pending_review/"
            "approved/change_pending/changed/rejected"
        )
    try:
        from apps.kuaizhizao.services.purchase_arrival_warning_service import (
            PurchaseArrivalWarningService,
        )

        result = await PurchaseArrivalWarningService().list_warnings(
            ctx.tenant_id,
            skip=0,
            limit=_ct()._clamp_limit(limit),
            warning_level=level,
            supplier_id=int(supplier_id) if supplier_id else None,
            order_code=(str(order_code).strip() or None) if order_code else None,
            processing_status=proc,
            current_user=ctx.user,
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_purchase_arrival_warnings 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询采购到货预警失败，请稍后重试"

    rows = list((result or {}).get("data") or [])
    total = int((result or {}).get("total") or len(rows))
    if not rows:
        return "当前用户数据范围内未查询到采购到货预警"

    summary = (result or {}).get("summary") or {}
    head = (
        f"共 {total} 条采购到货预警行（当前用户数据范围内），"
        f"返回前 {len(rows)} 条"
    )
    if summary:
        head += (
            f"（逾期 {summary.get('overdue', 0)} /"
            f" 临期 {summary.get('imminent', 0)} /"
            f" 正常 {summary.get('normal', 0)}）"
        )
    lines = [head + "："]
    for r in rows:
        level_zh = _WARNING_LEVEL_ZH.get(
            str(r.get("warning_level") or ""), str(r.get("warning_level") or "未知")
        )
        days = ""
        if int(r.get("overdue_days") or 0) > 0:
            days = f"，逾期 {r.get('overdue_days')} 天"
        elif int(r.get("remaining_days") or 0) > 0:
            days = f"，剩余 {r.get('remaining_days')} 天"
        lines.append(
            f"采购单 {r.get('order_code') or ''}："
            f"供应商 {r.get('supplier_name') or '未知'}，"
            f"物料 {r.get('material_code') or ''}"
            f"（{r.get('material_name') or '未命名'}），"
            f"待收 {_ct()._fmt_num(r.get('outstanding_quantity'))}"
            f"{r.get('unit') or ''}，"
            f"要求到货 {r.get('required_date') or '未定'}，"
            f"预警 {level_zh}{days}，"
            f"处理状态 {r.get('processing_status') or 'unprocessed'}"
            f"（行id={r.get('purchase_order_item_id') or r.get('id') or ''}）"
        )
    return "\n".join(lines)
