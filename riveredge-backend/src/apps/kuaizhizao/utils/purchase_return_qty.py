"""采购退货数量按采购订单行汇总（含 purchase_order_item_id 缺失时的回落匹配）。"""

from decimal import Decimal
from typing import Dict, List, Literal

ReplenishFilter = Literal["all", "exclude_replenish", "replenish_only"]

_PURCHASE_RETURN_CONFIRMED_STATUSES = frozenset(
    {"已退货", "completed", "已完成", "RETURNED"}
)
_PURCHASE_RETURN_VOID_STATUSES = frozenset(
    {"已取消", "cancelled", "CANCELLED", "已作废", "作废", "void", "VOID"}
)
_PURCHASE_RECEIPT_CONFIRMED_STATUSES = frozenset(
    {"已入库", "已完成", "completed", "COMPLETED"}
)


async def _purchase_return_qty_by_po_item_ids(
    tenant_id: int,
    purchase_order_item_ids: List[int],
    *,
    confirmed_only: bool,
    replenish_filter: ReplenishFilter = "all",
) -> Dict[int, Decimal]:
    """按采购订单行汇总退货占用量；明细缺 purchase_order_item_id 时按入库行/订单+物料回落。"""
    from apps.kuaizhizao.models.purchase_order import PurchaseOrderItem
    from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem
    from apps.kuaizhizao.models.purchase_return import PurchaseReturn
    from apps.kuaizhizao.models.purchase_return_item import PurchaseReturnItem

    result: Dict[int, Decimal] = {
        int(i): Decimal("0") for i in purchase_order_item_ids if int(i) > 0
    }
    if not result:
        return result

    po_items = await PurchaseOrderItem.filter(
        tenant_id=tenant_id, id__in=list(result.keys())
    ).all()
    if not po_items:
        return result

    order_ids = sorted({int(i.order_id) for i in po_items})
    item_by_order_material: Dict[tuple[int, int], int] = {}
    for po_item in po_items:
        material_id = int(po_item.material_id or 0)
        if material_id > 0:
            item_by_order_material[(int(po_item.order_id), material_id)] = int(po_item.id)

    returns = await PurchaseReturn.filter(
        tenant_id=tenant_id,
        purchase_order_id__in=order_ids,
        deleted_at__isnull=True,
    ).all()
    eligible_return_ids: set[int] = set()
    return_order_by_id: Dict[int, int] = {}
    for header in returns:
        status = str(header.status or "").strip()
        if status in _PURCHASE_RETURN_VOID_STATUSES:
            continue
        if confirmed_only and status not in _PURCHASE_RETURN_CONFIRMED_STATUSES:
            continue
        is_replenish = bool(getattr(header, "replenish", False))
        if replenish_filter == "exclude_replenish" and is_replenish:
            continue
        if replenish_filter == "replenish_only" and not is_replenish:
            continue
        rid = int(header.id)
        eligible_return_ids.add(rid)
        return_order_by_id[rid] = int(header.purchase_order_id or 0)

    if not eligible_return_ids:
        return result

    return_items = await PurchaseReturnItem.filter(
        tenant_id=tenant_id,
        return_id__in=list(eligible_return_ids),
    ).all()
    if not return_items:
        return result

    receipt_item_ids = [
        int(ri.purchase_receipt_item_id)
        for ri in return_items
        if ri.purchase_receipt_item_id
    ]
    receipt_po_item: Dict[int, int] = {}
    if receipt_item_ids:
        rows = await PurchaseReceiptItem.filter(
            tenant_id=tenant_id,
            id__in=receipt_item_ids,
        ).values("id", "purchase_order_item_id")
        for row in rows:
            po_item_id = int(row.get("purchase_order_item_id") or 0)
            if po_item_id > 0:
                receipt_po_item[int(row["id"])] = po_item_id

    def _resolve_po_item_id(ri: PurchaseReturnItem) -> int:
        direct = int(ri.purchase_order_item_id or 0)
        if direct in result:
            return direct
        receipt_id = int(ri.purchase_receipt_item_id or 0)
        if receipt_id in receipt_po_item:
            mapped = receipt_po_item[receipt_id]
            if mapped in result:
                return mapped
        order_id = return_order_by_id.get(int(ri.return_id or 0), 0)
        material_id = int(ri.material_id or 0)
        if order_id > 0 and material_id > 0:
            return item_by_order_material.get((order_id, material_id), 0)
        return 0

    for ri in return_items:
        po_item_id = _resolve_po_item_id(ri)
        if po_item_id <= 0:
            continue
        result[po_item_id] = result.get(po_item_id, Decimal("0")) + Decimal(
            str(ri.return_quantity or 0)
        )
    return result


