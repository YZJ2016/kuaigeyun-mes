"""
历史数据：按已有应付/进项与单据关系补写入库行财务占用（仅补缺，不覆盖已有占用）。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from apps.kuaicaiwu.constants.finance_source_types import PAYABLE_SOURCE_PURCHASE_RECEIPT
from apps.kuaicaiwu.models.payable import Payable
from apps.kuaicaiwu.models.purchase_invoice import PurchaseInvoice
from apps.kuaicaiwu.models.purchase_receipt_line_finance_occupancy import (
    PurchaseReceiptLineFinanceOccupancy,
)
from apps.kuaicaiwu.services.invoice_source_allocation import parse_relation_allocated_amount
from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
    resolve_purchase_receipt_id_from_payable,
)
from apps.kuaicaiwu.services.purchase_receipt_line_finance_occupancy_service import (
    PurchaseReceiptLineFinanceOccupancyService,
    _KIND_PAYABLE,
    _q_money,
    record_purchase_receipt_invoice_from_payable,
    record_purchase_receipt_invoice_occupancy,
    record_purchase_receipt_payable_occupancy,
)
from apps.kuaizhizao.models.document_relation import DocumentRelation
from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem
from infra.exceptions.exceptions import BusinessLogicError

_RECEIPT_SOURCE_TYPES = frozenset(
    {
        "purchase_receipt",
        "采购入库",
        "PurchaseReceipt",
        PAYABLE_SOURCE_PURCHASE_RECEIPT,
    }
)


async def _target_has_occupancy(
    tenant_id: int,
    target_doc_type: str,
    target_doc_id: int,
    occupancy_kind: str,
) -> bool:
    return (
        await PurchaseReceiptLineFinanceOccupancy.filter(
            tenant_id=tenant_id,
            target_doc_type=target_doc_type,
            target_doc_id=int(target_doc_id),
            occupancy_kind=occupancy_kind,
            deleted_at__isnull=True,
        ).count()
        > 0
    )


async def _remaining_payable_capacity_on_receipt(tenant_id: int, receipt_id: int) -> Decimal:
    svc = PurchaseReceiptLineFinanceOccupancyService()
    occupied = await svc._sum_occupied_by_item(tenant_id, receipt_id, _KIND_PAYABLE)
    items = await PurchaseReceiptItem.filter(
        tenant_id=tenant_id,
        receipt_id=receipt_id,
        deleted_at__isnull=True,
    ).all()
    total = Decimal("0")
    for item in items:
        cap = _q_money(item.total_amount or 0)
        used = occupied.get(int(item.id), Decimal("0"))
        rem = _q_money(cap - used)
        if rem > 0:
            total += rem
    return _q_money(total)


async def backfill_payables_from_receipt(
    tenant_id: int,
    *,
    apply: bool,
) -> Tuple[int, int, List[str]]:
    """补写来源为采购入库的应付单行占用。返回 (候选数, 已写入数, 跳过说明)。"""
    payables = await Payable.filter(tenant_id=tenant_id, deleted_at__isnull=True).order_by("id").all()
    candidates = 0
    written = 0
    skipped: List[str] = []
    for payable in payables:
        receipt_id = resolve_purchase_receipt_id_from_payable(
            str(getattr(payable, "source_type", "") or ""),
            getattr(payable, "source_id", None),
        )
        if not receipt_id:
            continue
        if await _target_has_occupancy(tenant_id, "Payable", int(payable.id), "payable"):
            continue
        candidates += 1
        if not apply:
            continue
        payable_total = _q_money(payable.total_amount or 0)
        remaining = await _remaining_payable_capacity_on_receipt(tenant_id, int(receipt_id))
        if remaining <= 0:
            skipped.append(f"payable={payable.id} receipt={receipt_id}: 入库行应付余量已为 0")
            continue
        alloc = payable_total if payable_total <= remaining else remaining
        try:
            await record_purchase_receipt_payable_occupancy(
                tenant_id,
                int(receipt_id),
                int(payable.id),
                alloc,
            )
            written += 1
            if alloc < payable_total:
                skipped.append(
                    f"payable={payable.id}: 仅写入 {alloc}（应付 {payable_total}，入库余量 {remaining}）"
                )
        except BusinessLogicError as exc:
            skipped.append(f"payable={payable.id}: {exc}")
    return candidates, written, skipped


async def backfill_invoices_from_relations(tenant_id: int, *, apply: bool) -> Tuple[int, int]:
    """按 DocumentRelation 补写入库行收票占用。返回 (候选发票数, 已写入数)。"""
    invoices = await PurchaseInvoice.filter(tenant_id=tenant_id, deleted_at__isnull=True).all()
    candidates = 0
    written = 0
    for invoice in invoices:
        iid = int(invoice.id)
        if await _target_has_occupancy(tenant_id, "PurchaseInvoice", iid, "invoice"):
            continue

        rels = await DocumentRelation.filter(
            tenant_id=tenant_id,
            target_type="purchase_invoice",
            target_id=iid,
            relation_mode="pull",
        ).all()
        if not rels:
            continue

        payable_rels = [r for r in rels if str(r.source_type or "").strip() == "payable"]
        receipt_rels = [
            r for r in rels if str(r.source_type or "").strip() in _RECEIPT_SOURCE_TYPES
        ]
        if not payable_rels and not receipt_rels:
            continue

        candidates += 1
        if not apply:
            continue

        try:
            if receipt_rels and not payable_rels:
                rel = receipt_rels[0]
                amt = parse_relation_allocated_amount(rel.notes) or Decimal(
                    str(invoice.total_amount or 0)
                )
                await record_purchase_receipt_invoice_occupancy(
                    tenant_id,
                    int(rel.source_id),
                    iid,
                    amt,
                )
                written += 1
                continue

            for rel in payable_rels:
                sid = int(rel.source_id)
                amt = parse_relation_allocated_amount(rel.notes)
                if amt is None:
                    payable = await Payable.get_or_none(
                        tenant_id=tenant_id, id=sid, deleted_at__isnull=True
                    )
                    amt = Decimal(str(payable.total_amount or 0)) if payable else Decimal("0")
                if amt <= 0:
                    continue
                await record_purchase_receipt_invoice_from_payable(
                    tenant_id,
                    sid,
                    iid,
                    amt,
                    allow_append=True,
                )
            written += 1
        except BusinessLogicError:
            continue
    return candidates, written


async def backfill_tenant(tenant_id: int, *, apply: bool = False) -> Dict[str, Any]:
    p_c, p_w, p_skip = await backfill_payables_from_receipt(tenant_id, apply=apply)
    i_c, i_w = await backfill_invoices_from_relations(tenant_id, apply=apply)
    return {
        "tenant_id": tenant_id,
        "apply": apply,
        "payable_candidates": p_c,
        "payable_written": p_w,
        "payable_skipped_notes": p_skip,
        "invoice_candidates": i_c,
        "invoice_written": i_w,
    }
