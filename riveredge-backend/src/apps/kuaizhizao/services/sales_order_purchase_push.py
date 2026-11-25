"""销售订单直推采购申请 / 采购订单（按单外购捷径）。

数量按销售明细订单量减已下推占用，不做库存净需求；占用仅计
source_type=sales_order 的采购申请与直推采购订单，避免与需求计算路径重复累计。
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from apps.kuaizhizao.utils.material_source_helper import (
    SOURCE_TYPE_BUY,
    SOURCE_TYPE_MAKE,
    SOURCE_TYPE_OUTSOURCE,
    material_source_types_set,
)
from core.utils.timezone_utils import resolve_business_datetime, to_site_date
from infra.exceptions.exceptions import BusinessLogicError


def _is_sales_order_source(source_type: Any) -> bool:
    raw = str(source_type or "").strip().lower().replace("-", "_")
    return raw in {"sales_order", "salesorder"}


def _is_purchase_order_doc_type(doc_type: Any) -> bool:
    raw = str(doc_type or "").strip().lower().replace("-", "_")
    return raw in {"purchase_order", "purchaseorder"}


def _add_po_item_qty(
    result: Dict[int, Dict[int, Decimal]],
    sales_order_id: int,
    material_id: int,
    quantity: Any,
) -> None:
    oid = int(sales_order_id or 0)
    mid = int(material_id or 0)
    if oid not in result or mid <= 0:
        return
    bucket = result.setdefault(oid, {})
    bucket[mid] = bucket.get(mid, Decimal("0")) + Decimal(str(quantity or 0))


async def require_purchase_requisition_for_tenant(tenant_id: int) -> bool:
    from infra.services.business_config_service import BusinessConfigService

    biz_config = await BusinessConfigService().get_business_config(tenant_id)
    return bool(
        biz_config.get("parameters", {})
        .get("procurement", {})
        .get("require_purchase_requisition", False)
    )


async def batch_pushed_purchase_requisition_qty_by_material(
    tenant_id: int,
    sales_order_ids: List[int],
) -> Dict[int, Dict[int, Decimal]]:
    """order_id → material_id → 已占用（仅 SO→采购申请）。"""
    result: Dict[int, Dict[int, Decimal]] = {int(oid): {} for oid in sales_order_ids}
    if not sales_order_ids:
        return result

    from apps.kuaizhizao.models.purchase_requisition import (
        PurchaseRequisition,
        PurchaseRequisitionItem,
    )

    prs = await PurchaseRequisition.filter(
        tenant_id=tenant_id,
        source_id__in=sales_order_ids,
        deleted_at__isnull=True,
    ).all()
    pr_ids_by_order: Dict[int, List[int]] = {}
    for pr in prs:
        if not _is_sales_order_source(pr.source_type):
            continue
        oid = int(pr.source_id or 0)
        if oid not in result:
            continue
        pr_ids_by_order.setdefault(oid, []).append(int(pr.id))

    all_pr_ids = [pid for ids in pr_ids_by_order.values() for pid in ids]
    if not all_pr_ids:
        return result
    pr_items = await PurchaseRequisitionItem.filter(
        tenant_id=tenant_id,
        requisition_id__in=all_pr_ids,
    ).all()
    pr_order_by_id = {pid: oid for oid, ids in pr_ids_by_order.items() for pid in ids}
    for item in pr_items:
        oid = pr_order_by_id.get(int(item.requisition_id))
        mid = int(item.material_id or 0)
        if not oid or mid <= 0:
            continue
        bucket = result.setdefault(oid, {})
        bucket[mid] = bucket.get(mid, Decimal("0")) + Decimal(str(item.quantity or 0))
    return result


async def batch_pushed_purchase_order_qty_by_material(
    tenant_id: int,
    sales_order_ids: List[int],
) -> Dict[int, Dict[int, Decimal]]:
    """order_id → material_id → 已占用（仅 SO→采购订单）。"""
    result: Dict[int, Dict[int, Decimal]] = {int(oid): {} for oid in sales_order_ids}
    if not sales_order_ids:
        return result

    from apps.kuaizhizao.models.document_relation import DocumentRelation
    from apps.kuaizhizao.models.purchase_order import PurchaseOrder, PurchaseOrderItem

    pos = await PurchaseOrder.filter(
        tenant_id=tenant_id,
        source_id__in=sales_order_ids,
        deleted_at__isnull=True,
    ).all()
    po_ids_by_order: Dict[int, List[int]] = {}
    counted_po_ids: set[int] = set()
    for po in pos:
        if not _is_sales_order_source(po.source_type):
            continue
        oid = int(po.source_id or 0)
        if oid not in result:
            continue
        pid = int(po.id)
        po_ids_by_order.setdefault(oid, []).append(pid)
        counted_po_ids.add(pid)

    def _ingest_po_items(po_items: List[Any], order_by_po: Dict[int, int]) -> None:
        for item in po_items:
            oid = order_by_po.get(int(item.order_id or 0))
            if not oid:
                continue
            _add_po_item_qty(result, oid, int(item.material_id or 0), item.ordered_quantity)

    all_po_ids = [pid for ids in po_ids_by_order.values() for pid in ids]
    if all_po_ids:
        po_items = await PurchaseOrderItem.filter(
            tenant_id=tenant_id,
            order_id__in=all_po_ids,
            deleted_at__isnull=True,
        ).all()
        po_order_by_id = {pid: oid for oid, ids in po_ids_by_order.items() for pid in ids}
        _ingest_po_items(po_items, po_order_by_id)

    extra_po_by_order: Dict[int, List[int]] = {}
    rels = await DocumentRelation.filter(
        tenant_id=tenant_id,
        source_id__in=sales_order_ids,
    ).all()
    for rel in rels:
        if not _is_sales_order_source(rel.source_type):
            continue
        if not _is_purchase_order_doc_type(rel.target_type):
            continue
        oid = int(rel.source_id or 0)
        pid = int(rel.target_id or 0)
        if oid not in result or pid <= 0 or pid in counted_po_ids:
            continue
        extra_po_by_order.setdefault(oid, []).append(pid)
        counted_po_ids.add(pid)

    extra_po_ids = sorted({pid for ids in extra_po_by_order.values() for pid in ids})
    if extra_po_ids:
        extra_items = await PurchaseOrderItem.filter(
            tenant_id=tenant_id,
            order_id__in=extra_po_ids,
            deleted_at__isnull=True,
        ).all()
        extra_order_by_po = {pid: oid for oid, ids in extra_po_by_order.items() for pid in ids}
        _ingest_po_items(extra_items, extra_order_by_po)

    line_items = await PurchaseOrderItem.filter(
        tenant_id=tenant_id,
        source_id__in=sales_order_ids,
        deleted_at__isnull=True,
    ).all()
    for item in line_items:
        if not _is_sales_order_source(item.source_type):
            continue
        pid = int(item.order_id or 0)
        if pid in counted_po_ids:
            continue
        oid = int(item.source_id or 0)
        if oid not in result:
            continue
        _add_po_item_qty(result, oid, int(item.material_id or 0), item.ordered_quantity)
    return result


async def batch_pushed_purchase_qty_by_material(
    tenant_id: int,
    sales_order_ids: List[int],
) -> Dict[int, Dict[int, Decimal]]:
    """order_id → material_id → 已占用数量（SO→PR + SO→PO）。"""
    if not sales_order_ids:
        return {}
    pr_map, po_map = await asyncio.gather(
        batch_pushed_purchase_requisition_qty_by_material(tenant_id, sales_order_ids),
        batch_pushed_purchase_order_qty_by_material(tenant_id, sales_order_ids),
    )
    result: Dict[int, Dict[int, Decimal]] = {int(oid): {} for oid in sales_order_ids}
    for oid in sales_order_ids:
        merged: Dict[int, Decimal] = {}
        for src in (pr_map.get(int(oid)) or {}, po_map.get(int(oid)) or {}):
            for mid, qty in src.items():
                merged[mid] = merged.get(mid, Decimal("0")) + qty
        result[int(oid)] = merged
    return result


def merge_exact_and_material_purchase_occupancy(
    items_by_order: Dict[int, List[Any]],
    exact_occupied: Dict[int, Decimal],
    material_by_order: Dict[int, Dict[int, Decimal]],
) -> Dict[int, Decimal]:
    """行精确占用 + 物料池余量 FIFO 摊到销售明细（不超行订单量）。"""
    occupied: Dict[int, Decimal] = {
        int(lid): Decimal(str(qty or 0)) for lid, qty in (exact_occupied or {}).items()
    }
    for oid, order_items in items_by_order.items():
        order_id = int(oid)
        pool = dict(material_by_order.get(order_id) or {})
        for it in order_items or []:
            lid = int(getattr(it, "id", 0) or 0)
            mid = int(getattr(it, "material_id", 0) or 0)
            already = occupied.get(lid, Decimal("0"))
            if lid <= 0 or mid <= 0 or already <= 0:
                continue
            pool[mid] = max(Decimal("0"), pool.get(mid, Decimal("0")) - already)
        for it in sorted(order_items or [], key=lambda row: int(getattr(row, "id", 0) or 0)):
            lid = int(getattr(it, "id", 0) or 0)
            mid = int(getattr(it, "material_id", 0) or 0)
            line_qty = Decimal(str(getattr(it, "order_quantity", 0) or 0))
            if lid <= 0 or mid <= 0 or line_qty <= 0:
                continue
            already = occupied.get(lid, Decimal("0"))
            room = line_qty - already
            if room <= 0:
                continue
            avail = pool.get(mid, Decimal("0"))
            if avail <= 0:
                continue
            take = min(room, avail)
            occupied[lid] = already + take
            pool[mid] = avail - take
    return occupied


async def batch_pushed_purchase_requisition_qty_by_sales_order_item(
    tenant_id: int,
    items_by_order: Dict[int, List[Any]],
) -> Dict[int, Decimal]:
    """销售明细 → 已下推采购申请占用（物料池 FIFO）。"""
    if not items_by_order:
        return {}
    material_by_order = await batch_pushed_purchase_requisition_qty_by_material(
        tenant_id, list(items_by_order.keys())
    )
    return merge_exact_and_material_purchase_occupancy(
        items_by_order, {}, material_by_order
    )


async def batch_pushed_purchase_order_qty_by_sales_order_item(
    tenant_id: int,
    items_by_order: Dict[int, List[Any]],
) -> Dict[int, Decimal]:
    """销售明细 → 已下推采购订单占用（行 source_id 优先 + 物料池 FIFO）。"""
    if not items_by_order:
        return {}

    item_ids: List[int] = []
    for items in items_by_order.values():
        for it in items or []:
            iid = int(getattr(it, "id", 0) or 0)
            if iid > 0:
                item_ids.append(iid)
    if not item_ids:
        return {}

    from apps.kuaizhizao.models.purchase_order import PurchaseOrder, PurchaseOrderItem

    exact_occupied: Dict[int, Decimal] = {}
    pois = await PurchaseOrderItem.filter(
        tenant_id=tenant_id,
        source_id__in=item_ids,
        deleted_at__isnull=True,
    ).all()
    if pois:
        order_ids = {int(pi.order_id) for pi in pois if pi.order_id}
        live_order_ids = set(
            await PurchaseOrder.filter(
                tenant_id=tenant_id,
                id__in=list(order_ids),
                deleted_at__isnull=True,
            ).values_list("id", flat=True)
        )
        for pi in pois:
            if int(pi.order_id or 0) not in live_order_ids:
                continue
            if not _is_sales_order_source(pi.source_type):
                continue
            sid = int(pi.source_id or 0)
            if sid <= 0 or sid not in set(item_ids):
                continue
            qty = Decimal(str(pi.ordered_quantity or 0))
            if qty <= 0:
                continue
            exact_occupied[sid] = exact_occupied.get(sid, Decimal("0")) + qty

    material_by_order = await batch_pushed_purchase_order_qty_by_material(
        tenant_id, list(items_by_order.keys())
    )
    return merge_exact_and_material_purchase_occupancy(
        items_by_order, exact_occupied, material_by_order
    )


async def batch_pushed_purchase_qty_by_sales_order_item(
    tenant_id: int,
    items_by_order: Dict[int, List[Any]],
    *,
    purchase_track: Optional[str] = None,
) -> Dict[int, Decimal]:
    """sales_order_item.id → 已下推采购占用（主数量，含草稿；删除的采购订单不计）。

    purchase_track：``purchase_requisition`` / ``purchase_order`` 时仅计对应轨；缺省为两轨合计。
    """
    if not items_by_order:
        return {}

    from apps.kuaizhizao.services.sales_order_procurement_mode import (
        PROCUREMENT_MODE_ORDER,
        PROCUREMENT_MODE_REQUISITION,
        normalize_procurement_fulfillment_mode,
    )

    track = normalize_procurement_fulfillment_mode(purchase_track)
    if track == PROCUREMENT_MODE_REQUISITION:
        return await batch_pushed_purchase_requisition_qty_by_sales_order_item(
            tenant_id, items_by_order
        )
    if track == PROCUREMENT_MODE_ORDER:
        return await batch_pushed_purchase_order_qty_by_sales_order_item(
            tenant_id, items_by_order
        )

    pr_map, po_map = await asyncio.gather(
        batch_pushed_purchase_requisition_qty_by_sales_order_item(tenant_id, items_by_order),
        batch_pushed_purchase_order_qty_by_sales_order_item(tenant_id, items_by_order),
    )
    merged: Dict[int, Decimal] = {}
    keys = set(pr_map.keys()) | set(po_map.keys())
    for lid in keys:
        merged[lid] = pr_map.get(lid, Decimal("0")) + po_map.get(lid, Decimal("0"))
    return merged


def material_is_buy_eligible(material: Any) -> bool:
    return SOURCE_TYPE_BUY in material_source_types_set(material)


def material_is_production_eligible(material: Any) -> bool:
    types = material_source_types_set(material)
    return SOURCE_TYPE_MAKE in types or SOURCE_TYPE_OUTSOURCE in types


def _order_qty_by_material(items: List[Any]) -> Dict[int, Decimal]:
    totals: Dict[int, Decimal] = {}
    for it in items or []:
        mid = int(getattr(it, "material_id", 0) or 0)
        if mid <= 0:
            continue
        totals[mid] = totals.get(mid, Decimal("0")) + Decimal(
            str(getattr(it, "order_quantity", 0) or 0)
        )
    return totals


async def batch_pushed_work_order_qty_by_sales_order_item(
    tenant_id: int,
    items_by_order: Dict[int, List[Any]],
) -> Dict[int, Decimal]:
    """
    sales_order_item.id → 已下推工单主数量（排除已取消工单）。

    优先认工单 ``sales_order_item_id``；历史工单无行指针时按物料池 FIFO 分摊（行 id 升序）。
    """
    if not items_by_order:
        return {}

    from apps.kuaizhizao.models.work_order import WorkOrder

    order_ids = [int(oid) for oid in items_by_order.keys() if oid]
    occupied: Dict[int, Decimal] = {}
    legacy_wo_by_order_material: Dict[int, Dict[int, Decimal]] = {oid: {} for oid in order_ids}
    if order_ids:
        rows = await WorkOrder.filter(
            tenant_id=tenant_id,
            sales_order_id__in=order_ids,
            deleted_at__isnull=True,
        ).exclude(status__in=["cancelled", "CANCELLED", "已取消"]).values_list(
            "sales_order_id", "sales_order_item_id", "product_id", "quantity"
        )
        for so_id, so_item_id, product_id, qty in rows:
            oid = int(so_id or 0)
            lid = int(so_item_id or 0)
            mid = int(product_id or 0)
            q = Decimal(str(qty or 0))
            if q <= 0 or oid not in legacy_wo_by_order_material:
                continue
            if lid > 0:
                occupied[lid] = occupied.get(lid, Decimal("0")) + q
            elif mid > 0:
                bucket = legacy_wo_by_order_material.setdefault(oid, {})
                bucket[mid] = bucket.get(mid, Decimal("0")) + q

    for oid, order_items in items_by_order.items():
        order_id = int(oid)
        wo_pool = dict(legacy_wo_by_order_material.get(order_id) or {})
        for it in sorted(order_items, key=lambda row: int(getattr(row, "id", 0) or 0)):
            lid = int(getattr(it, "id", 0) or 0)
            if lid <= 0:
                continue
            if lid in occupied:
                continue
            mid = int(getattr(it, "material_id", 0) or 0)
            line_qty = Decimal(str(getattr(it, "order_quantity", 0) or 0))
            if line_qty <= 0:
                occupied[lid] = Decimal("0")
                continue
            pool = wo_pool.get(mid, Decimal("0"))
            take = min(line_qty, pool) if pool > 0 else Decimal("0")
            occupied[lid] = take
            if mid > 0 and take > 0:
                wo_pool[mid] = pool - take
    return occupied


async def batch_pushed_work_order_qty_by_material(
    tenant_id: int,
    items_by_order: Dict[int, List[Any]],
) -> Dict[int, Dict[int, Decimal]]:
    """order_id → material_id → 已下推工单数量（排除已取消）。"""
    order_ids = [int(oid) for oid in items_by_order.keys() if oid]
    result: Dict[int, Dict[int, Decimal]] = {oid: {} for oid in order_ids}
    if not order_ids:
        return result

    from apps.kuaizhizao.models.work_order import WorkOrder

    rows = await WorkOrder.filter(
        tenant_id=tenant_id,
        sales_order_id__in=order_ids,
        deleted_at__isnull=True,
    ).exclude(status__in=["cancelled", "CANCELLED", "已取消"]).values_list(
        "sales_order_id", "product_id", "quantity"
    )
    for so_id, product_id, qty in rows:
        oid = int(so_id or 0)
        mid = int(product_id or 0)
        if oid not in result or mid <= 0:
            continue
        bucket = result.setdefault(oid, {})
        bucket[mid] = bucket.get(mid, Decimal("0")) + Decimal(str(qty or 0))
    return result


async def batch_remaining_fulfillable_qty_by_material(
    tenant_id: int,
    items_by_order: Dict[int, List[Any]],
) -> Dict[int, Dict[int, Decimal]]:
    """order_id → material_id → 共享余量 max(0, 订单量 - 已下推工单 - 已下推采购)。"""
    if not items_by_order:
        return {}

    pushed_purchase, pushed_wo = await asyncio.gather(
        batch_pushed_purchase_qty_by_material(tenant_id, list(items_by_order.keys())),
        batch_pushed_work_order_qty_by_material(tenant_id, items_by_order),
    )
    out: Dict[int, Dict[int, Decimal]] = {}
    for oid, items in items_by_order.items():
        order_id = int(oid)
        totals = _order_qty_by_material(items)
        wo_for = pushed_wo.get(order_id) or {}
        pr_for = pushed_purchase.get(order_id) or {}
        bucket: Dict[int, Decimal] = {}
        for mid, total_qty in totals.items():
            remaining = total_qty - wo_for.get(mid, Decimal("0")) - pr_for.get(mid, Decimal("0"))
            if remaining > 0:
                bucket[mid] = remaining
        out[order_id] = bucket
    return out


async def batch_remaining_fulfillable_qty_by_material_for_track(
    tenant_id: int,
    items_by_order: Dict[int, List[Any]],
    *,
    purchase_track: str,
) -> Dict[int, Dict[int, Decimal]]:
    """取单余量：工单占用 + 指定采购轨占用。"""
    from apps.kuaizhizao.services.sales_order_procurement_mode import (
        PROCUREMENT_MODE_ORDER,
        PROCUREMENT_MODE_REQUISITION,
        normalize_procurement_fulfillment_mode,
    )

    track = normalize_procurement_fulfillment_mode(purchase_track)
    if track not in (PROCUREMENT_MODE_REQUISITION, PROCUREMENT_MODE_ORDER):
        return await batch_remaining_fulfillable_qty_by_material(tenant_id, items_by_order)

    purchase_fn = (
        batch_pushed_purchase_requisition_qty_by_material
        if track == PROCUREMENT_MODE_REQUISITION
        else batch_pushed_purchase_order_qty_by_material
    )
    pushed_purchase, pushed_wo = await asyncio.gather(
        purchase_fn(tenant_id, list(items_by_order.keys())),
        batch_pushed_work_order_qty_by_material(tenant_id, items_by_order),
    )
    out: Dict[int, Dict[int, Decimal]] = {}
    for oid, items in items_by_order.items():
        order_id = int(oid)
        totals = _order_qty_by_material(items)
        wo_for = pushed_wo.get(order_id) or {}
        pr_for = pushed_purchase.get(order_id) or {}
        bucket: Dict[int, Decimal] = {}
        for mid, total_qty in totals.items():
            remaining = total_qty - wo_for.get(mid, Decimal("0")) - pr_for.get(mid, Decimal("0"))
            if remaining > 0:
                bucket[mid] = remaining
        out[order_id] = bucket
    return out


async def batch_sales_order_fulfillment_push_summary(
    tenant_id: int,
    orders: List[Any],
    items_by_order: Dict[int, List[Any]],
) -> Dict[int, Dict[str, Any]]:
    """列表采产下推进度：按锁定采购轨 + 工单轨合计。"""
    from apps.kuaizhizao.services.sales_order_procurement_mode import (
        PROCUREMENT_MODE_ORDER,
        PROCUREMENT_MODE_REQUISITION,
        batch_resolve_procurement_fulfillment_mode,
        list_sales_order_purchase_downstream_codes,
    )

    if not orders:
        return {}
    order_ids = [int(getattr(o, "id", 0) or 0) for o in orders]
    mode_map = await batch_resolve_procurement_fulfillment_mode(tenant_id, orders)
    material_by_id = await _load_materials_for_items(tenant_id, items_by_order)
    codes_pr, codes_po = await asyncio.gather(
        list_sales_order_purchase_downstream_codes(
            tenant_id, order_ids, PROCUREMENT_MODE_REQUISITION
        ),
        list_sales_order_purchase_downstream_codes(
            tenant_id, order_ids, PROCUREMENT_MODE_ORDER
        ),
    )
    items_subset_pr: Dict[int, List[Any]] = {}
    items_subset_po: Dict[int, List[Any]] = {}
    buy_eligible_qty: Dict[int, Decimal] = {oid: Decimal("0") for oid in order_ids}
    make_eligible_qty: Dict[int, Decimal] = {oid: Decimal("0") for oid in order_ids}
    for oid, items in items_by_order.items():
        order_id = int(oid)
        pr_list: List[Any] = []
        po_list: List[Any] = []
        mode = mode_map.get(order_id)
        for it in items or []:
            mid = int(getattr(it, "material_id", 0) or 0)
            m = material_by_id.get(mid)
            if not m:
                continue
            qty = Decimal(str(getattr(it, "order_quantity", 0) or 0))
            if qty <= 0:
                continue
            if material_is_buy_eligible(m):
                buy_eligible_qty[order_id] = buy_eligible_qty.get(order_id, Decimal("0")) + qty
                if mode == PROCUREMENT_MODE_ORDER:
                    po_list.append(it)
                else:
                    pr_list.append(it)
            if material_is_production_eligible(m):
                make_eligible_qty[order_id] = make_eligible_qty.get(order_id, Decimal("0")) + qty
        if pr_list:
            items_subset_pr[order_id] = pr_list
        if po_list:
            items_subset_po[order_id] = po_list

    pushed_wo = await batch_pushed_work_order_qty_by_sales_order_item(
        tenant_id, items_by_order
    )
    pushed_pr = (
        await batch_pushed_purchase_requisition_qty_by_sales_order_item(
            tenant_id, items_subset_pr
        )
        if items_subset_pr
        else {}
    )
    pushed_po = (
        await batch_pushed_purchase_order_qty_by_sales_order_item(
            tenant_id, items_subset_po
        )
        if items_subset_po
        else {}
    )

    out: Dict[int, Dict[str, Any]] = {}
    for order in orders:
        oid = int(order.id)
        mode = mode_map.get(oid)
        purchase_pushed = Decimal("0")
        if mode == PROCUREMENT_MODE_ORDER:
            for it in items_subset_po.get(oid) or []:
                lid = int(getattr(it, "id", 0) or 0)
                purchase_pushed += pushed_po.get(lid, Decimal("0"))
            purchase_codes = list(codes_po.get(oid) or [])
        else:
            for it in items_subset_pr.get(oid) or []:
                lid = int(getattr(it, "id", 0) or 0)
                purchase_pushed += pushed_pr.get(lid, Decimal("0"))
            purchase_codes = list(codes_pr.get(oid) or [])
        wo_pushed = Decimal("0")
        for it in items_by_order.get(oid) or []:
            lid = int(getattr(it, "id", 0) or 0)
            m = material_by_id.get(int(getattr(it, "material_id", 0) or 0))
            if m and material_is_production_eligible(m):
                wo_pushed += pushed_wo.get(lid, Decimal("0"))

        buy_total = buy_eligible_qty.get(oid, Decimal("0"))
        make_total = make_eligible_qty.get(oid, Decimal("0"))
        eligible = buy_total + make_total
        pushed_total = purchase_pushed + wo_pushed
        if buy_total > 0:
            purchase_ratio = float(
                min(Decimal("100"), (purchase_pushed / buy_total) * Decimal("100"))
            )
        else:
            purchase_ratio = 0.0
        if make_total > 0:
            wo_ratio = float(min(Decimal("100"), (wo_pushed / make_total) * Decimal("100")))
        else:
            wo_ratio = 0.0
        if eligible > 0:
            fulfillment_ratio = float(
                min(Decimal("100"), (pushed_total / eligible) * Decimal("100"))
            )
        else:
            fulfillment_ratio = 0.0

        out[oid] = {
            "procurement_fulfillment_mode": mode,
            "purchase_push_progress": round(purchase_ratio, 1),
            "pushed_purchase_quantity": purchase_pushed,
            "pushed_purchase_codes": purchase_codes,
            "fulfillment_push_progress": round(fulfillment_ratio, 1),
            "work_order_push_progress_refined": round(wo_ratio, 1),
        }
    return out


async def _load_materials_for_items(
    tenant_id: int,
    items_by_order: Dict[int, List[Any]],
) -> Dict[int, Any]:
    from apps.master_data.models.material import Material

    all_mids: set[int] = set()
    for items in items_by_order.values():
        for it in items or []:
            mid = int(getattr(it, "material_id", 0) or 0)
            if mid > 0:
                all_mids.add(mid)
    if not all_mids:
        return {}
    mats = await Material.filter(
        tenant_id=tenant_id, id__in=list(all_mids), deleted_at__isnull=True
    ).all()
    return {int(m.id): m for m in mats}


async def batch_has_purchasable_remaining(
    tenant_id: int,
    items_by_order: Dict[int, List[Any]],
) -> Dict[int, bool]:
    if not items_by_order:
        return {}
    material_by_id, fulfill_by_order = await asyncio.gather(
        _load_materials_for_items(tenant_id, items_by_order),
        batch_remaining_fulfillable_qty_by_material(tenant_id, items_by_order),
    )
    buy_ids = {
        mid for mid, m in material_by_id.items() if material_is_buy_eligible(m)
    }
    out: Dict[int, bool] = {}
    for oid in items_by_order.keys():
        order_id = int(oid)
        fulfill = fulfill_by_order.get(order_id) or {}
        out[order_id] = any(
            mid in buy_ids and qty > 0 for mid, qty in fulfill.items()
        )
    return out


async def batch_has_production_fulfillable_remaining(
    tenant_id: int,
    items_by_order: Dict[int, List[Any]],
) -> Dict[int, bool]:
    if not items_by_order:
        return {}
    material_by_id, fulfill_by_order = await asyncio.gather(
        _load_materials_for_items(tenant_id, items_by_order),
        batch_remaining_fulfillable_qty_by_material(tenant_id, items_by_order),
    )
    prod_ids = {
        mid for mid, m in material_by_id.items() if material_is_production_eligible(m)
    }
    out: Dict[int, bool] = {}
    for oid in items_by_order.keys():
        order_id = int(oid)
        fulfill = fulfill_by_order.get(order_id) or {}
        out[order_id] = any(
            mid in prod_ids and qty > 0 for mid, qty in fulfill.items()
        )
    return out


async def collect_sales_order_buy_push_lines(
    tenant_id: int,
    sales_order_id: int,
    items: List[Any],
    *,
    selected_item_ids: Optional[List[int]] = None,
    selected_quantities: Optional[Dict[int, Decimal]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[int, Decimal]]:
    """返回可下推行与 material 占用映射。"""
    from apps.master_data.models.material import Material

    selected: Optional[set[int]] = None
    if selected_item_ids is not None:
        selected = {int(x) for x in selected_item_ids if x is not None}

    material_ids = sorted(
        {
            int(getattr(it, "material_id", 0) or 0)
            for it in items
            if int(getattr(it, "material_id", 0) or 0) > 0
        }
    )
    materials = (
        await Material.filter(
            tenant_id=tenant_id, id__in=material_ids, deleted_at__isnull=True
        ).all()
        if material_ids
        else []
    )
    material_by_id = {int(m.id): m for m in materials}
    buy_ids = {
        mid for mid, m in material_by_id.items() if material_is_buy_eligible(m)
    }

    fulfill_map = await batch_remaining_fulfillable_qty_by_material(
        tenant_id, {sales_order_id: items}
    )
    fulfill_by_material = fulfill_map.get(sales_order_id) or {}
    pushed_map = await batch_pushed_purchase_qty_by_material(tenant_id, [sales_order_id])
    pushed_by_material = pushed_map.get(sales_order_id) or {}
    items_map = {sales_order_id: items}
    pushed_by_item, wo_by_item = await asyncio.gather(
        batch_pushed_purchase_qty_by_sales_order_item(tenant_id, items_map),
        batch_pushed_work_order_qty_by_sales_order_item(tenant_id, items_map),
    )

    remaining_cursor: Dict[int, Decimal] = {
        mid: qty for mid, qty in fulfill_by_material.items() if mid in buy_ids
    }

    lines: List[Dict[str, Any]] = []
    for it in items:
        item_id = int(getattr(it, "id", 0) or 0)
        mid = int(getattr(it, "material_id", 0) or 0)
        if mid not in buy_ids:
            continue
        if selected is not None and item_id not in selected:
            continue
        qty = Decimal(str(getattr(it, "order_quantity", 0) or 0))
        if qty <= 0:
            continue
        item_purchase = pushed_by_item.get(item_id, Decimal("0"))
        item_wo = wo_by_item.get(item_id, Decimal("0"))
        item_fulfilled = item_purchase + item_wo
        line_rem = max(Decimal("0"), qty - item_fulfilled)
        material_rem = remaining_cursor.get(mid, Decimal("0"))
        max_qty = min(line_rem, material_rem) if line_rem > 0 and material_rem > 0 else Decimal("0")
        if selected_quantities and item_id in selected_quantities:
            override = Decimal(str(selected_quantities[item_id]))
            if override < 0:
                override = Decimal("0")
            max_qty = min(max_qty, override)
        if max_qty <= 0:
            continue
        remaining_cursor[mid] = material_rem - max_qty
        material = material_by_id.get(mid)
        from apps.kuaizhizao.utils.material_source_helper import (
            resolve_default_supplier_id_from_material,
            resolve_default_supplier_name_from_material,
        )

        supplier_id = resolve_default_supplier_id_from_material(material)
        supplier_name = resolve_default_supplier_name_from_material(material) or ""
        unit_price = Decimal("0")
        if material and supplier_id:
            from apps.master_data.services.partner_material_price_resolver import (
                PartnerMaterialPriceResolver,
            )

            resolved = await PartnerMaterialPriceResolver.resolve(
                tenant_id,
                "purchase",
                int(supplier_id),
                mid,
                quantity=max_qty,
            )
            if resolved.found and resolved.unit_price > 0:
                unit_price = resolved.unit_price
        elif material:
            from apps.kuaizhizao.utils.material_source_helper import (
                resolve_material_purchase_line_unit_price,
            )

            unit_price = resolve_material_purchase_line_unit_price(material=material)
        lines.append(
            {
                "item_id": item_id,
                "material_id": mid,
                "material_code": str(
                    getattr(it, "material_code", None)
                    or (material.main_code if material else None)
                    or (material.code if material else None)
                    or mid
                ),
                "material_name": str(
                    getattr(it, "material_name", None)
                    or (material.name if material else None)
                    or ""
                ),
                "material_spec": getattr(it, "material_spec", None)
                or (getattr(material, "specification", None) if material else None),
                "unit": str(
                    getattr(it, "material_unit", None)
                    or (material.base_unit if material else None)
                    or "件"
                ),
                "quantity": qty,
                "pushed_quantity": item_fulfilled,
                "pushed_work_order_quantity": item_wo,
                "pushed_purchase_quantity": item_purchase,
                "max_push_quantity": max_qty,
                "required_date": getattr(it, "delivery_date", None),
                "supplier_id": int(supplier_id) if supplier_id else None,
                "supplier_name": str(supplier_name or ""),
                "suggested_unit_price": unit_price or Decimal("0"),
                "material": material,
            }
        )
    return lines, pushed_by_material


async def preview_push_to_purchase_requisition(
    *,
    tenant_id: int,
    order: Any,
    items: List[Any],
) -> Dict[str, Any]:
    lines, _ = await collect_sales_order_buy_push_lines(tenant_id, int(order.id), items)
    preview_items = [
        {
            "item_id": row["item_id"],
            "material_id": row["material_id"],
            "material_code": row["material_code"],
            "material_name": row["material_name"],
            "material_spec": row["material_spec"],
            "unit": row["unit"],
            "quantity": float(row["quantity"]),
            "pushed_quantity": float(row["pushed_quantity"]),
            "max_push_quantity": float(row["max_push_quantity"]),
            "required_date": str(row["required_date"]) if row["required_date"] else None,
            "supplier_id": row["supplier_id"],
            "suggested_unit_price": float(row["suggested_unit_price"] or 0),
        }
        for row in lines
    ]
    pushable = len(preview_items)
    has_blocking = pushable == 0
    return {
        "target_type": "purchase_requisition",
        "sales_order_id": int(order.id),
        "sales_order_code": order.order_code,
        "summary": (
            f"将按销售明细采购件生成采购申请，共 {pushable} 行可下推"
            if not has_blocking
            else "销售订单无可下推采购件"
        ),
        "items": preview_items,
        "has_blocking_issues": has_blocking,
        "blocking_reason": (
            "sales_order.push_purchase_requisition.no_buy_items" if has_blocking else None
        ),
        "tip": "按销售订单数量下推，不做库存抵扣；已通过本单下推采购申请/采购订单的数量不会重复纳入。",
    }


async def build_purchase_requisition_create_from_sales_order(
    *,
    tenant_id: int,
    order: Any,
    items: List[Any],
    selected_item_ids: Optional[List[int]] = None,
    selected_quantities: Optional[Dict[int, Decimal]] = None,
):
    from apps.kuaizhizao.schemas.purchase_requisition import (
        PurchaseRequisitionCreate,
        PurchaseRequisitionItemCreate,
    )

    lines, _ = await collect_sales_order_buy_push_lines(
        tenant_id,
        int(order.id),
        items,
        selected_item_ids=selected_item_ids,
        selected_quantities=selected_quantities,
    )
    if not lines:
        raise BusinessLogicError("销售订单无可下推采购件，无法生成采购申请")

    today = to_site_date(resolve_business_datetime())
    req_items: List[PurchaseRequisitionItemCreate] = []
    required_dates = []
    for row in lines:
        req_date = row["required_date"] or today
        required_dates.append(req_date)
        req_items.append(
            PurchaseRequisitionItemCreate(
                material_id=row["material_id"],
                material_code=row["material_code"],
                material_name=row["material_name"],
                material_spec=row["material_spec"],
                unit=row["unit"],
                quantity=row["max_push_quantity"],
                suggested_unit_price=row["suggested_unit_price"] or Decimal(0),
                required_date=req_date,
                supplier_id=row["supplier_id"],
                notes=f"销售订单 {order.order_code} 明细#{row['item_id']} 直推请购",
            )
        )

    return PurchaseRequisitionCreate(
        requisition_code="",
        requisition_name=f"销售订单{order.order_code}请购",
        requisition_date=today,
        required_date=min(required_dates) if required_dates else today,
        source_type="sales_order",
        source_id=int(order.id),
        source_code=order.order_code,
        notes=f"由销售订单 {order.order_code} 直推生成（按单外购，未做库存抵扣）",
        items=req_items,
    )


async def draft_purchase_requisition_from_sales_order(
    *,
    tenant_id: int,
    order: Any,
    items: List[Any],
    selected_item_ids: Optional[List[int]] = None,
    selected_quantities: Optional[Dict[int, Decimal]] = None,
) -> Dict[str, Any]:
    req_data = await build_purchase_requisition_create_from_sales_order(
        tenant_id=tenant_id,
        order=order,
        items=items,
        selected_item_ids=selected_item_ids,
        selected_quantities=selected_quantities,
    )
    return {
        "target_type": "purchase_requisition",
        "source_type": "sales_order",
        "source_id": int(order.id),
        "source_code": order.order_code,
        "create_payload": req_data.model_dump(by_alias=True, mode="json"),
        "document_flow": {
            "documentFlowSourceType": "sales_order_buy_push",
            "documentFlowSalesOrderId": int(order.id),
        },
    }


async def finalize_sales_order_after_requisition_created(
    *,
    tenant_id: int,
    sales_order_id: int,
    requisition_id: int,
    requisition_code: str,
    requisition_name: Optional[str],
    created_by: int,
) -> None:
    from apps.kuaizhizao.models.sales_order import SalesOrder
    from apps.kuaizhizao.schemas.document_relation import DocumentRelationCreate
    from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService

    order = await SalesOrder.get_or_none(
        tenant_id=tenant_id, id=sales_order_id, deleted_at__isnull=True
    )
    if not order:
        return
    from apps.kuaizhizao.services.sales_order_procurement_mode import (
        PROCUREMENT_MODE_REQUISITION,
        lock_procurement_fulfillment_mode,
    )

    try:
        await DocumentRelationNewService().create_relation(
            tenant_id=tenant_id,
            relation_data=DocumentRelationCreate(
                source_type="sales_order",
                source_id=int(order.id),
                source_code=order.order_code,
                source_name=getattr(order, "order_name", None) or order.order_code,
                target_type="purchase_requisition",
                target_id=requisition_id,
                target_code=requisition_code,
                target_name=requisition_name,
                relation_type="source",
                relation_mode="push",
                relation_desc="销售订单直推采购申请",
            ),
            created_by=created_by,
        )
    except Exception as exc:
        logger.warning("建立销售订单→采购申请关联失败: %s", exc)
    await lock_procurement_fulfillment_mode(
        tenant_id, int(order.id), PROCUREMENT_MODE_REQUISITION
    )


async def push_to_purchase_requisition(
    *,
    tenant_id: int,
    order: Any,
    items: List[Any],
    created_by: int,
    selected_item_ids: Optional[List[int]] = None,
    selected_quantities: Optional[Dict[int, Decimal]] = None,
) -> Dict[str, Any]:
    from apps.kuaizhizao.services.purchase_requisition_service import PurchaseRequisitionService
    from apps.kuaizhizao.services.sales_order_procurement_mode import (
        PROCUREMENT_MODE_REQUISITION,
        assert_procurement_mode_allows_push,
    )

    await assert_procurement_mode_allows_push(
        tenant_id, order, PROCUREMENT_MODE_REQUISITION
    )

    req_data = await build_purchase_requisition_create_from_sales_order(
        tenant_id=tenant_id,
        order=order,
        items=items,
        selected_item_ids=selected_item_ids,
        selected_quantities=selected_quantities,
    )

    req = await PurchaseRequisitionService().create_requisition(
        tenant_id=tenant_id,
        data=req_data,
        created_by=created_by,
    )

    await finalize_sales_order_after_requisition_created(
        tenant_id=tenant_id,
        sales_order_id=int(order.id),
        requisition_id=int(req.id),
        requisition_code=req.requisition_code,
        requisition_name=req.requisition_name,
        created_by=created_by,
    )

    return {
        "success": True,
        "message": "下推成功，已生成采购申请",
        "target_document": {
            "type": "purchase_requisition",
            "id": req.id,
            "code": req.requisition_code,
        },
    }


async def preview_push_to_purchase_order(
    *,
    tenant_id: int,
    order: Any,
    items: List[Any],
) -> Dict[str, Any]:
    if await require_purchase_requisition_for_tenant(tenant_id):
        return {
            "target_type": "purchase_order",
            "sales_order_id": int(order.id),
            "sales_order_code": order.order_code,
            "summary": "当前组织要求先采购申请后下单",
            "items": [],
            "has_blocking_issues": True,
            "blocking_reason": "sales_order.push_purchase_order.require_requisition",
            "tip": "请改用「从销售订单创建采购申请」。",
        }

    lines, _ = await collect_sales_order_buy_push_lines(tenant_id, int(order.id), items)
    preview_items = []
    has_blocking = False
    for row in lines:
        issues = []
        if not row["supplier_id"]:
            issues.append("缺少默认供应商，将生成待定供应商草稿单")
        preview_items.append(
            {
                "item_id": row["item_id"],
                "material_id": row["material_id"],
                "material_code": row["material_code"],
                "material_name": row["material_name"],
                "material_spec": row["material_spec"],
                "unit": row["unit"],
                "quantity": float(row["quantity"]),
                "pushed_quantity": float(row["pushed_quantity"]),
                "max_push_quantity": float(row["max_push_quantity"]),
                "required_date": str(row["required_date"]) if row["required_date"] else None,
                "supplier_id": row["supplier_id"],
                "supplier_name": row["supplier_name"],
                "suggested_unit_price": float(row["suggested_unit_price"] or 0),
                "issues": issues,
            }
        )
    pushable = len(preview_items)
    if pushable == 0:
        has_blocking = True
    return {
        "target_type": "purchase_order",
        "sales_order_id": int(order.id),
        "sales_order_code": order.order_code,
        "summary": (
            f"将按供应商分组生成采购订单，共 {pushable} 行可下推"
            if not has_blocking
            else "销售订单无可下推采购件"
        ),
        "items": preview_items,
        "has_blocking_issues": has_blocking,
        "blocking_reason": (
            "sales_order.push_purchase_order.no_buy_items" if has_blocking else None
        ),
        "tip": "按销售订单数量下推，不做库存净需求；无默认供应商的行将归入「待定供应商」草稿单。",
    }


async def plan_purchase_orders_from_sales_order(
    *,
    tenant_id: int,
    order: Any,
    items: List[Any],
    selected_item_ids: Optional[List[int]] = None,
    selected_quantities: Optional[Dict[int, Decimal]] = None,
) -> List[Any]:
    from apps.kuaizhizao.constants import DocumentStatus
    from apps.kuaizhizao.schemas.purchase import PurchaseOrderCreate, PurchaseOrderItemCreate
    from apps.kuaizhizao.utils.sales_order_currency_carry import currency_fields_for_purchase_doc
    from apps.master_data.models.supplier import Supplier

    if await require_purchase_requisition_for_tenant(tenant_id):
        raise BusinessLogicError("当前组织要求先采购申请后下单，请下推采购申请")

    so_currency = currency_fields_for_purchase_doc(order)

    lines, _ = await collect_sales_order_buy_push_lines(
        tenant_id,
        int(order.id),
        items,
        selected_item_ids=selected_item_ids,
        selected_quantities=selected_quantities,
    )
    if not lines:
        raise BusinessLogicError("销售订单无可下推采购件，无法生成采购订单")

    today = to_site_date(resolve_business_datetime())
    by_supplier: Dict[int, List[Dict[str, Any]]] = {}
    for row in lines:
        sid = int(row["supplier_id"] or 0)
        by_supplier.setdefault(sid, []).append(row)

    plans: List[PurchaseOrderCreate] = []
    for supplier_id, group in by_supplier.items():
        supplier_name = "待定供应商"
        if supplier_id > 0:
            supplier = await Supplier.get_or_none(tenant_id=tenant_id, id=supplier_id)
            if supplier:
                supplier_name = supplier.name
            else:
                supplier_name = group[0].get("supplier_name") or f"供应商({supplier_id})"
        elif group[0].get("supplier_name"):
            supplier_name = str(group[0]["supplier_name"])

        po_items: List[PurchaseOrderItemCreate] = []
        required_dates = []
        for row in group:
            qty = row["max_push_quantity"]
            unit_price = row["suggested_unit_price"] or Decimal(0)
            req_date = row["required_date"] or today
            required_dates.append(req_date)
            po_items.append(
                PurchaseOrderItemCreate(
                    material_id=row["material_id"],
                    material_code=row["material_code"],
                    material_name=row["material_name"],
                    material_spec=row["material_spec"],
                    ordered_quantity=qty,
                    unit=row["unit"],
                    unit_price=unit_price,
                    total_price=qty * unit_price,
                    received_quantity=Decimal(0),
                    outstanding_quantity=qty,
                    required_date=req_date,
                    source_type="sales_order",
                    source_id=int(order.id),
                    notes=f"销售订单 {order.order_code} 明细#{row['item_id']} 直推采购",
                )
            )

        plans.append(
            PurchaseOrderCreate(
                supplier_id=supplier_id if supplier_id > 0 else 0,
                supplier_name=supplier_name,
                order_date=today,
                delivery_date=min(required_dates) if required_dates else today,
                order_type="标准采购",
                status=DocumentStatus.DRAFT.value,
                currency=so_currency["currency"],
                exchange_rate=so_currency["exchange_rate"],
                source_type="sales_order",
                source_id=int(order.id),
                notes=f"由销售订单 {order.order_code} 直推生成（按单外购，未做库存抵扣）",
                items=po_items,
            )
        )
    return plans


async def draft_purchase_orders_from_sales_order(
    *,
    tenant_id: int,
    order: Any,
    items: List[Any],
    selected_item_ids: Optional[List[int]] = None,
    selected_quantities: Optional[Dict[int, Decimal]] = None,
) -> Dict[str, Any]:
    plans = await plan_purchase_orders_from_sales_order(
        tenant_id=tenant_id,
        order=order,
        items=items,
        selected_item_ids=selected_item_ids,
        selected_quantities=selected_quantities,
    )
    drafts = []
    for po_create in plans:
        drafts.append(
            {
                "create_payload": po_create.model_dump(by_alias=True, mode="json"),
                "document_flow": {
                    "documentFlowSourceType": "sales_order_buy_push",
                    "documentFlowSalesOrderId": int(order.id),
                },
                "supplier_id": int(po_create.supplier_id or 0),
            }
        )
    return {
        "target_type": "purchase_order",
        "source_type": "sales_order",
        "source_id": int(order.id),
        "source_code": order.order_code,
        "drafts": drafts,
    }


async def finalize_sales_order_after_purchase_order_created(
    *,
    tenant_id: int,
    sales_order_id: int,
    purchase_order_id: int,
    purchase_order_code: str,
    created_by: int,
) -> None:
    from apps.kuaizhizao.models.sales_order import SalesOrder
    from apps.kuaizhizao.schemas.document_relation import DocumentRelationCreate
    from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService

    order = await SalesOrder.get_or_none(
        tenant_id=tenant_id, id=sales_order_id, deleted_at__isnull=True
    )
    if not order:
        return
    from apps.kuaizhizao.services.sales_order_procurement_mode import (
        PROCUREMENT_MODE_ORDER,
        lock_procurement_fulfillment_mode,
    )

    try:
        await DocumentRelationNewService().create_relation(
            tenant_id=tenant_id,
            relation_data=DocumentRelationCreate(
                source_type="sales_order",
                source_id=int(order.id),
                source_code=order.order_code,
                source_name=getattr(order, "order_name", None) or order.order_code,
                target_type="purchase_order",
                target_id=purchase_order_id,
                target_code=purchase_order_code,
                target_name=purchase_order_code,
                relation_type="source",
                relation_mode="push",
                relation_desc="销售订单直推采购订单",
            ),
            created_by=created_by,
        )
    except Exception as exc:
        logger.warning("建立销售订单→采购订单关联失败: %s", exc)
    await lock_procurement_fulfillment_mode(
        tenant_id, int(order.id), PROCUREMENT_MODE_ORDER
    )


async def push_to_purchase_order(
    *,
    tenant_id: int,
    order: Any,
    items: List[Any],
    created_by: int,
    selected_item_ids: Optional[List[int]] = None,
    selected_quantities: Optional[Dict[int, Decimal]] = None,
) -> Dict[str, Any]:
    from apps.kuaizhizao.services.purchase_service import PurchaseService
    from apps.kuaizhizao.services.sales_order_procurement_mode import (
        PROCUREMENT_MODE_ORDER,
        assert_procurement_mode_allows_push,
    )

    await assert_procurement_mode_allows_push(tenant_id, order, PROCUREMENT_MODE_ORDER)

    plans = await plan_purchase_orders_from_sales_order(
        tenant_id=tenant_id,
        order=order,
        items=items,
        selected_item_ids=selected_item_ids,
        selected_quantities=selected_quantities,
    )

    purchase_service = PurchaseService()
    target_documents: List[Dict[str, Any]] = []

    for po_create in plans:
        po = await purchase_service.create_purchase_order(
            tenant_id=tenant_id,
            order_data=po_create,
            created_by=created_by,
        )
        target_documents.append(
            {"type": "purchase_order", "id": po.id, "code": po.order_code}
        )
        await finalize_sales_order_after_purchase_order_created(
            tenant_id=tenant_id,
            sales_order_id=int(order.id),
            purchase_order_id=int(po.id),
            purchase_order_code=po.order_code,
            created_by=created_by,
        )

    return {
        "success": True,
        "message": f"下推成功，共生成 {len(target_documents)} 张采购订单",
        "target_documents": target_documents,
    }


def _purchase_pull_audited_status_values() -> Tuple[str, ...]:
    from apps.kuaizhizao.constants import LEGACY_AUDITED_VALUES, DemandStatus

    return tuple(
        dict.fromkeys(
            (
                *LEGACY_AUDITED_VALUES,
                DemandStatus.AUDITED.value,
                DemandStatus.CONFIRMED.value,
            )
        )
    )


async def _list_sales_order_buy_pull_lines(
    tenant_id: int,
    *,
    skip: int = 0,
    limit: int = 20,
    keyword: Optional[str] = None,
    sales_order_id: Optional[int] = None,
    pullable_only: bool = True,
    block_when_require_pr: bool,
    purchase_pull_track: Optional[str] = None,
) -> Dict[str, Any]:
    """开口销售订单外购行（采购订单/采购申请取单共用）。

    block_when_require_pr=True 时组织强制先请购则返回空（采购订单直连取单）。
    """
    if block_when_require_pr and await require_purchase_requisition_for_tenant(tenant_id):
        return {"data": [], "total": 0}

    from apps.kuaizhizao.models.sales_order import SalesOrder
    from apps.kuaizhizao.models.sales_order_item import SalesOrderItem
    from apps.kuaizhizao.utils.material_source_helper import (
        resolve_default_supplier_id_from_material,
        resolve_default_supplier_name_from_material,
    )
    from apps.kuaizhizao.utils.pull_open_line_quantity import enrich_pull_line_from_source_item

    so_query = SalesOrder.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        status__in=list(_purchase_pull_audited_status_values()),
    )
    if sales_order_id is not None:
        so_query = so_query.filter(id=int(sales_order_id))
    orders = await so_query.only(
        "id", "order_code", "status", "customer_name", "order_date"
    )
    if not orders:
        return {"data": [], "total": 0}

    from apps.kuaizhizao.services.sales_order_procurement_mode import (
        PROCUREMENT_MODE_ORDER,
        PROCUREMENT_MODE_REQUISITION,
        batch_resolve_procurement_fulfillment_mode,
        normalize_procurement_fulfillment_mode,
    )

    mode_by_order = await batch_resolve_procurement_fulfillment_mode(tenant_id, orders)
    track = normalize_procurement_fulfillment_mode(purchase_pull_track)
    if track == PROCUREMENT_MODE_ORDER:
        filtered_orders = {
            oid: o
            for oid, o in {int(o.id): o for o in orders}.items()
            if mode_by_order.get(oid) != PROCUREMENT_MODE_REQUISITION
        }
    elif track == PROCUREMENT_MODE_REQUISITION:
        filtered_orders = {
            oid: o
            for oid, o in {int(o.id): o for o in orders}.items()
            if mode_by_order.get(oid) != PROCUREMENT_MODE_ORDER
        }
    else:
        filtered_orders = {int(o.id): o for o in orders}
    if not filtered_orders:
        return {"data": [], "total": 0}

    order_by_id = filtered_orders
    items = await SalesOrderItem.filter(
        tenant_id=tenant_id, sales_order_id__in=list(order_by_id.keys())
    ).all()
    items_by_order: Dict[int, List[Any]] = {}
    for it in items:
        items_by_order.setdefault(int(it.sales_order_id), []).append(it)

    fulfill_coro = (
        batch_remaining_fulfillable_qty_by_material_for_track(
            tenant_id, items_by_order, purchase_track=track
        )
        if track
        else batch_remaining_fulfillable_qty_by_material(tenant_id, items_by_order)
    )
    material_by_id, fulfill_by_order, pushed_purchase_by_item, pushed_wo_by_item = (
        await asyncio.gather(
            _load_materials_for_items(tenant_id, items_by_order),
            fulfill_coro,
            batch_pushed_purchase_qty_by_sales_order_item(
                tenant_id, items_by_order, purchase_track=track
            ),
            batch_pushed_work_order_qty_by_sales_order_item(tenant_id, items_by_order),
        )
    )
    buy_ids = {
        mid for mid, m in material_by_id.items() if material_is_buy_eligible(m)
    }
    from apps.kuaizhizao.utils.pull_open_line_quantity import build_partial_push_qty_triplet

    kw = (keyword or "").strip().lower()
    lines: List[Dict[str, Any]] = []
    for oid, order_items in items_by_order.items():
        order = order_by_id.get(oid)
        if not order:
            continue
        remaining_cursor: Dict[int, Decimal] = {
            mid: qty
            for mid, qty in (fulfill_by_order.get(oid) or {}).items()
            if mid in buy_ids
        }
        for it in sorted(order_items, key=lambda row: int(getattr(row, "id", 0) or 0)):
            item_id = int(it.id) if it.id is not None else 0
            if item_id <= 0:
                continue
            mid = int(getattr(it, "material_id", 0) or 0)
            if mid not in buy_ids:
                continue
            qty_dec = Decimal(str(it.order_quantity or 0))
            if qty_dec <= 0:
                continue
            item_purchase = pushed_purchase_by_item.get(item_id, Decimal("0"))
            item_wo = pushed_wo_by_item.get(item_id, Decimal("0"))
            item_fulfilled = item_purchase + item_wo
            line_rem = max(Decimal("0"), qty_dec - item_fulfilled)
            if pullable_only and line_rem <= 0:
                continue
            material_rem = remaining_cursor.get(mid, Decimal("0"))
            max_qty = (
                min(line_rem, material_rem)
                if line_rem > 0 and material_rem > 0
                else Decimal("0")
            )
            if pullable_only and max_qty <= 0:
                continue
            remaining_cursor[mid] = material_rem - max_qty
            material_code = str(it.material_code or "").strip()
            material_name = str(it.material_name or "").strip()
            material_spec = str(it.material_spec or "").strip()
            order_code = str(order.order_code or "").strip()
            customer_name = str(getattr(order, "customer_name", None) or "").strip()
            if kw:
                haystack = " ".join(
                    [order_code, customer_name, material_code, material_name, material_spec]
                ).lower()
                if kw not in haystack:
                    continue
            qty = float(qty_dec)
            remaining = float(max_qty)
            _, pushed, _ = build_partial_push_qty_triplet(qty_dec, item_fulfilled)
            material = material_by_id.get(mid)
            supplier_id = resolve_default_supplier_id_from_material(material)
            supplier_name = resolve_default_supplier_name_from_material(material) or ""
            order_date = (
                order.order_date.isoformat()
                if getattr(order, "order_date", None)
                else None
            )
            line: Dict[str, Any] = {
                "id": item_id,
                "sales_order_id": oid,
                "order_code": order.order_code,
                "document_date": order_date,
                "order_date": order_date,
                "customer_name": getattr(order, "customer_name", None),
                "material_id": it.material_id,
                "material_code": material_code,
                "material_name": material_name,
                "material_spec": material_spec or None,
                "unit": it.material_unit or "件",
                "supplier_id": int(supplier_id) if supplier_id else None,
                "supplier_name": str(supplier_name or "") or None,
                "pushed_work_order_quantity": float(item_wo),
                "pushed_purchase_quantity": float(item_purchase),
            }
            enrich_pull_line_from_source_item(
                line,
                it,
                suggested_primary=qty,
                pushed_primary=pushed,
                remaining_primary=remaining,
                occupied_aux_pushed=0,
            )
            lines.append(line)
    lines.sort(
        key=lambda r: (
            str(r.get("order_code") or ""),
            str(r.get("material_code") or ""),
            int(r.get("id") or 0),
        ),
        reverse=True,
    )
    from apps.kuaizhizao.utils.inventory_helper import paginate_pull_lines_with_stock

    return await paginate_pull_lines_with_stock(tenant_id, lines, skip, limit)


async def list_purchase_order_sales_order_pull_lines(
    tenant_id: int,
    *,
    skip: int = 0,
    limit: int = 20,
    keyword: Optional[str] = None,
    sales_order_id: Optional[int] = None,
    pullable_only: bool = True,
) -> Dict[str, Any]:
    return await _list_sales_order_buy_pull_lines(
        tenant_id,
        skip=skip,
        limit=limit,
        keyword=keyword,
        sales_order_id=sales_order_id,
        pullable_only=pullable_only,
        block_when_require_pr=True,
        purchase_pull_track="purchase_order",
    )


async def list_purchase_requisition_sales_order_pull_lines(
    tenant_id: int,
    *,
    skip: int = 0,
    limit: int = 20,
    keyword: Optional[str] = None,
    sales_order_id: Optional[int] = None,
    pullable_only: bool = True,
) -> Dict[str, Any]:
    return await _list_sales_order_buy_pull_lines(
        tenant_id,
        skip=skip,
        limit=limit,
        keyword=keyword,
        sales_order_id=sales_order_id,
        pullable_only=pullable_only,
        block_when_require_pr=False,
        purchase_pull_track="purchase_requisition",
    )


async def _list_sales_orders_for_buy_pull(
    tenant_id: int,
    *,
    skip: int = 0,
    limit: int = 20,
    keyword: Optional[str] = None,
    pullable_only: bool = True,
    block_when_require_pr: bool,
) -> Dict[str, Any]:
    from apps.kuaizhizao.models.sales_order import SalesOrder
    from apps.kuaizhizao.models.sales_order_item import SalesOrderItem
    from tortoise.expressions import Q

    if block_when_require_pr and await require_purchase_requisition_for_tenant(tenant_id):
        return {"data": [], "total": 0, "success": True}

    from tortoise.expressions import Q

    q = SalesOrder.filter(tenant_id=tenant_id, deleted_at__isnull=True)
    if keyword and str(keyword).strip():
        kw = str(keyword).strip()
        q = q.filter(
            Q(order_code__icontains=kw)
            | Q(customer_name__icontains=kw)
            | Q(order_name__icontains=kw)
        )
    orders = await q.order_by("-id").limit(500).all()
    if not orders:
        return {"data": [], "total": 0, "success": True}

    audited: List[Any] = []
    for order in orders:
        raw = str(getattr(order, "status", "") or "").strip()
        normalized = normalize_status(raw)
        if normalized in (DemandStatus.AUDITED.value, DemandStatus.CONFIRMED.value) or raw in LEGACY_AUDITED_VALUES:
            audited.append(order)
    if not audited:
        return {"data": [], "total": 0, "success": True}

    order_ids = [int(o.id) for o in audited]
    items = await SalesOrderItem.filter(
        tenant_id=tenant_id, sales_order_id__in=order_ids
    ).all()
    items_by_order: Dict[int, List[Any]] = {}
    for it in items:
        items_by_order.setdefault(int(it.sales_order_id), []).append(it)

    purchasable_map = await batch_has_purchasable_remaining(tenant_id, items_by_order)
    rows = []
    for order in audited:
        oid = int(order.id)
        if pullable_only and not purchasable_map.get(oid, False):
            continue
        rows.append(
            {
                "id": oid,
                "order_code": order.order_code,
                "customer_name": getattr(order, "customer_name", None),
                "order_date": str(order.order_date) if order.order_date else None,
                "total_quantity": float(order.total_quantity or 0),
            }
        )
    rows.sort(key=lambda r: str(r.get("order_code") or ""), reverse=True)
    total = len(rows)
    page_rows = rows[skip : skip + limit] if skip < len(rows) else []
    return {"data": page_rows, "total": total, "success": True}


async def list_sales_orders_for_purchase_order_pull(
    tenant_id: int,
    *,
    skip: int = 0,
    limit: int = 20,
    keyword: Optional[str] = None,
    pullable_only: bool = True,
) -> Dict[str, Any]:
    """供采购订单「从销售订单创建」取单：已审核且仍有外购共享余量的销售订单头。"""
    return await _list_sales_orders_for_buy_pull(
        tenant_id,
        skip=skip,
        limit=limit,
        keyword=keyword,
        pullable_only=pullable_only,
        block_when_require_pr=True,
    )


async def list_sales_orders_for_purchase_requisition_pull(
    tenant_id: int,
    *,
    skip: int = 0,
    limit: int = 20,
    keyword: Optional[str] = None,
    pullable_only: bool = True,
) -> Dict[str, Any]:
    """供采购申请「从销售订单创建」取单：已审核且仍有外购共享余量的销售订单头。"""
    return await _list_sales_orders_for_buy_pull(
        tenant_id,
        skip=skip,
        limit=limit,
        keyword=keyword,
        pullable_only=pullable_only,
        block_when_require_pr=False,
    )