async def confirmed_returned_qty_by_purchase_order_item_ids(
    tenant_id: int,
    purchase_order_item_ids: List[int],
) -> Dict[int, Decimal]:
    """按采购订单行统计已确认退货数量（仅已退货，不含待退货草稿；不含补货退货）。"""
    return await _purchase_return_qty_by_po_item_ids(
        tenant_id,
        purchase_order_item_ids,
        confirmed_only=True,
        replenish_filter="exclude_replenish",
    )


async def confirmed_returned_aux_qty_by_purchase_order_item_ids(
    tenant_id: int,
    purchase_order_item_ids: List[int],
) -> Dict[int, float]:
    """按采购订单行统计已确认退货副数量（与 confirmed_returned_qty_by_purchase_order_item_ids 同口径）。"""
    qty_map = await _purchase_return_aux_qty_by_po_item_ids(
        tenant_id,
        purchase_order_item_ids,
        confirmed_only=True,
        replenish_filter="exclude_replenish",
    )
    return {item_id: float(qty) for item_id, qty in qty_map.items()}


async def replenish_return_qty_by_purchase_order_item_ids(
    tenant_id: int,
    purchase_order_item_ids: List[int],
    *,
    confirmed_only: bool = False,
) -> Dict[int, Decimal]:
    """按采购订单行统计补货退货数量（保存后即可释放可入库量；默认含待退货）。"""
    return await _purchase_return_qty_by_po_item_ids(
        tenant_id,
        purchase_order_item_ids,
        confirmed_only=confirmed_only,
        replenish_filter="replenish_only",
    )


async def returned_qty_by_purchase_order_item_ids(
    tenant_id: int,
    purchase_order_item_ids: List[int],
) -> Dict[int, float]:
    """按采购订单行统计已退货数量（含待退货，占用可退余量）。"""
    qty_map = await _purchase_return_qty_by_po_item_ids(
        tenant_id,
        purchase_order_item_ids,
        confirmed_only=False,
    )
    return {item_id: float(qty) for item_id, qty in qty_map.items()}


async def returned_qty_by_purchase_receipt_item_ids(
    tenant_id: int,
    purchase_receipt_item_ids: List[int],
) -> Dict[int, float]:
    """按采购入库明细统计已退货数量（含待退货，占用可退余量；作废退货单不计）。"""
    from apps.kuaizhizao.models.purchase_return import PurchaseReturn
    from apps.kuaizhizao.models.purchase_return_item import PurchaseReturnItem

    ids = [int(i) for i in purchase_receipt_item_ids if int(i) > 0]
    if not ids:
        return {}

    return_items = await PurchaseReturnItem.filter(
        tenant_id=tenant_id,
        purchase_receipt_item_id__in=ids,
    ).all()
    if not return_items:
        return {i: 0.0 for i in ids}

    return_ids = list({int(ri.return_id) for ri in return_items if ri.return_id})
    eligible_return_ids: set[int] = set()
    if return_ids:
        headers = await PurchaseReturn.filter(
            tenant_id=tenant_id,
            id__in=return_ids,
            deleted_at__isnull=True,
        ).all()
        for header in headers:
            status = str(header.status or "").strip()
            if status in _PURCHASE_RETURN_VOID_STATUSES:
                continue
            eligible_return_ids.add(int(header.id))

    totals: Dict[int, float] = {i: 0.0 for i in ids}
    for ri in return_items:
        if int(ri.return_id) not in eligible_return_ids:
            continue
        item_id = int(ri.purchase_receipt_item_id or 0)
        if item_id not in totals:
            continue
        totals[item_id] = totals.get(item_id, 0.0) + float(ri.return_quantity or 0)
    return totals


