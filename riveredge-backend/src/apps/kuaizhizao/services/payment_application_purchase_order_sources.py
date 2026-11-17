"""付款申请详情：按申请行聚合来源采购订单（只读快照，不写申请行表）。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Sequence

from apps.kuaizhizao.models.payment_application import PaymentApplicationLine
from apps.kuaizhizao.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from core.utils.timezone_utils import to_api_isoformat


def _normalize_payment_line_source_type(source_type: Any) -> str:
    return str(source_type or "").strip().lower().replace("-", "_")


def _is_purchase_order_source(source_type: Any) -> bool:
    raw = _normalize_payment_line_source_type(source_type)
    return raw in ("purchase_order", "purchaseorder")


def _is_purchase_receipt_source(source_type: Any) -> bool:
    return _normalize_payment_line_source_type(source_type) == "purchase_receipt"


async def load_payment_application_purchase_order_sources(
    tenant_id: int,
    lines: Sequence[PaymentApplicationLine],
) -> List[Dict[str, Any]]:
    po_ids: set[int] = set()
    codes: set[str] = set()
    for line in lines:
        if not _is_purchase_order_source(line.source_type):
            continue
        if line.source_id and int(line.source_id) > 0:
            po_ids.add(int(line.source_id))
        code = str(line.source_code or "").strip()
        if code:
            codes.add(code)
    if codes:
        code_rows = await PurchaseOrder.filter(
            tenant_id=tenant_id,
            order_code__in=list(codes),
            deleted_at__isnull=True,
        ).all()
        for order in code_rows:
            po_ids.add(int(order.id))
    if not po_ids:
        return []
    po_id_list = sorted(po_ids)
    orders = await PurchaseOrder.filter(
        tenant_id=tenant_id, id__in=po_id_list, deleted_at__isnull=True
    ).all()
    by_id = {int(o.id): o for o in orders}
    item_rows = await PurchaseOrderItem.filter(
        tenant_id=tenant_id,
        order_id__in=po_id_list,
        deleted_at__isnull=True,
    ).order_by("order_id", "id")
    items_by_order: Dict[int, List[PurchaseOrderItem]] = {}
    for row in item_rows:
        oid = int(row.order_id)
        items_by_order.setdefault(oid, []).append(row)

    out: List[Dict[str, Any]] = []
    for oid in po_id_list:
        order = by_id.get(oid)
        if not order:
            continue
        line_items = items_by_order.get(oid, [])
        out.append(
            {
                "id": oid,
                "order_code": order.order_code or "",
                "order_date": to_api_isoformat(order.order_date)
                if order.order_date
                else None,
                "order_type": order.order_type or "",
                "buyer_name": order.buyer_name or "",
                "total_amount": str(order.total_amount or Decimal("0")),
                "items": [
                    {
                        "id": int(it.id),
                        "material_code": it.material_code or "",
                        "material_name": it.material_name or "",
                        "material_spec": it.material_spec or "",
                        "quantity": str(it.ordered_quantity or Decimal("0")),
                        "unit": it.unit or "",
                        "unit_price": str(it.unit_price or Decimal("0")),
                        "total_price": str(it.total_price or Decimal("0")),
                        "notes": str(getattr(it, "notes", None) or ""),
                    }
                    for it in line_items
                ],
            }
        )
    return out


async def load_payment_application_print_purchase_order_items(
    tenant_id: int,
    lines: Sequence[PaymentApplicationLine],
) -> List[Dict[str, Any]]:
    """打印用：扁平化采购订单行（含来源为采购入库时反查订单）。"""
    from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

    po_sources = list(await load_payment_application_purchase_order_sources(tenant_id, lines))
    known_order_ids = {int(s["id"]) for s in po_sources if s.get("id")}

    receipt_ids: set[int] = set()
    receipt_codes: set[str] = set()
    for line in lines:
        if not _is_purchase_receipt_source(line.source_type):
            continue
        if line.source_id and int(line.source_id) > 0:
            receipt_ids.add(int(line.source_id))
        code = str(line.source_code or "").strip()
        if code:
            receipt_codes.add(code)
    extra_po_ids: set[int] = set()
    if receipt_ids or receipt_codes:
        receipt_q = PurchaseReceipt.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if receipt_ids and receipt_codes:
            from tortoise.expressions import Q

            receipt_rows = await receipt_q.filter(
                Q(id__in=list(receipt_ids)) | Q(receipt_code__in=list(receipt_codes))
            ).all()
        elif receipt_ids:
            receipt_rows = await receipt_q.filter(id__in=list(receipt_ids)).all()
        else:
            receipt_rows = await receipt_q.filter(receipt_code__in=list(receipt_codes)).all()
        for receipt in receipt_rows:
            if receipt.purchase_order_id and int(receipt.purchase_order_id) > 0:
                oid = int(receipt.purchase_order_id)
                if oid not in known_order_ids:
                    extra_po_ids.add(oid)
    if extra_po_ids:
        orders = await PurchaseOrder.filter(
            tenant_id=tenant_id, id__in=sorted(extra_po_ids), deleted_at__isnull=True
        ).all()
        item_rows = await PurchaseOrderItem.filter(
            tenant_id=tenant_id,
            order_id__in=sorted(extra_po_ids),
            deleted_at__isnull=True,
        ).order_by("order_id", "id")
        items_by_order: Dict[int, List[PurchaseOrderItem]] = {}
        for row in item_rows:
            items_by_order.setdefault(int(row.order_id), []).append(row)
        for order in orders:
            oid = int(order.id)
            known_order_ids.add(oid)
            po_sources.append(
                {
                    "id": oid,
                    "order_code": order.order_code or "",
                    "order_date": to_api_isoformat(order.order_date)
                    if order.order_date
                    else None,
                    "order_type": order.order_type or "",
                    "buyer_name": order.buyer_name or "",
                    "total_amount": str(order.total_amount or Decimal("0")),
                    "items": [
                        {
                            "id": int(it.id),
                            "material_code": it.material_code or "",
                            "material_name": it.material_name or "",
                            "material_spec": it.material_spec or "",
                            "quantity": str(it.ordered_quantity or Decimal("0")),
                            "unit": it.unit or "",
                            "unit_price": str(it.unit_price or Decimal("0")),
                            "total_price": str(it.total_price or Decimal("0")),
                            "notes": str(getattr(it, "notes", None) or ""),
                        }
                        for it in items_by_order.get(oid, [])
                    ],
                }
            )

    flat: List[Dict[str, Any]] = []
    for po in po_sources:
        order_code = str(po.get("order_code") or "").strip()
        for it in po.get("items") or []:
            if not isinstance(it, dict):
                continue
            flat.append(
                {
                    "purchase_order_code": order_code,
                    "material_code": it.get("material_code") or "",
                    "material_name": it.get("material_name") or "",
                    "material_spec": it.get("material_spec") or "",
                    "unit": it.get("unit") or "",
                    "quantity": it.get("quantity") or "",
                    "unit_price": it.get("unit_price") or "",
                    "total_price": it.get("total_price") or "",
                    "notes": it.get("notes") or "",
                }
            )
    return flat
