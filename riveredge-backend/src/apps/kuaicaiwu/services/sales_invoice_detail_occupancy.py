"""明细销售发票：按 InvoiceItem 在审核通过后写入出库行开票占用。"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import DefaultDict, List, Optional, Tuple

from apps.kuaicaiwu.models.invoice import InvoiceItem
from apps.kuaicaiwu.services.sales_delivery_line_finance_occupancy_service import (
    record_sales_delivery_invoice_occupancy,
)

_MONEY = Decimal("0.01")


def _q_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(_MONEY)


async def record_detail_sales_invoice_occupancy_on_approve(
    tenant_id: int,
    invoice_id: int,
    *,
    created_by: Optional[int] = None,
) -> None:
    items = await InvoiceItem.filter(
        tenant_id=tenant_id,
        invoice_id=int(invoice_id),
        deleted_at__isnull=True,
    ).order_by("id")
    if not items:
        return
    by_delivery: DefaultDict[int, List[Tuple[int, Decimal, Decimal]]] = defaultdict(list)
    for row in items:
        doc_type = str(row.source_doc_type or "").strip()
        if doc_type != "sales_delivery":
            continue
        did = int(row.source_doc_id or 0)
        sid = int(row.source_line_id or 0)
        if did <= 0 or sid <= 0:
            continue
        incl = _q_money(row.amount) + _q_money(row.tax_amount)
        if incl <= 0:
            continue
        qty = Decimal(str(row.quantity or 0))
        by_delivery[did].append((sid, qty, incl))
    for delivery_id, slices in by_delivery.items():
        total = sum((amt for _, _, amt in slices), Decimal("0"))
        await record_sales_delivery_invoice_occupancy(
            tenant_id,
            sales_delivery_id=delivery_id,
            invoice_id=int(invoice_id),
            amount=_q_money(total),
            line_slices=slices,
            created_by=created_by,
        )