async def _purchase_return_aux_qty_by_po_item_ids(
    tenant_id: int,
    purchase_order_item_ids: List[int],
    *,
    confirmed_only: bool,
    replenish_filter: ReplenishFilter = "all",
) -> Dict[int, Decimal]:
    """按采购订单行汇总退货占用的副数量。"""
    from apps.kuaizhizao.models.purchase_order import PurchaseOrderItem
    from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem
    from apps.kuaizhizao.models.purchase_return import PurchaseReturn
    from apps.kuaizhizao.models.purchase_return_item import PurchaseReturnItem

    result: Dict[int, Decimal] = {
        int(i): Decimal("0") for i in purchase_order_item_ids if int(i) > 0
    }
    if not result:
        return result

    po_items = await PurchaseOrderItem.filter(
        tenant_id=tenant_id, id__in=list(result.keys())
    ).all()
    if not po_items:
        return result

    order_ids = sorted({int(i.order_id) for i in po_items})
    item_by_order_material: Dict[tuple[int, int], int] = {}
    for po_item in po_items:
        material_id = int(po_item.material_id or 0)
        if material_id > 0:
            item_by_order_material[(int(po_item.order_id), material_id)] = int(po_item.id)

    returns = await PurchaseReturn.filter(
        tenant_id=tenant_id,
        purchase_order_id__in=order_ids,
        deleted_at__isnull=True,
    ).all()
    eligible_return_ids: set[int] = set()
    return_order_by_id: Dict[int, int] = {}
    for header in returns:
        status = str(header.status or "").strip()
        if status in _PURCHASE_RETURN_VOID_STATUSES:
            continue
        if confirmed_only and status not in _PURCHASE_RETURN_CONFIRMED_STATUSES:
            continue
        is_replenish = bool(getattr(header, "replenish", False))
        if replenish_filter == "exclude_replenish" and is_replenish:
            continue
        if replenish_filter == "replenish_only" and not is_replenish:
            continue
        rid = int(header.id)
        eligible_return_ids.add(rid)
        return_order_by_id[rid] = int(header.purchase_order_id or 0)

    if not eligible_return_ids:
        return result

    return_items = await PurchaseReturnItem.filter(
        tenant_id=tenant_id,
        return_id__in=list(eligible_return_ids),
    ).all()
    if not return_items:
        return result

    receipt_item_ids = [
        int(ri.purchase_receipt_item_id)
        for ri in return_items
        if ri.purchase_receipt_item_id
    ]
    receipt_po_item: Dict[int, int] = {}
    if receipt_item_ids:
        rows = await PurchaseReceiptItem.filter(
            tenant_id=tenant_id,
            id__in=receipt_item_ids,
        ).values("id", "purchase_order_item_id")
        for row in rows:
            po_item_id = int(row.get("purchase_order_item_id") or 0)
            if po_item_id > 0:
                receipt_po_item[int(row["id"])] = po_item_id

    def _resolve_po_item_id(ri: PurchaseReturnItem) -> int:
        direct = int(ri.purchase_order_item_id or 0)
        if direct in result:
            return direct
        receipt_id = int(ri.purchase_receipt_item_id or 0)
        if receipt_id in receipt_po_item:
            mapped = receipt_po_item[receipt_id]
            if mapped in result:
                return mapped
        order_id = return_order_by_id.get(int(ri.return_id or 0), 0)
        material_id = int(ri.material_id or 0)
        if order_id > 0 and material_id > 0:
            return item_by_order_material.get((order_id, material_id), 0)
        return 0

    for ri in return_items:
        po_item_id = _resolve_po_item_id(ri)
        if po_item_id <= 0:
            continue
        aux = getattr(ri, "aux_quantity", None)
        if aux is None:
            continue
        result[po_item_id] = result.get(po_item_id, Decimal("0")) + Decimal(str(aux))
    return result


