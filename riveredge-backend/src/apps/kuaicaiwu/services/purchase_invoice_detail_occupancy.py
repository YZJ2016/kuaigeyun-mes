"""明细采购发票：按 PurchaseInvoiceItem 写入入库行开票占用。"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import DefaultDict, List, Tuple

from apps.kuaicaiwu.models.purchase_invoice_item import PurchaseInvoiceItem
from apps.kuaicaiwu.services.purchase_receipt_line_finance_occupancy_service import (
    record_purchase_receipt_invoice_occupancy,
)

_MONEY = Decimal("0.01")


def _q_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(_MONEY)


async def record_detail_purchase_invoice_occupancy(
    tenant_id: int,
    invoice_id: int,
    *,
    created_by: int | None = None,
) -> None:
    items = await PurchaseInvoiceItem.filter(
        tenant_id=tenant_id,
        purchase_invoice_id=int(invoice_id),
        deleted_at__isnull=True,
    ).order_by("id")
    if not items:
        return
    by_receipt: DefaultDict[int, List[Tuple[int, Decimal]]] = defaultdict(list)
    for row in items:
        doc_type = str(row.source_doc_type or "").strip()
        if doc_type not in ("purchase_receipt", "outsource_order_receipt"):
            continue
        rid = int(row.source_doc_id or 0)
        sid = int(row.source_line_id or 0)
        if rid <= 0 or sid <= 0:
            continue
        incl = _q_money(row.amount) + _q_money(row.tax_amount)
        if incl <= 0:
            continue
        by_receipt[rid].append((sid, incl))
    for receipt_id, slices in by_receipt.items():
        total = sum((amt for _, amt in slices), Decimal("0"))
        line_selections = [
            {"purchase_receipt_item_id": int(sid), "amount": amt}
            for sid, amt in slices
        ]
        await record_purchase_receipt_invoice_occupancy(
            tenant_id,
            receipt_id,
            int(invoice_id),
            _q_money(total),
            line_selections=line_selections,
            created_by=created_by,
        )