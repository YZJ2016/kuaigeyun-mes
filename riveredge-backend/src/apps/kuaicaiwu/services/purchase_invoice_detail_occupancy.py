"""明细采购发票：按 PurchaseInvoiceItem 写入入库行/委外批次开票占用。"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import DefaultDict, Dict, List, Tuple

from infra.exceptions.exceptions import ValidationError

from apps.kuaicaiwu.models.purchase_invoice import PurchaseInvoice
from apps.kuaicaiwu.models.purchase_invoice_item import PurchaseInvoiceItem
from apps.kuaicaiwu.services.purchase_receipt_line_finance_occupancy_service import (
    PurchaseReceiptLineFinanceOccupancyService,
    record_purchase_receipt_invoice_occupancy,
)
from apps.kuaicaiwu.services.purchase_invoice_detail_post_approve import (
    sum_outsource_batch_invoice_occupied_incl,
)

_MONEY = Decimal("0.01")
_QTY = Decimal("0.0001")
_KIND_INVOICE = "invoice"


def _q_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(_MONEY)


def _q_qty(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(_QTY)


async def _record_outsource_batch_invoice_occupancy(
    tenant_id: int,
    batch_id: int,
    invoice_id: int,
    amount: Decimal,
    *,
    created_by: int | None = None,
) -> None:
    from apps.kuaicaiwu.services.purchase_invoice_pull_service import (
        PurchaseInvoicePullService,
    )
    from apps.kuaizhizao.models.outsource_order import OutsourceOrder
    from apps.kuaizhizao.models.outsource_order_receipt import OutsourceOrderReceipt

    amt = _q_money(amount)
    if amt <= 0:
        return
    batch = await OutsourceOrderReceipt.get_or_none(
        tenant_id=tenant_id, id=int(batch_id), deleted_at__isnull=True
    )
    if not batch:
        raise ValidationError(f"工序委外收货批次不存在: {batch_id}")
    pull_svc = PurchaseInvoicePullService()
    gross = await pull_svc.outsource_order_receipt_settlement_gross(tenant_id, int(batch_id))
    occupied = await sum_outsource_batch_invoice_occupied_incl(tenant_id, int(batch_id))
    if amt > gross - occupied + _MONEY:
        raise ValidationError(
            f"委外收货批次 {batch_id} 开票金额 {amt} 超过可开票余额 {gross - occupied}"
        )
    qual = _q_qty(batch.qualified_quantity or 0)
    take_qty = qual if qual > 0 else Decimal("1")
    svc = PurchaseReceiptLineFinanceOccupancyService()
    await svc.record_receipt_finance_occupancy_explicit(
        tenant_id,
        int(batch_id),
        occupancy_kind=_KIND_INVOICE,
        target_doc_type="PurchaseInvoice",
        target_doc_id=int(invoice_id),
        slices=[(int(batch_id), take_qty, amt)],
        created_by=created_by,
    )


async def record_detail_purchase_invoice_occupancy(
    tenant_id: int,
    invoice_id: int,
    *,
    created_by: int | None = None,
) -> None:
    rows = await PurchaseInvoiceItem.filter(
        tenant_id=tenant_id,
        purchase_invoice_id=int(invoice_id),
        deleted_at__isnull=True,
    ).order_by("id").all()
    if not rows:
        return
    by_receipt: DefaultDict[int, List[Tuple[int, Decimal]]] = defaultdict(list)
    outsource_totals: Dict[int, Decimal] = {}
    for row in rows:
        doc_type = str(row.source_doc_type or "").strip()
        incl = _q_money(row.amount) + _q_money(row.tax_amount)
        if incl <= 0:
            continue
        if doc_type == "outsource_order_receipt":
            bid = int(row.source_doc_id or row.source_line_id or 0)
            if bid <= 0:
                continue
            outsource_totals[bid] = _q_money(outsource_totals.get(bid, Decimal("0")) + incl)
            continue
        if doc_type != "purchase_receipt":
            continue
        rid = int(row.source_doc_id or 0)
        sid = int(row.source_line_id or 0)
        if rid <= 0 or sid <= 0:
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
            allow_append=True,
        )
    if not outsource_totals:
        return
    invoice = await PurchaseInvoice.get_or_none(
        tenant_id=tenant_id, id=int(invoice_id), deleted_at__isnull=True
    )
    if not invoice:
        return
    from apps.kuaicaiwu.services.purchase_invoice_pull_service import (
        PurchaseInvoicePullService,
    )
    from apps.kuaizhizao.models.outsource_order import OutsourceOrder
    from apps.kuaizhizao.models.outsource_order_receipt import OutsourceOrderReceipt

    pull_svc = PurchaseInvoicePullService()
    for batch_id, total in outsource_totals.items():
        await _record_outsource_batch_invoice_occupancy(
            tenant_id,
            int(batch_id),
            int(invoice_id),
            total,
            created_by=created_by,
        )
        batch = await OutsourceOrderReceipt.get_or_none(
            tenant_id=tenant_id, id=int(batch_id), deleted_at__isnull=True
        )
        if not batch:
            continue
        order = await OutsourceOrder.get_or_none(
            tenant_id=tenant_id,
            id=int(batch.outsource_order_id), deleted_at__isnull=True
        )
        code = f"{order.code}-{batch.id}" if order else str(batch.outsource_order_code or batch_id)
        await pull_svc.create_pull_relation(
            tenant_id=tenant_id,
            source_type="outsource_order_receipt",
            source_id=int(batch_id),
            source_code=code,
            invoice_id=int(invoice_id),
            invoice_code=str(invoice.invoice_code),
            created_by=int(created_by or invoice.created_by or 0),
            allocated_amount=_q_money(total),
        )