async def returned_aux_qty_by_purchase_order_item_ids(
    tenant_id: int,
    purchase_order_item_ids: List[int],
) -> Dict[int, float]:
    qty_map = await _purchase_return_aux_qty_by_po_item_ids(
        tenant_id,
        purchase_order_item_ids,
        confirmed_only=False,
    )
    return {item_id: float(qty) for item_id, qty in qty_map.items()}


async def returned_aux_qty_by_purchase_receipt_item_ids(
    tenant_id: int,
    purchase_receipt_item_ids: List[int],
) -> Dict[int, float]:
    from apps.kuaizhizao.models.purchase_return import PurchaseReturn
    from apps.kuaizhizao.models.purchase_return_item import PurchaseReturnItem

    ids = [int(i) for i in purchase_receipt_item_ids if int(i) > 0]
    if not ids:
        return {}

    return_items = await PurchaseReturnItem.filter(
        tenant_id=tenant_id,
        purchase_receipt_item_id__in=ids,
    ).all()
    if not return_items:
        return {i: 0.0 for i in ids}

    return_ids = list({int(ri.return_id) for ri in return_items if ri.return_id})
    eligible_return_ids: set[int] = set()
    if return_ids:
        headers = await PurchaseReturn.filter(
            tenant_id=tenant_id,
            id__in=return_ids,
            deleted_at__isnull=True,
        ).all()
        for header in headers:
            status = str(header.status or "").strip()
            if status in _PURCHASE_RETURN_VOID_STATUSES:
                continue
            eligible_return_ids.add(int(header.id))

    totals: Dict[int, float] = {i: 0.0 for i in ids}
    for ri in return_items:
        if int(ri.return_id) not in eligible_return_ids:
            continue
        item_id = int(ri.purchase_receipt_item_id or 0)
        if item_id not in totals:
            continue
        aux = getattr(ri, "aux_quantity", None)
        if aux is None:
            continue
        totals[item_id] = totals.get(item_id, 0.0) + float(aux)
    return totals


async def received_aux_qty_by_purchase_order_item_ids(
    tenant_id: int,
    purchase_order_item_ids: List[int],
) -> Dict[int, float]:
    """按采购订单行汇总已确认入库明细副数量（采购退货开口 suggested 辅量）。"""
    from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
    from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem

    ids = [int(i) for i in purchase_order_item_ids if int(i) > 0]
    if not ids:
        return {}
    item_rows = await PurchaseReceiptItem.filter(
        tenant_id=tenant_id,
        purchase_order_item_id__in=ids,
    ).values("receipt_id", "purchase_order_item_id", "aux_quantity")
    if not item_rows:
        return {i: 0.0 for i in ids}
    receipt_ids = sorted({int(r["receipt_id"]) for r in item_rows if r.get("receipt_id")})
    confirmed_ids: set[int] = set()
    if receipt_ids:
        rows = await PurchaseReceipt.filter(
            tenant_id=tenant_id,
            id__in=receipt_ids,
            deleted_at__isnull=True,
        ).values("id", "status")
        for row in rows:
            if str(row.get("status") or "").strip() in _PURCHASE_RECEIPT_CONFIRMED_STATUSES:
                confirmed_ids.add(int(row["id"]))
    totals: Dict[int, float] = {i: 0.0 for i in ids}
    for row in item_rows:
        rid = int(row.get("receipt_id") or 0)
        if rid not in confirmed_ids:
            continue
        po_item_id = int(row.get("purchase_order_item_id") or 0)
        if po_item_id not in totals:
            continue
        aux = row.get("aux_quantity")
        if aux is None:
            continue
        totals[po_item_id] = totals.get(po_item_id, 0.0) + float(aux)
    return totals
