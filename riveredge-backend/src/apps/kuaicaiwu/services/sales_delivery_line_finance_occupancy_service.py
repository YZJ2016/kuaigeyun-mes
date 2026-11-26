"""销售出库行财务占用（镜像采购入库行占用）。"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Mapping, Optional, Tuple

from apps.kuaicaiwu.models.sales_delivery_line_finance_occupancy import (
    SalesDeliveryLineFinanceOccupancy,
)
from infra.exceptions.exceptions import ValidationError

_MONEY = Decimal("0.01")
_KIND_INVOICE = "invoice"
_KIND_RECEIVABLE = "receivable"
_KIND_RECEIVED = "received"


def _q_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(_MONEY)


async def record_sales_delivery_invoice_occupancy(
    tenant_id: int,
    *,
    sales_delivery_id: int,
    invoice_id: int,
    amount: Decimal,
    line_slices: Optional[List[Tuple[int, Decimal, Decimal]]] = None,
    target_item_id: Optional[int] = None,
) -> None:
    """明细/汇总发票审核后写入出库行开票占用。line_slices: (item_id, qty, amount)。"""
    amt = _q_money(amount)
    if amt <= 0:
        return
    if line_slices:
        for item_id, qty, part in line_slices:
            if _q_money(part) <= 0:
                continue
            await SalesDeliveryLineFinanceOccupancy.create(
                tenant_id=tenant_id,
                sales_delivery_id=sales_delivery_id,
                sales_delivery_item_id=int(item_id),
                occupancy_kind=_KIND_INVOICE,
                quantity=qty,
                amount=_q_money(part),
                target_doc_type="sales_invoice",
                target_doc_id=int(invoice_id),
                target_item_id=target_item_id,
            )
        return
    from apps.kuaizhizao.models.sales_delivery_item import SalesDeliveryItem

    items = await SalesDeliveryItem.filter(
        tenant_id=tenant_id,
        delivery_id=sales_delivery_id,
        deleted_at__isnull=True,
    ).order_by("id")
    if not items:
        raise ValidationError("销售出库单无明细，无法记录开票占用")
    remaining = amt
    for idx, item in enumerate(items):
        part = _q_money(remaining) if idx == len(items) - 1 else _q_money(amt / len(items))
        if idx < len(items) - 1:
            remaining -= part
        await SalesDeliveryLineFinanceOccupancy.create(
            tenant_id=tenant_id,
            sales_delivery_id=sales_delivery_id,
            sales_delivery_item_id=int(item.id),
            occupancy_kind=_KIND_INVOICE,
            quantity=item.delivery_quantity or 0,
            amount=part,
            target_doc_type="sales_invoice",
            target_doc_id=int(invoice_id),
            target_item_id=target_item_id,
        )


async def release_sales_delivery_invoice_occupancy(
    tenant_id: int, invoice_id: int
) -> None:
    await SalesDeliveryLineFinanceOccupancy.filter(
        tenant_id=tenant_id,
        target_doc_type="sales_invoice",
        target_doc_id=int(invoice_id),
        occupancy_kind=_KIND_INVOICE,
        deleted_at__isnull=True,
    ).delete()


async def sum_invoice_occupied_by_delivery_item(
    tenant_id: int, delivery_id: int
) -> Dict[int, Decimal]:
    from tortoise.functions import Sum

    rows = await SalesDeliveryLineFinanceOccupancy.filter(
        tenant_id=tenant_id,
        sales_delivery_id=delivery_id,
        occupancy_kind=_KIND_INVOICE,
        deleted_at__isnull=True,
    ).annotate(total=Sum("amount")).group_by("sales_delivery_item_id").values(
        "sales_delivery_item_id", "total"
    )
    return {int(r["sales_delivery_item_id"]): _q_money(r["total"]) for r in rows}