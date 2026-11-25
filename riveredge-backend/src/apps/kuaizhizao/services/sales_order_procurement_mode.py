"""销售订单外购履单路径（采购申请轨 vs 采购订单轨，二选一）。"""

from __future__ import annotations

import asyncio
from typing import Any, List, Optional

from apps.kuaizhizao.services.sales_order_purchase_push import (
    _is_purchase_order_doc_type,
    _is_sales_order_source,
    require_purchase_requisition_for_tenant,
)

PROCUREMENT_MODE_REQUISITION = "purchase_requisition"
PROCUREMENT_MODE_ORDER = "purchase_order"
_PROCUREMENT_MODES = frozenset({PROCUREMENT_MODE_REQUISITION, PROCUREMENT_MODE_ORDER})


def normalize_procurement_fulfillment_mode(raw: Any) -> Optional[str]:
    val = str(raw or "").strip().lower().replace("-", "_")
    if val in _PROCUREMENT_MODES:
        return val
    return None


async def infer_procurement_fulfillment_mode(tenant_id: int, sales_order_id: int) -> Optional[str]:
    """历史单：存在 SO 来源采购申请则请购轨，否则存在直推采购订单则直采轨。"""
    from apps.kuaizhizao.models.purchase_order import PurchaseOrder
    from apps.kuaizhizao.models.purchase_requisition import PurchaseRequisition

    oid = int(sales_order_id or 0)
    if oid <= 0:
        return None

    pr_count, po_count = await asyncio.gather(
        PurchaseRequisition.filter(
            tenant_id=tenant_id,
            source_id=oid,
            deleted_at__isnull=True,
        ).count(),
        PurchaseOrder.filter(
            tenant_id=tenant_id,
            source_id=oid,
            deleted_at__isnull=True,
        ).count(),
    )
    has_pr = False
    if pr_count > 0:
        prs = await PurchaseRequisition.filter(
            tenant_id=tenant_id, source_id=oid, deleted_at__isnull=True
        ).only("source_type")
        has_pr = any(_is_sales_order_source(pr.source_type) for pr in prs)
    has_po = False
    if po_count > 0:
        pos = await PurchaseOrder.filter(
            tenant_id=tenant_id, source_id=oid, deleted_at__isnull=True
        ).only("source_type")
        has_po = any(_is_sales_order_source(po.source_type) for po in pos)

    if has_pr and not has_po:
        return PROCUREMENT_MODE_REQUISITION
    if has_po and not has_pr:
        return PROCUREMENT_MODE_ORDER
    if has_pr and has_po:
        return PROCUREMENT_MODE_REQUISITION
    return None


async def batch_resolve_procurement_fulfillment_mode(
    tenant_id: int,
    orders: List[Any],
) -> dict[int, Optional[str]]:
    """批量解析销售订单外购履单路径（列表门禁/进度用）。"""
    if not orders:
        return {}
    require_pr = await require_purchase_requisition_for_tenant(tenant_id)
    out: dict[int, Optional[str]] = {}
    need_infer: List[int] = []
    for order in orders:
        oid = int(getattr(order, "id", 0) or 0)
        stored = normalize_procurement_fulfillment_mode(
            getattr(order, "procurement_fulfillment_mode", None)
        )
        if stored:
            out[oid] = stored
        elif require_pr:
            out[oid] = PROCUREMENT_MODE_REQUISITION
        else:
            need_infer.append(oid)
    if need_infer:
        inferred = await _batch_infer_procurement_fulfillment_mode(tenant_id, need_infer)
        for oid in need_infer:
            out[oid] = inferred.get(oid)
    return out


async def _batch_infer_procurement_fulfillment_mode(
    tenant_id: int,
    sales_order_ids: List[int],
) -> dict[int, Optional[str]]:
    from apps.kuaizhizao.models.purchase_order import PurchaseOrder
    from apps.kuaizhizao.models.purchase_requisition import PurchaseRequisition

    if not sales_order_ids:
        return {}
    pr_rows = await PurchaseRequisition.filter(
        tenant_id=tenant_id,
        source_id__in=sales_order_ids,
        deleted_at__isnull=True,
    ).values_list("source_id", "source_type")
    po_rows = await PurchaseOrder.filter(
        tenant_id=tenant_id,
        source_id__in=sales_order_ids,
        deleted_at__isnull=True,
    ).values_list("source_id", "source_type")
    has_pr: set[int] = set()
    has_po: set[int] = set()
    for oid, st in pr_rows:
        if _is_sales_order_source(st):
            has_pr.add(int(oid))
    for oid, st in po_rows:
        if _is_sales_order_source(st):
            has_po.add(int(oid))
    out: dict[int, Optional[str]] = {}
    for oid in sales_order_ids:
        pr = int(oid) in has_pr
        po = int(oid) in has_po
        if pr and not po:
            out[int(oid)] = PROCUREMENT_MODE_REQUISITION
        elif po and not pr:
            out[int(oid)] = PROCUREMENT_MODE_ORDER
        elif pr and po:
            out[int(oid)] = PROCUREMENT_MODE_REQUISITION
        else:
            out[int(oid)] = None
    return out


