"""
对账单 → 购销发票加载源：按 ledger_posting_mode 过滤对账明细行。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, Tuple

from infra.exceptions.exceptions import BusinessLogicError

InvoicePullSide = Literal["sales", "purchase"]


@dataclass(frozen=True)
class PartnerStatementInvoicePullSnapshot:
    ledger_posting_mode: str
    doc_type: str
    source_type: str
    source_ids: List[int]


def normalize_ledger_posting_mode(mode: Optional[str]) -> str:
    m = str(mode or "immediate").strip()
    return m if m in ("immediate", "by_invoice") else "immediate"


def invoice_source_doc_type_for_mode(partner_type: str, ledger_posting_mode: str) -> str:
    pt = str(partner_type or "").strip()
    mode = normalize_ledger_posting_mode(ledger_posting_mode)
    if pt == "Customer":
        return "销售出库" if mode == "by_invoice" else "应收单"
    if pt == "Supplier":
        return "采购入库" if mode == "by_invoice" else "应付单"
    raise BusinessLogicError(f"不支持的往来单位类型: {partner_type}")


def invoice_source_type_for_mode(partner_type: str, ledger_posting_mode: str) -> str:
    pt = str(partner_type or "").strip()
    mode = normalize_ledger_posting_mode(ledger_posting_mode)
    if pt == "Customer":
        return "sales_delivery" if mode == "by_invoice" else "receivable"
    if pt == "Supplier":
        return "purchase_receipt" if mode == "by_invoice" else "payable"
    raise BusinessLogicError(f"不支持的往来单位类型: {partner_type}")


def extract_statement_source_doc_ids(transaction_details: Any, doc_type: str) -> List[int]:
    if not isinstance(transaction_details, dict):
        return []
    lines = transaction_details.get("lines") or []
    if not isinstance(lines, list):
        return []
    want = str(doc_type or "").strip()
    ids: List[int] = []
    seen: set[int] = set()
    for ln in lines:
        if not isinstance(ln, dict):
            continue
        if str(ln.get("doc_type") or "").strip() != want:
            continue
        if int(ln.get("tree_level") or 0) != 0:
            continue
        try:
            amt = float(ln.get("statement_amount") or ln.get("debit") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        if amt <= 0:
            continue
        try:
            doc_id = int(ln.get("doc_id"))
        except (TypeError, ValueError):
            continue
        if doc_id <= 0 or doc_id in seen:
            continue
        seen.add(doc_id)
        ids.append(doc_id)
    return ids


def resolve_statement_invoice_source_ids(
    *,
    partner_type: str,
    ledger_posting_mode: Optional[str],
    transaction_details: Any,
) -> PartnerStatementInvoicePullSnapshot:
    mode = normalize_ledger_posting_mode(ledger_posting_mode)
    doc_type = invoice_source_doc_type_for_mode(partner_type, mode)
    source_type = invoice_source_type_for_mode(partner_type, mode)
    source_ids = extract_statement_source_doc_ids(transaction_details, doc_type)
    return PartnerStatementInvoicePullSnapshot(
        ledger_posting_mode=mode,
        doc_type=doc_type,
        source_type=source_type,
        source_ids=source_ids,
    )


def _capability_reason_codes(side: InvoicePullSide) -> Tuple[str, str]:
    if side == "sales":
        return (
            "sales_invoice.pull_from_partner_statement.no_lines",
            "sales_invoice.pull_from_partner_statement.already_pulled",
        )
    return (
        "purchase_invoice.pull_from_partner_statement.no_lines",
        "purchase_invoice.pull_from_partner_statement.already_pulled",
    )


def derive_pull_capability(
    *,
    side: InvoicePullSide,
    source_ids: List[int],
    remaining: float,
) -> Tuple[bool, Optional[str]]:
    no_lines, already_pulled = _capability_reason_codes(side)
    if not source_ids:
        return False, no_lines
    if remaining <= 0:
        return False, already_pulled
    return True, None


async def load_source_total_amounts(
    tenant_id: int,
    source_type: str,
    source_ids: List[int],
) -> Dict[int, Decimal]:
    if not source_ids:
        return {}
    from apps.kuaicaiwu.models.payable import Payable
    from apps.kuaicaiwu.models.receivable import Receivable
    from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
    from apps.kuaizhizao.models.sales_delivery import SalesDelivery

    out: Dict[int, Decimal] = {}
    if source_type == "sales_delivery":
        rows = await SalesDelivery.filter(
            tenant_id=tenant_id,
            id__in=source_ids,
            deleted_at__isnull=True,
        )
        for d in rows:
            out[int(d.id)] = Decimal(str(d.total_amount or 0))
    elif source_type == "receivable":
        rows = await Receivable.filter(
            tenant_id=tenant_id,
            id__in=source_ids,
            deleted_at__isnull=True,
        )
        for r in rows:
            out[int(r.id)] = Decimal(str(r.total_amount or 0))
    elif source_type == "purchase_receipt":
        rows = await PurchaseReceipt.filter(
            tenant_id=tenant_id,
            id__in=source_ids,
            deleted_at__isnull=True,
        )
        for p in rows:
            out[int(p.id)] = Decimal(str(p.total_amount or 0))
    elif source_type == "payable":
        rows = await Payable.filter(
            tenant_id=tenant_id,
            id__in=source_ids,
            deleted_at__isnull=True,
        )
        for p in rows:
            out[int(p.id)] = Decimal(str(p.total_amount or 0))
    return out


async def sum_pushed_by_source_type(
    tenant_id: int,
    source_type: str,
    source_ids: List[int],
) -> Dict[int, Decimal]:
    if not source_ids:
        return {}
    code_by_id = {int(i): str(i) for i in source_ids}
    if source_type == "sales_delivery":
        from apps.kuaicaiwu.services.sales_invoice_service import SalesInvoiceService

        svc = SalesInvoiceService()
        return await svc._sum_pushed_totals_by_source(
            tenant_id, "sales_delivery", source_ids, code_by_id
        )
    if source_type == "receivable":
        from apps.kuaicaiwu.services.sales_invoice_service import SalesInvoiceService

        svc = SalesInvoiceService()
        return await svc._sum_pushed_totals_by_receivable(
            tenant_id, source_ids, code_by_id
        )
    if source_type == "purchase_receipt":
        from apps.kuaicaiwu.services.purchase_invoice_pull_service import (
            PurchaseInvoicePullService,
        )

        svc = PurchaseInvoicePullService()
        return await svc._sum_pushed_totals_by_source(
            tenant_id, "purchase_receipt", source_ids, code_by_id
        )
    if source_type == "payable":
        from apps.kuaicaiwu.services.purchase_invoice_pull_service import (
            PurchaseInvoicePullService,
        )

        svc = PurchaseInvoicePullService()
        return await svc._sum_pushed_totals_by_payable(tenant_id, source_ids, code_by_id)
    return {}


async def compute_statement_invoice_pull_metrics(
    tenant_id: int,
    *,
    side: InvoicePullSide,
    source_ids: List[int],
    source_type: str,
) -> Tuple[float, float, bool, Optional[str]]:
    amount_map = await load_source_total_amounts(tenant_id, source_type, source_ids)
    pushed_map = await sum_pushed_by_source_type(tenant_id, source_type, source_ids)
    invoiced = float(
        sum((pushed_map.get(sid, Decimal("0")) for sid in source_ids), Decimal("0"))
    )
    stmt_total = sum(
        (amount_map.get(sid, Decimal("0")) for sid in source_ids),
        Decimal("0"),
    )
    remaining = float(stmt_total) - invoiced
    allowed, reason = derive_pull_capability(
        side=side, source_ids=source_ids, remaining=remaining
    )
    return invoiced, remaining, allowed, reason


def snapshot_ids_for_api(
    snapshot: PartnerStatementInvoicePullSnapshot,
) -> Dict[str, List[int]]:
    """候选 API 字段：仅填充当前模式对应的 id 数组。"""
    payload: Dict[str, List[int]] = {
        "delivery_ids": [],
        "receivable_ids": [],
        "receipt_ids": [],
        "payable_ids": [],
    }
    st = snapshot.source_type
    ids = list(snapshot.source_ids)
    if st == "sales_delivery":
        payload["delivery_ids"] = ids
    elif st == "receivable":
        payload["receivable_ids"] = ids
    elif st == "purchase_receipt":
        payload["receipt_ids"] = ids
    elif st == "payable":
        payload["payable_ids"] = ids
    return payload