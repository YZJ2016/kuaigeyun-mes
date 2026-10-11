"""
销售订单编号：下游检测与改号后快照同步。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from apps.kuaizhizao.constants import DemandStatus, normalize_status
from apps.kuaizhizao.models.sales_order import SalesOrder
from core.services.document_code_editability import (
    REASON_HAS_DOWNSTREAM,
    REASON_MANUAL_EDIT_DISABLED,
    resolve_document_code_editable,
)
from core.services.business.code_generation_service import CodeGenerationService
from infra.exceptions.exceptions import BusinessLogicError, ValidationError


def _is_sales_order_draft(order: SalesOrder) -> bool:
    return normalize_status(str(order.status or "")) == DemandStatus.DRAFT.value


def _lazy_work_order_model():
    from apps.kuaizhizao.models.work_order import WorkOrder

    return WorkOrder


def _lazy_sales_delivery_model():
    from apps.kuaizhizao.models.sales_delivery import SalesDelivery

    return SalesDelivery


def _lazy_shipment_notice_model():
    from apps.kuaizhizao.models.shipment_notice import ShipmentNotice

    return ShipmentNotice


def _lazy_sales_return_model():
    from apps.kuaizhizao.models.sales_return import SalesReturn

    return SalesReturn


_SALES_ORDER_DOWNSTREAM_FK_SPECS: List[Tuple[Any, str]] = [
    (_lazy_work_order_model, "sales_order_id"),
    (_lazy_sales_delivery_model, "sales_order_id"),
    (_lazy_shipment_notice_model, "sales_order_id"),
    (_lazy_sales_return_model, "sales_order_id"),
]


async def sales_order_downstream_by_ids(
    tenant_id: int, sales_order_ids: List[int]
) -> dict[int, bool]:
    """列表 capabilities 批量检测：工单/出库/发货通知/销售退货等 FK 下游。"""
    if not sales_order_ids:
        return {}
    result: dict[int, bool] = {int(i): False for i in sales_order_ids}

    def _mark(order_id: int) -> None:
        result[int(order_id)] = True

    for loader, field in _SALES_ORDER_DOWNSTREAM_FK_SPECS:
        model = loader()
        fields_map = getattr(getattr(model, "_meta", None), "fields_map", {}) or {}
        if field not in fields_map:
            continue
        filters: Dict[str, Any] = {
            "tenant_id": tenant_id,
            f"{field}__in": sales_order_ids,
        }
        if "deleted_at" in fields_map:
            filters["deleted_at__isnull"] = True
        related_ids = await model.filter(**filters).values_list(field, flat=True)
        for oid in related_ids:
            if oid is not None:
                _mark(int(oid))
    return result


_SALES_ORDER_DOWNSTREAM_TYPE_LABELS: Dict[str, str] = {
    "work_order": "工单",
    "demand_computation": "需求计算",
    "shipment_notice": "发货通知",
    "sales_delivery": "销售出库",
    "sales_return": "销售退货",
    "sales_invoice": "销售发票",
    "delivery_project": "交付项目",
}

# 销售订单删除时会级联处理的伴随单据，不作为「不可删除」的下游拦截
_SALES_ORDER_DELETE_IGNORE_DOWNSTREAM_TYPES = frozenset({"demand"})


def _flatten_active_downstream_nodes(
    nodes: List[Any],
    collected: Optional[Dict[Tuple[str, int], Dict[str, Any]]] = None,
) -> Dict[Tuple[str, int], Dict[str, Any]]:
    """仅收集未删除的下游节点（忽略 is_deleted / 级联伴随 demand）。"""
    if collected is None:
        collected = {}
    for node in nodes:
        doc_type = str(getattr(node, "document_type", "") or "")
        if doc_type in _SALES_ORDER_DELETE_IGNORE_DOWNSTREAM_TYPES:
            _flatten_active_downstream_nodes(getattr(node, "children", None) or [], collected)
            continue
        if bool(getattr(node, "is_deleted", False)):
            # 已删节点的子树仍可能挂着有效单据，继续下钻
            _flatten_active_downstream_nodes(getattr(node, "children", None) or [], collected)
            continue
        doc_id = int(getattr(node, "document_id", 0) or 0)
        if doc_id <= 0:
            continue
        key = (doc_type, doc_id)
        if key not in collected:
            collected[key] = {
                "document_type": doc_type,
                "document_id": doc_id,
                "document_code": getattr(node, "document_code", None),
                "document_name": getattr(node, "document_name", None),
            }
        _flatten_active_downstream_nodes(getattr(node, "children", None) or [], collected)
    return collected


async def list_sales_order_active_downstream_documents(
    tenant_id: int, sales_order_id: int
) -> List[Dict[str, Any]]:
    """销售订单有效下游（未软删），用于删除/改号门禁与报错明细。"""
    from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService

    trace = await DocumentRelationNewService().trace_document_chain(
        tenant_id=tenant_id,
        document_type="sales_order",
        document_id=sales_order_id,
        direction="downstream",
        max_depth=10,
    )
    collected = _flatten_active_downstream_nodes(trace.downstream_chain)
    if collected:
        return list(collected.values())

    downstream_map = await sales_order_downstream_by_ids(tenant_id, [sales_order_id])
    if not downstream_map.get(sales_order_id, False):
        return []

    # FK 兜底：追溯树为空但 FK 仍指向有效单据时，补齐明细
    docs: List[Dict[str, Any]] = []
    for loader, field in _SALES_ORDER_DOWNSTREAM_FK_SPECS:
        model = loader()
        fields_map = getattr(getattr(model, "_meta", None), "fields_map", {}) or {}
        if field not in fields_map:
            continue
        filters: Dict[str, Any] = {
            "tenant_id": tenant_id,
            field: sales_order_id,
        }
        if "deleted_at" in fields_map:
            filters["deleted_at__isnull"] = True
        rows = await model.filter(**filters).limit(20)
        type_name = {
            _lazy_work_order_model: "work_order",
            _lazy_sales_delivery_model: "sales_delivery",
            _lazy_shipment_notice_model: "shipment_notice",
            _lazy_sales_return_model: "sales_return",
        }.get(loader, "downstream")
        for row in rows:
            code = (
                getattr(row, "code", None)
                or getattr(row, "delivery_code", None)
                or getattr(row, "notice_code", None)
                or getattr(row, "return_code", None)
            )
            docs.append(
                {
                    "document_type": type_name,
                    "document_id": int(row.id),
                    "document_code": code,
                    "document_name": getattr(row, "name", None),
                }
            )
    return docs


def format_sales_order_downstream_labels(docs: List[Dict[str, Any]], *, limit: int = 5) -> str:
    parts: List[str] = []
    for doc in docs[:limit]:
        type_label = _SALES_ORDER_DOWNSTREAM_TYPE_LABELS.get(
            str(doc.get("document_type") or ""),
            str(doc.get("document_type") or "下游"),
        )
        code = str(doc.get("document_code") or doc.get("document_id") or "").strip()
        parts.append(f"{type_label}{code}" if code else type_label)
    if len(docs) > limit:
        parts.append(f"等{len(docs)}单")
    return "、".join(parts)


async def sales_order_has_downstream_documents(tenant_id: int, sales_order_id: int) -> bool:
    docs = await list_sales_order_active_downstream_documents(tenant_id, sales_order_id)
    return bool(docs)


async def resolve_sales_order_code_editable(
    tenant_id: int,
    order: SalesOrder,
    *,
    allow_manual_edit: bool = True,
) -> tuple[bool, str | None]:
    has_downstream = await sales_order_has_downstream_documents(tenant_id, int(order.id))
    return resolve_document_code_editable(
        is_draft=_is_sales_order_draft(order),
        has_downstream=has_downstream,
        allow_manual_edit=allow_manual_edit,
    )


async def assert_sales_order_code_change_allowed(
    tenant_id: int,
    order: SalesOrder,
    new_code: str,
    *,
    allow_manual_edit: bool = True,
) -> None:
    new_code = (new_code or "").strip()
    if not new_code:
        raise ValidationError("销售订单编号不能为空")
    old_code = (order.order_code or "").strip()
    if new_code == old_code:
        return

    editable, reason = await resolve_sales_order_code_editable(
        tenant_id,
        order,
        allow_manual_edit=allow_manual_edit,
    )
    if not editable:
        if reason == REASON_MANUAL_EDIT_DISABLED:
            raise BusinessLogicError("当前编号规则不允许手工修改订单编号")
        if reason == REASON_HAS_DOWNSTREAM:
            raise BusinessLogicError("销售订单已有下游单据，不可修改编号")
        raise BusinessLogicError("当前状态不可修改销售订单编号")

    exists = await CodeGenerationService._check_code_exists(
        tenant_id=tenant_id,
        code=new_code,
        entity_type="sales_order",
    )
    if exists and new_code != old_code:
        other = await SalesOrder.get_or_none(
            tenant_id=tenant_id,
            order_code=new_code,
            deleted_at__isnull=True,
        )
        if other and int(other.id) != int(order.id):
            raise ValidationError("销售订单编号已存在")


async def sync_sales_order_code_snapshots(
    tenant_id: int,
    sales_order_id: int,
    new_code: str,
    *,
    old_code: str | None = None,
) -> None:
    """改号后同步 sales_order_id 关联的快照编码与单据关系。"""
    new_code = (new_code or "").strip()
    if not new_code:
        return

    snapshot_specs: List[Tuple[Any, str, str]] = [
        (_lazy_work_order_model, "sales_order_id", "sales_order_code"),
        (_lazy_sales_delivery_model, "sales_order_id", "sales_order_code"),
        (_lazy_shipment_notice_model, "sales_order_id", "sales_order_code"),
        (_lazy_sales_return_model, "sales_order_id", "sales_order_code"),
        (_lazy_delivery_notice_model, "sales_order_id", "sales_order_code"),
        (_lazy_delivery_project_model, "sales_order_id", "sales_order_code"),
        (_lazy_oqc_inspection_model, "sales_order_id", "sales_order_code"),
        (_lazy_finished_goods_receipt_model, "sales_order_id", "sales_order_code"),
        (_lazy_finished_goods_inspection_model, "sales_order_id", "sales_order_code"),
        (_lazy_after_sales_ticket_model, "sales_order_id", "sales_order_code"),
        (_lazy_after_sales_service_model, "sales_order_id", "sales_order_code"),
        (_lazy_quotation_model, "sales_order_id", "sales_order_code"),
    ]

    for loader, id_field, code_field in snapshot_specs:
        model = loader()
        fields_map = getattr(getattr(model, "_meta", None), "fields_map", {}) or {}
        if id_field not in fields_map or code_field not in fields_map:
            continue
        filters: Dict[str, Any] = {"tenant_id": tenant_id, id_field: sales_order_id}
        if "deleted_at" in fields_map:
            filters["deleted_at__isnull"] = True
        await model.filter(**filters).update(**{code_field: new_code})

    from apps.kuaizhizao.models.demand import Demand

    demand_filters: Dict[str, Any] = {
        "tenant_id": tenant_id,
        "source_type": "sales_order",
        "source_id": sales_order_id,
        "deleted_at__isnull": True,
    }
    await Demand.filter(**demand_filters).update(source_code=new_code)
    if old_code:
        await Demand.filter(**demand_filters, demand_code=old_code).update(demand_code=new_code)

    from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService

    await DocumentRelationNewService().refresh_document_code_snapshots(
        tenant_id,
        document_type="sales_order",
        document_id=sales_order_id,
        code=new_code,
        refresh_source=True,
        refresh_target=False,
    )

    logger.info(
        "销售订单 {} 编号已同步快照为 {}",
        sales_order_id,
        new_code,
    )


def _lazy_delivery_notice_model():
    from apps.kuaizhizao.models.delivery_notice import DeliveryNotice

    return DeliveryNotice


def _lazy_delivery_project_model():
    from apps.kuaizhizao.models.delivery_project import DeliveryProject

    return DeliveryProject


def _lazy_oqc_inspection_model():
    from apps.kuaizhizao.models.oqc_inspection import OqcInspection

    return OqcInspection


def _lazy_finished_goods_receipt_model():
    from apps.kuaizhizao.models.finished_goods_receipt import FinishedGoodsReceipt

    return FinishedGoodsReceipt


def _lazy_finished_goods_inspection_model():
    from apps.kuaizhizao.models.finished_goods_inspection import FinishedGoodsInspection

    return FinishedGoodsInspection


def _lazy_after_sales_ticket_model():
    from apps.kuaizhizao.models.after_sales_ticket import AfterSalesTicket

    return AfterSalesTicket


def _lazy_after_sales_service_model():
    from apps.kuaizhizao.models.after_sales_service import AfterSalesService

    return AfterSalesService


def _lazy_quotation_model():
    from apps.kuaizhizao.models.quotation import Quotation

    return Quotation
