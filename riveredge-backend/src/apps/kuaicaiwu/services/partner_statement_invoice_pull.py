"""
对账单 → 购销发票加载源：按 ledger_posting_mode 过滤对账明细行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, Sequence, Set, Tuple

from infra.exceptions.exceptions import BusinessLogicError

_PARTNER_STMT_APPROVED_REVIEW = frozenset({"已审核", "approved", "APPROVED"})


def parse_partner_statement_id_csv(raw: Optional[str]) -> List[int]:
    parsed: List[int] = []
    for part in str(raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        sid = int(part)
        if sid > 0:
            parsed.append(sid)
    return parsed
_PARTNER_STMT_INVOICE_PULL_STATUSES = frozenset({"Confirmed", "Sent", "LedgerPosted"})

InvoicePullSide = Literal["sales", "purchase"]

SUPPLIER_BY_INVOICE_STATEMENT_DOC_TYPES = ("采购入库", "工序委外收货")

STATEMENT_DOC_TYPE_TO_PULL_SOURCE_TYPE: Dict[str, str] = {
    "采购入库": "purchase_receipt",
    "工序委外收货": "outsource_order_receipt",
}


@dataclass(frozen=True)
class PartnerStatementInvoicePullSnapshot:
    ledger_posting_mode: str
    doc_type: str
    source_type: str
    source_ids: List[int]
    purchase_receipt_ids: List[int] = field(default_factory=list)
    outsource_order_receipt_ids: List[int] = field(default_factory=list)


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
    ids: List[int] = []
    seen: set[int] = set()
    for ln, _amt in _iter_invoice_statement_lines(transaction_details, doc_type):
        try:
            doc_id = int(ln.get("doc_id") or ln.get("source_doc_id") or 0)
        except (TypeError, ValueError):
            continue
        if doc_id <= 0 or doc_id in seen:
            continue
        seen.add(doc_id)
        ids.append(doc_id)
    return ids


_STATEMENT_DOC_TYPE_EXTRA_SOURCE_TYPES: Dict[str, str] = {
    **STATEMENT_DOC_TYPE_TO_PULL_SOURCE_TYPE,
    "销售出库": "sales_delivery",
    "应收单": "receivable",
    "应付单": "payable",
    "委外收货": "outsource_material_receipt",
}


def _iter_invoice_statement_lines(
    transaction_details: Any,
    doc_type: str,
) -> List[Tuple[Dict[str, Any], Decimal]]:
    """按 doc_type 提取对账单可开票明细行及本次对账金额（优先 document_lines，兼容物料 lines）。"""
    if not isinstance(transaction_details, dict):
        return []
    raw_lines = transaction_details.get("document_lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        raw_lines = transaction_details.get("lines") or []
    if not isinstance(raw_lines, list):
        return []
    want = str(doc_type or "").strip()
    mapped_src = _STATEMENT_DOC_TYPE_EXTRA_SOURCE_TYPES.get(want, "")
    matched: List[Tuple[Dict[str, Any], Decimal]] = []
    for ln in raw_lines:
        if not isinstance(ln, dict):
            continue
        line_doc_type = str(ln.get("doc_type") or ln.get("doc_type_label") or "").strip()
        src_dt = str(ln.get("source_doc_type") or "").strip()
        if line_doc_type != want and not (src_dt and src_dt in (mapped_src, want)):
            continue
        if int(ln.get("tree_level") or 0) != 0:
            continue
        raw_amt = ln.get("statement_amount")
        if raw_amt is None:
            raw_amt = ln.get("debit")
        try:
            amt = Decimal(str(raw_amt or 0))
        except Exception:
            continue
        if amt <= 0:
            continue
        matched.append((ln, amt))
    return matched


def sum_statement_invoice_period_amount(transaction_details: Any, doc_type: str) -> Decimal:
    """本期可开票对账金额：明细「本次对账金额」合计（与对账单金额口径一致，默认含税）。"""
    return sum_statement_invoice_period_for_sources(transaction_details, doc_type, None)


def sum_statement_invoice_period_for_sources(
    transaction_details: Any,
    doc_type: str,
    allowed_doc_ids: Optional[Set[int]],
) -> Decimal:
    """限定源单 id 时，只合计对账单上对应行的本次对账金额。"""
    total = Decimal("0")
    for ln, amt in _iter_invoice_statement_lines(transaction_details, doc_type):
        if allowed_doc_ids is not None:
            try:
                doc_id = int(ln.get("doc_id") or ln.get("source_doc_id") or 0)
            except (TypeError, ValueError):
                continue
            if doc_id not in allowed_doc_ids:
                continue
        total += amt
    return total


@dataclass(frozen=True)
class PartnerStatementInvoiceBudget:
    """对账单→发票：唯一可开票预算（列表/预览/创建共用）。"""

    period_amount: Decimal
    source_pushable: Decimal
    invoiced: Decimal
    invoiceable: Decimal


def resolve_statement_amount_basis(transaction_details: Any) -> str:
    if not isinstance(transaction_details, dict):
        return "tax_inclusive"
    basis = str(transaction_details.get("amount_basis") or "tax_inclusive").strip()
    return basis if basis in ("tax_inclusive", "tax_exclusive") else "tax_inclusive"


def sum_supplier_by_invoice_statement_period(transaction_details: Any) -> Decimal:
    total = Decimal("0")
    for doc_type in SUPPLIER_BY_INVOICE_STATEMENT_DOC_TYPES:
        total += sum_statement_invoice_period_amount(transaction_details, doc_type)
    return total


def resolve_statement_invoice_source_ids(
    *,
    partner_type: str,
    ledger_posting_mode: Optional[str],
    transaction_details: Any,
) -> PartnerStatementInvoicePullSnapshot:
    mode = normalize_ledger_posting_mode(ledger_posting_mode)
    pt = str(partner_type or "").strip()
    purchase_receipt_ids: List[int] = []
    outsource_order_receipt_ids: List[int] = []
    if pt == "Supplier" and mode == "by_invoice":
        purchase_receipt_ids = extract_statement_source_doc_ids(
            transaction_details, "采购入库"
        )
        outsource_order_receipt_ids = extract_statement_source_doc_ids(
            transaction_details, "工序委外收货"
        )
        if purchase_receipt_ids:
            doc_type = "采购入库"
            source_type = "purchase_receipt"
            source_ids = list(purchase_receipt_ids)
        elif outsource_order_receipt_ids:
            doc_type = "工序委外收货"
            source_type = "outsource_order_receipt"
            source_ids = list(outsource_order_receipt_ids)
        else:
            doc_type = invoice_source_doc_type_for_mode(pt, mode)
            source_type = invoice_source_type_for_mode(pt, mode)
            source_ids = []
    else:
        doc_type = invoice_source_doc_type_for_mode(pt, mode)
        source_type = invoice_source_type_for_mode(pt, mode)
        source_ids = extract_statement_source_doc_ids(transaction_details, doc_type)
    return PartnerStatementInvoicePullSnapshot(
        ledger_posting_mode=mode,
        doc_type=doc_type,
        source_type=source_type,
        source_ids=source_ids,
        purchase_receipt_ids=purchase_receipt_ids,
        outsource_order_receipt_ids=outsource_order_receipt_ids,
    )


def statement_purchase_invoice_source_groups(
    snapshot: PartnerStatementInvoicePullSnapshot,
) -> List[Tuple[str, List[int]]]:
    groups: List[Tuple[str, List[int]]] = []
    if snapshot.purchase_receipt_ids:
        groups.append(("purchase_receipt", list(snapshot.purchase_receipt_ids)))
    if snapshot.outsource_order_receipt_ids:
        groups.append(("outsource_order_receipt", list(snapshot.outsource_order_receipt_ids)))
    if not groups and snapshot.source_ids:
        groups.append((snapshot.source_type, list(snapshot.source_ids)))
    return groups


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
    elif source_type == "outsource_order_receipt":
        from apps.kuaicaiwu.services.purchase_invoice_pull_service import (
            PurchaseInvoicePullService,
        )

        svc = PurchaseInvoicePullService()
        for sid in source_ids:
            gross = await svc.outsource_order_receipt_settlement_gross(tenant_id, int(sid))
            out[int(sid)] = gross
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
    if source_type == "outsource_order_receipt":
        from apps.kuaicaiwu.services.purchase_invoice_pull_service import (
            PurchaseInvoicePullService,
        )

        svc = PurchaseInvoicePullService()
        return await svc._sum_pushed_totals_by_source(
            tenant_id, "outsource_order_receipt", source_ids, code_by_id
        )
    if source_type == "payable":
        from apps.kuaicaiwu.services.purchase_invoice_pull_service import (
            PurchaseInvoicePullService,
        )

        svc = PurchaseInvoicePullService()
        return await svc._sum_pushed_totals_by_payable(tenant_id, source_ids, code_by_id)
    return {}


async def sum_source_invoice_pushable_remaining(
    tenant_id: int,
    source_type: str,
    source_ids: List[int],
) -> Decimal:
    """源单还可开票余量（与购销发票 pull-preview 同一结算口径）。"""
    if not source_ids:
        return Decimal("0")
    pushed_map = await sum_pushed_by_source_type(tenant_id, source_type, source_ids)
    total = Decimal("0")
    ids = [int(x) for x in source_ids if int(x) > 0]
    if source_type == "purchase_receipt":
        from apps.kuaicaiwu.services.purchase_settlement import (
            purchase_receipt_settlement_gross_async,
        )
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        rows = await PurchaseReceipt.filter(
            tenant_id=tenant_id,
            id__in=ids,
            deleted_at__isnull=True,
        )
        by_id = {int(r.id): r for r in rows}
        for sid in ids:
            receipt = by_id.get(sid)
            if not receipt:
                continue
            gross = await purchase_receipt_settlement_gross_async(tenant_id, receipt)
            pushed = pushed_map.get(sid, Decimal("0"))
            total += max(Decimal("0"), Decimal(str(gross or 0)) - pushed)
        return total
    if source_type == "outsource_order_receipt":
        from apps.kuaicaiwu.services.purchase_invoice_pull_service import (
            PurchaseInvoicePullService,
        )

        svc = PurchaseInvoicePullService()
        for sid in ids:
            gross = await svc.outsource_order_receipt_settlement_gross(tenant_id, int(sid))
            pushed = pushed_map.get(sid, Decimal("0"))
            total += max(Decimal("0"), gross - pushed)
        return total
    if source_type == "sales_delivery":
        from apps.kuaizhizao.models.sales_delivery import SalesDelivery

        rows = await SalesDelivery.filter(
            tenant_id=tenant_id,
            id__in=ids,
            deleted_at__isnull=True,
        )
        by_id = {int(d.id): d for d in rows}
        for sid in ids:
            delivery = by_id.get(sid)
            if not delivery:
                continue
            gross = Decimal(str(delivery.total_amount or 0))
            pushed = pushed_map.get(sid, Decimal("0"))
            total += max(Decimal("0"), gross - pushed)
        return total
    amount_map = await load_source_total_amounts(tenant_id, source_type, ids)
    for sid in ids:
        gross = amount_map.get(sid, Decimal("0"))
        pushed = pushed_map.get(sid, Decimal("0"))
        total += max(Decimal("0"), gross - pushed)
    return total


async def resolve_partner_statement_invoice_budget(
    tenant_id: int,
    *,
    side: InvoicePullSide,
    source_type: str,
    source_ids: List[int],
    statement_period_amount: Decimal,
) -> PartnerStatementInvoiceBudget:
    """
    对账单→发票：可开票以对账单为准。
    invoiceable = 本期对账金额 − 已从对应源单占用（已开票合计）。
    source_pushable 仅回显/诊断，不得再压低头表「可开票」。
    """
    ids = [int(x) for x in source_ids if int(x) > 0]
    pushed_map = await sum_pushed_by_source_type(tenant_id, source_type, ids)
    invoiced = sum((pushed_map.get(sid, Decimal("0")) for sid in ids), Decimal("0"))
    period = Decimal(str(statement_period_amount or 0))
    statement_remaining = max(Decimal("0"), period - invoiced)
    source_pushable = await sum_source_invoice_pushable_remaining(
        tenant_id, source_type, ids
    )
    invoiceable = statement_remaining
    return PartnerStatementInvoiceBudget(
        period_amount=period,
        source_pushable=source_pushable,
        invoiced=invoiced,
        invoiceable=invoiceable,
    )


async def resolve_budget_for_statements(
    tenant_id: int,
    statement_ids: Sequence[int],
    *,
    side: InvoicePullSide,
    restrict_source_ids: Optional[Sequence[int]] = None,
) -> PartnerStatementInvoiceBudget:
    """按对账单聚合本期对账额与源单 id，走唯一预算函数。"""
    from apps.kuaicaiwu.models.partner_statement import PartnerStatement

    stmt_ids = [int(x) for x in statement_ids if int(x) > 0]
    if not stmt_ids:
        raise BusinessLogicError("须指定往来对账单")
    restrict: Optional[Set[int]] = None
    if restrict_source_ids:
        restrict = {int(x) for x in restrict_source_ids if int(x) > 0}
    rows = await PartnerStatement.filter(
        tenant_id=tenant_id,
        id__in=stmt_ids,
        deleted_at__isnull=True,
    )
    if not rows:
        raise BusinessLogicError("往来对账单不存在")
    want_side = "Supplier" if side == "purchase" else "Customer"
    period = Decimal("0")
    source_ids_ordered: List[int] = []
    seen: Set[int] = set()
    source_type: Optional[str] = None
    source_groups: List[Tuple[str, List[int]]] = []
    group_seen: Dict[str, Set[int]] = {}
    for stmt in rows:
        if str(stmt.partner_type or "").strip() != want_side:
            continue
        snapshot = resolve_statement_invoice_source_ids(
            partner_type=str(stmt.partner_type or ""),
            ledger_posting_mode=stmt.ledger_posting_mode,
            transaction_details=stmt.transaction_details,
        )
        if not source_type:
            source_type = snapshot.source_type
        details = stmt.transaction_details
        if (
            side == "purchase"
            and snapshot.ledger_posting_mode == "by_invoice"
            and (snapshot.purchase_receipt_ids or snapshot.outsource_order_receipt_ids)
        ):
            for doc_type, sid_list in (
                ("采购入库", snapshot.purchase_receipt_ids),
                ("工序委外收货", snapshot.outsource_order_receipt_ids),
            ):
                allowed_ids: Optional[Set[int]] = None
                if restrict is not None:
                    allowed_ids = {int(x) for x in sid_list if int(x) in restrict}
                period += sum_statement_invoice_period_for_sources(
                    details, doc_type, allowed_ids
                )
                pull_st = STATEMENT_DOC_TYPE_TO_PULL_SOURCE_TYPE.get(doc_type)
                if not pull_st:
                    continue
                bucket = group_seen.setdefault(pull_st, set())
                for sid in sid_list:
                    sid = int(sid)
                    if sid <= 0:
                        continue
                    if restrict is not None and sid not in restrict:
                        continue
                    if sid in seen:
                        continue
                    seen.add(sid)
                    source_ids_ordered.append(sid)
                    if sid not in bucket:
                        bucket.add(sid)
            continue
        allowed = {int(x) for x in snapshot.source_ids if int(x) > 0}
        if restrict is not None:
            allowed &= restrict
        period += sum_statement_invoice_period_for_sources(
            details, snapshot.doc_type, allowed
        )
        for sid in snapshot.source_ids:
            sid = int(sid)
            if sid <= 0:
                continue
            if restrict is not None and sid not in restrict:
                continue
            if sid in seen:
                continue
            seen.add(sid)
            source_ids_ordered.append(sid)
            bucket = group_seen.setdefault(snapshot.source_type, set())
            bucket.add(sid)
    for st, id_set in group_seen.items():
        if id_set:
            source_groups.append((st, sorted(id_set)))
    if not source_type or not source_ids_ordered:
        raise BusinessLogicError("对账单无可用于开票的源单")
    if len(source_groups) > 1:
        invoiced = Decimal("0")
        source_pushable = Decimal("0")
        for st, ids in source_groups:
            pushed_map = await sum_pushed_by_source_type(tenant_id, st, ids)
            invoiced += sum((pushed_map.get(i, Decimal("0")) for i in ids), Decimal("0"))
            source_pushable += await sum_source_invoice_pushable_remaining(
                tenant_id, st, ids
            )
        invoiceable = max(Decimal("0"), period - invoiced)
        return PartnerStatementInvoiceBudget(
            period_amount=period,
            source_pushable=source_pushable,
            invoiced=invoiced,
            invoiceable=invoiceable,
        )
    return await resolve_partner_statement_invoice_budget(
        tenant_id,
        side=side,
        source_type=source_type,
        source_ids=source_ids_ordered,
        statement_period_amount=period,
    )


def resolve_pull_preview_invoice_cap(preview: Dict[str, Any]) -> Decimal:
    """
    列表 / 预览 / 保存共用：可开票价税合计上限。
    优先对账单唯一预算字段，其次 max_push_total，再按明细行合计。
    """
    budget_cap = preview.get("partner_statement_invoice_budget")
    if budget_cap is not None:
        return Decimal(str(budget_cap))
    raw_total = preview.get("max_push_total")
    if raw_total is not None:
        return Decimal(str(raw_total))
    items = preview.get("items") or []
    return sum(
        (Decimal(str(item.get("max_push_quantity") or 0)) for item in items),
        Decimal("0"),
    )


def apply_invoice_budget_to_pull_preview(
    preview: Dict[str, Any],
    budget: PartnerStatementInvoiceBudget,
) -> None:
    """将 pull-preview 价税上限钉死在唯一预算上（含明细行按比收缩）。"""
    cap = budget.invoiceable
    cap_f = float(cap)
    preview["partner_statement_invoice_budget"] = cap_f
    preview["statement_period_amount"] = float(budget.period_amount)
    preview["source_invoice_pushable"] = float(budget.source_pushable)
    items = preview.get("items") or []
    items_sum = sum(
        Decimal(str(item.get("max_push_quantity") or 0)) for item in items
    )
    if items_sum <= 0:
        preview["max_push_total"] = cap_f
        if cap_f <= 0:
            preview["has_blocking_issues"] = True
        return
    if cap >= items_sum:
        preview["max_push_total"] = cap_f
        if cap > items_sum and items_sum > 0:
            ratio = cap / items_sum
            for item in items:
                item["max_push_quantity"] = float(
                    (Decimal(str(item.get("max_push_quantity") or 0)) * ratio).quantize(
                        Decimal("0.01")
                    )
                )
            for line in preview.get("detail_lines") or []:
                for key in ("max_push_amount", "max_push_quantity"):
                    if key not in line or line[key] is None:
                        continue
                    line[key] = float(
                        (Decimal(str(line[key])) * ratio).quantize(Decimal("0.01"))
                    )
        return
    ratio = cap / items_sum
    for item in items:
        item["max_push_quantity"] = float(
            (Decimal(str(item.get("max_push_quantity") or 0)) * ratio).quantize(
                Decimal("0.01")
            )
        )
    for line in preview.get("detail_lines") or []:
        for key in ("max_push_amount", "max_push_quantity"):
            if key not in line or line[key] is None:
                continue
            line[key] = float(
                (Decimal(str(line[key])) * ratio).quantize(Decimal("0.01"))
            )
    preview["max_push_total"] = cap_f


def scale_line_push_caps_to_header(
    max_by_item: Dict[int, Decimal],
    header_amount: Decimal,
) -> Dict[int, Decimal]:
    """对账单开票：行分摊上限随表头价税合计同比放大，使落库校验以对账单为准。"""
    if not max_by_item:
        return max_by_item
    header = Decimal(str(header_amount or 0))
    if header <= 0:
        return max_by_item
    total = sum(max_by_item.values(), Decimal("0"))
    if total <= 0 or header <= total:
        return max_by_item
    ratio = header / total
    scaled: Dict[int, Decimal] = {
        int(k): (v * ratio).quantize(Decimal("0.01")) for k, v in max_by_item.items()
    }
    drift = header - sum(scaled.values(), Decimal("0"))
    if drift and scaled:
        top_key = max(scaled, key=lambda key: scaled[key])
        scaled[top_key] = scaled[top_key] + drift
    return scaled


async def statement_scaled_receipt_line_caps(
    tenant_id: int,
    receipt_id: int,
    *,
    header_amount: Decimal,
) -> Dict[int, Decimal]:
    from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
        build_purchase_receipt_finance_detail_lines,
    )

    detail = await build_purchase_receipt_finance_detail_lines(
        tenant_id, int(receipt_id), "invoice"
    )
    max_by = {
        int(d["purchase_receipt_item_id"]): Decimal(str(d.get("max_push_amount") or 0))
        for d in detail
    }
    return scale_line_push_caps_to_header(max_by, header_amount)


async def enforce_partner_statement_invoice_total(
    tenant_id: int,
    statement_ids: Sequence[int],
    *,
    side: InvoicePullSide,
    restrict_source_ids: Sequence[int],
    total_amount: Decimal,
) -> PartnerStatementInvoiceBudget:
    budget = await resolve_budget_for_statements(
        tenant_id,
        statement_ids,
        side=side,
        restrict_source_ids=restrict_source_ids,
    )
    if total_amount > budget.invoiceable:
        raise BusinessLogicError(
            f"价税合计 {total_amount} 超过对账单可开票金额 {budget.invoiceable}"
        )
    return budget


async def compute_statement_invoice_pull_metrics(
    tenant_id: int,
    *,
    side: InvoicePullSide,
    source_ids: List[int],
    source_type: str,
    statement_period_amount: Optional[Decimal] = None,
    snapshot: Optional[PartnerStatementInvoicePullSnapshot] = None,
) -> Tuple[float, float, bool, Optional[str]]:
    groups = statement_purchase_invoice_source_groups(snapshot) if snapshot else []
    if not groups:
        groups = [(source_type, source_ids)] if source_ids else []
    period = statement_period_amount
    if period is None:
        amount_map = await load_source_total_amounts(tenant_id, source_type, source_ids)
        period = sum(
            (amount_map.get(sid, Decimal("0")) for sid in source_ids),
            Decimal("0"),
        )
    if len(groups) > 1 or (
        groups
        and snapshot
        and side == "purchase"
        and snapshot.ledger_posting_mode == "by_invoice"
        and (snapshot.purchase_receipt_ids and snapshot.outsource_order_receipt_ids)
    ):
        invoiced = Decimal("0")
        for st, ids in groups:
            pushed_map = await sum_pushed_by_source_type(tenant_id, st, ids)
            invoiced += sum((pushed_map.get(i, Decimal("0")) for i in ids), Decimal("0"))
        invoiceable = max(Decimal("0"), Decimal(str(period or 0)) - invoiced)
        all_ids = [i for _, id_list in groups for i in id_list]
        remaining = float(invoiceable)
        allowed, reason = derive_pull_capability(
            side=side, source_ids=all_ids, remaining=remaining
        )
        return float(invoiced), remaining, allowed, reason
    budget = await resolve_partner_statement_invoice_budget(
        tenant_id,
        side=side,
        source_type=source_type,
        source_ids=source_ids,
        statement_period_amount=Decimal(str(period or 0)),
    )
    remaining = float(budget.invoiceable)
    allowed, reason = derive_pull_capability(
        side=side, source_ids=source_ids, remaining=remaining
    )
    return float(budget.invoiced), remaining, allowed, reason


async def _covered_source_ids_from_statements(
    tenant_id: int,
    statement_ids: Sequence[int],
    *,
    side: InvoicePullSide,
) -> Set[int]:
    """已审核且按发票立账的对账单所引用的源单 id（采购入库/销售出库）。"""
    if not statement_ids:
        return set()
    from apps.kuaicaiwu.models.partner_statement import PartnerStatement

    covered: Set[int] = set()
    rows = await PartnerStatement.filter(
        tenant_id=tenant_id,
        id__in=[int(x) for x in statement_ids if int(x) > 0],
        deleted_at__isnull=True,
    )
    for stmt in rows:
        review = str(stmt.review_status or "").strip()
        if review not in _PARTNER_STMT_APPROVED_REVIEW:
            continue
        if str(stmt.status or "").strip() not in _PARTNER_STMT_INVOICE_PULL_STATUSES:
            continue
        mode = normalize_ledger_posting_mode(stmt.ledger_posting_mode)
        if mode != "by_invoice":
            continue
        snapshot = resolve_statement_invoice_source_ids(
            partner_type=str(stmt.partner_type or ""),
            ledger_posting_mode=mode,
            transaction_details=stmt.transaction_details,
        )
        if side == "purchase":
            covered.update(int(x) for x in snapshot.purchase_receipt_ids if int(x) > 0)
            covered.update(
                int(x) for x in snapshot.outsource_order_receipt_ids if int(x) > 0
            )
            if not snapshot.purchase_receipt_ids and not snapshot.outsource_order_receipt_ids:
                if snapshot.source_type in ("purchase_receipt", "outsource_order_receipt"):
                    covered.update(int(x) for x in snapshot.source_ids if int(x) > 0)
            continue
        expected_source_type = "sales_delivery"
        if snapshot.source_type != expected_source_type:
            continue
        covered.update(int(x) for x in snapshot.source_ids if int(x) > 0)
    return covered


async def receipts_covered_by_audited_partner_statements(
    tenant_id: int,
    statement_ids: Sequence[int],
    receipt_ids: Sequence[int],
) -> bool:
    wanted = {int(x) for x in receipt_ids if int(x) > 0}
    if not wanted:
        return False
    covered = await _covered_source_ids_from_statements(
        tenant_id, statement_ids, side="purchase"
    )
    return wanted <= covered


async def deliveries_covered_by_audited_partner_statements(
    tenant_id: int,
    statement_ids: Sequence[int],
    delivery_ids: Sequence[int],
) -> bool:
    wanted = {int(x) for x in delivery_ids if int(x) > 0}
    if not wanted:
        return False
    covered = await _covered_source_ids_from_statements(
        tenant_id, statement_ids, side="sales"
    )
    return wanted <= covered


def snapshot_ids_for_api(
    snapshot: PartnerStatementInvoicePullSnapshot,
) -> Dict[str, List[int]]:
    """候选 API 字段：仅填充当前模式对应的 id 数组。"""
    payload: Dict[str, List[int]] = {
        "delivery_ids": [],
        "receivable_ids": [],
        "receipt_ids": list(snapshot.purchase_receipt_ids or []),
        "payable_ids": [],
        "outsource_order_receipt_ids": list(snapshot.outsource_order_receipt_ids or []),
    }
    st = snapshot.source_type
    ids = list(snapshot.source_ids)
    if st == "sales_delivery":
        payload["delivery_ids"] = ids
    elif st == "receivable":
        payload["receivable_ids"] = ids
    elif st == "purchase_receipt":
        if not payload["receipt_ids"]:
            payload["receipt_ids"] = ids
    elif st == "outsource_order_receipt":
        if not payload["outsource_order_receipt_ids"]:
            payload["outsource_order_receipt_ids"] = ids
    elif st == "payable":
        payload["payable_ids"] = ids
    return payload