async def resolve_procurement_fulfillment_mode(tenant_id: int, order: Any) -> Optional[str]:
    stored = normalize_procurement_fulfillment_mode(
        getattr(order, "procurement_fulfillment_mode", None)
    )
    if stored:
        return stored
    if await require_purchase_requisition_for_tenant(tenant_id):
        return PROCUREMENT_MODE_REQUISITION
    return await infer_procurement_fulfillment_mode(tenant_id, int(order.id))


async def lock_procurement_fulfillment_mode(
    tenant_id: int,
    sales_order_id: int,
    mode: str,
) -> None:
    normalized = normalize_procurement_fulfillment_mode(mode)
    if not normalized:
        return
    from apps.kuaizhizao.models.sales_order import SalesOrder

    order = await SalesOrder.get_or_none(
        tenant_id=tenant_id, id=int(sales_order_id), deleted_at__isnull=True
    )
    if not order:
        return
    current = normalize_procurement_fulfillment_mode(
        getattr(order, "procurement_fulfillment_mode", None)
    )
    if current:
        return
    order.procurement_fulfillment_mode = normalized
    await order.save(update_fields=["procurement_fulfillment_mode", "updated_at"])


async def assert_procurement_mode_allows_push(
    tenant_id: int,
    order: Any,
    target: str,
) -> None:
    """target: purchase_requisition | purchase_order"""
    from infra.exceptions.exceptions import BusinessLogicError

    want = normalize_procurement_fulfillment_mode(target)
    if not want:
        return
    mode = await resolve_procurement_fulfillment_mode(tenant_id, order)
    if not mode:
        return
    if mode != want:
        raise BusinessLogicError(
            "该销售订单已走"
            + ("采购申请" if mode == PROCUREMENT_MODE_REQUISITION else "采购订单")
            + "履单路径，不可再从此单下推"
            + ("采购订单" if want == PROCUREMENT_MODE_ORDER else "采购申请")
        )


async def list_sales_order_purchase_downstream_codes(
    tenant_id: int,
    sales_order_ids: List[int],
    mode: Optional[str],
) -> dict[int, List[str]]:
    """按履单路径收集下游采购申请或采购订单单号（列表进度气泡）。"""
    from apps.kuaizhizao.models.document_relation import DocumentRelation
    from apps.kuaizhizao.models.purchase_order import PurchaseOrder
    from apps.kuaizhizao.models.purchase_requisition import PurchaseRequisition

    if not sales_order_ids:
        return {}

    out: dict[int, List[str]] = {int(oid): [] for oid in sales_order_ids}
    normalized = normalize_procurement_fulfillment_mode(mode)

    if normalized != PROCUREMENT_MODE_ORDER:
        prs = await PurchaseRequisition.filter(
            tenant_id=tenant_id,
            source_id__in=sales_order_ids,
            deleted_at__isnull=True,
        ).all()
        for pr in prs:
            if not _is_sales_order_source(pr.source_type):
                continue
            oid = int(pr.source_id or 0)
            code = str(pr.requisition_code or "").strip()
            if oid in out and code:
                out[oid].append(code)

    if normalized != PROCUREMENT_MODE_REQUISITION:
        pos = await PurchaseOrder.filter(
            tenant_id=tenant_id,
            source_id__in=sales_order_ids,
            deleted_at__isnull=True,
        ).all()
        for po in pos:
            if not _is_sales_order_source(po.source_type):
                continue
            oid = int(po.source_id or 0)
            code = str(po.order_code or "").strip()
            if oid in out and code:
                out[oid].append(code)

        rels = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_id__in=sales_order_ids,
        ).all()
        live_po_ids = {int(po.id) for po in pos}
        for rel in rels:
            if not _is_sales_order_source(rel.source_type):
                continue
            if not _is_purchase_order_doc_type(rel.target_type):
                continue
            oid = int(rel.source_id or 0)
            code = str(rel.target_code or "").strip()
            if oid in out and code and int(rel.target_id or 0) in live_po_ids:
                if code not in out[oid]:
                    out[oid].append(code)
    return out