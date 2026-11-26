"""
往来对账单业务服务
"""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from tortoise.expressions import Q
from tortoise import timezone as tortoise_timezone

from apps.common.audit_actor import apply_update_audit
from apps.common.base_service import AppBaseService
from apps.kuaicaiwu.constants.finance_source_types import (
    PAYABLE_SOURCE_OUTSOURCE_RECEIPT,
    PAYABLE_SOURCE_PARTNER_STATEMENT,
    PAYABLE_SOURCE_PURCHASE_RECEIPT,
    PAYABLE_SOURCE_PURCHASE_RETURN,
    RECEIVABLE_SOURCE_PARTNER_STATEMENT,
    RECEIVABLE_SOURCE_SALES_DELIVERY,
    RECEIVABLE_SOURCE_SALES_RETURN,
)
from apps.kuaicaiwu.models.partner_statement import PartnerStatement
from apps.kuaicaiwu.models.payable import Payable
from apps.kuaicaiwu.models.payment import Payment
from apps.kuaicaiwu.models.receivable import Receivable
from apps.kuaicaiwu.models.receipt import Receipt
from apps.kuaicaiwu.services.finance_settlement_hierarchy import order_lines_by_settlement_hierarchy
from apps.kuaicaiwu.services.finance_refund_utils import (
    SETTLEMENT_CREDIT_PURCHASE_RETURN_OFFSET,
    SETTLEMENT_CREDIT_SALES_RETURN_OFFSET,
)
from apps.master_data.models.customer import Customer
from apps.master_data.models.supplier import Supplier
from core.config.finance_recognition import PARTNER_STATEMENT_LEDGER_MODES
from core.utils.timezone_utils import to_api_isoformat, today_site_str
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.models.tenant import Tenant
from infra.models.user import User

_APPROVED_REVIEW = ("已审核",)
_EXCLUDED_REVIEW = ("待审核", "驳回", "已驳回", "rejected", "审核驳回")
_MONEY = Decimal("0.01")

# 对账单行 doc_type → 稳定族，用于「已纳入其它对账单」去重
_DOC_TYPE_FAMILY: Dict[str, str] = {
    "应收单": "receivable",
    "销售退货": "receivable",
    "销售出库": "sales_delivery",
    "收款单": "receipt",
    "收款退款": "receipt",
    "应付单": "payable",
    "采购退货": "payable",
    "采购入库": "purchase_receipt",
    "付款单": "payment",
    "付款退款": "payment",
    "工序委外收货": "outsource_process_receipt",
    "委外收货": "outsource_material_receipt",
}


def _q_money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value or 0)).quantize(_MONEY)


def _is_refund_voucher(settlement_type: Optional[str], total_amount: Decimal) -> bool:
    return (settlement_type or "normal") == "refund" or total_amount < 0


def _line_doc_key(doc_type: Any, doc_id: Any) -> Optional[Tuple[str, int]]:
    if doc_id is None:
        return None
    family = _DOC_TYPE_FAMILY.get(str(doc_type or "").strip())
    if not family:
        return None
    try:
        return family, int(doc_id)
    except (TypeError, ValueError):
        return None


def _abs_money(value: Decimal | float | int | str) -> Decimal:
    return abs(_q_money(value))


def _net_statement_ledger_amount(lines: List[Dict[str, Any]]) -> Decimal:
    """对账立账整单金额：借贷方向合并本次对账金额。"""
    net = Decimal("0")
    for ln in lines:
        stmt_amt = _q_money(ln.get("statement_amount") or ln.get("doc_amount") or 0)
        if stmt_amt <= 0:
            continue
        debit = _q_money(ln.get("debit", 0))
        credit = _q_money(ln.get("credit", 0))
        if credit > debit:
            net -= stmt_amt
        else:
            net += stmt_amt
    return _q_money(net)


def _coerce_statement_sort_date(value: Any) -> date:
    """排序键统一为 date；未立账源单仅带 ISO 字符串 date，须与 ORM date 可比较。"""
    if value is None:
        return date.min
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return date.min
    return date.fromisoformat(text[:10])


def _statement_line_sort_key(ln: Dict[str, Any]) -> Tuple[date, str, int]:
    """对账单明细排序键；未立账源单行可能在查询服务内已去掉 sort_date。"""
    sd_raw = ln.get("sort_date")
    if sd_raw is None:
        sd_raw = ln.get("date")
    sort_date = _coerce_statement_sort_date(sd_raw)
    doc_type = str(ln.get("doc_type") or "")
    try:
        doc_id = int(ln.get("doc_id") or 0)
    except (TypeError, ValueError):
        doc_id = 0
    return (sort_date, doc_type, doc_id)


AMOUNT_BASIS_TAX_INCLUSIVE = "tax_inclusive"
AMOUNT_BASIS_TAX_EXCLUSIVE = "tax_exclusive"


def parse_statement_amount_basis(value: Optional[str]) -> str:
    basis = str(value or AMOUNT_BASIS_TAX_INCLUSIVE).strip()
    if basis not in (AMOUNT_BASIS_TAX_INCLUSIVE, AMOUNT_BASIS_TAX_EXCLUSIVE):
        raise ValidationError("amount_basis 须为 tax_inclusive 或 tax_exclusive")
    return basis

def _rewrite_line_stored_amount_basis(ln: Dict[str, Any], amount_basis: str) -> None:
    """单据金额已等于未税或价税合计时，改到本次口径。不改已经部分对账的金额。"""
    if ln.get("amount_excluding_tax") is None or ln.get("amount_including_tax") is None:
        return
    excl = _q_money(ln["amount_excluding_tax"])
    incl = _q_money(ln["amount_including_tax"])
    current = _line_doc_amount(ln)
    if current != excl and current != incl:
        return
    target = incl if amount_basis != AMOUNT_BASIS_TAX_EXCLUSIVE else excl
    is_credit = _q_money(ln.get("credit", 0)) > 0 and _q_money(ln.get("debit", 0)) <= 0
    ln["doc_amount"] = float(target)
    ln["debit"] = 0.0 if is_credit else float(target)
    ln["credit"] = float(target) if is_credit else 0.0


def _line_doc_amount(ln: Dict[str, Any]) -> Decimal:
    if ln.get("doc_amount") is not None:
        return _abs_money(ln["doc_amount"])
    debit = _q_money(ln.get("debit", 0))
    credit = _q_money(ln.get("credit", 0))
    return debit if debit > 0 else credit


def _line_statement_amount(ln: Dict[str, Any]) -> Decimal:
    if ln.get("statement_amount") is not None:
        return _q_money(ln["statement_amount"])
    return _line_doc_amount(ln)


def collapse_material_lines_to_document_lines(
    lines: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """物料粒度行合并为单据头展示行（列表按单号一行，展开再看明细）。"""
    from apps.kuaicaiwu.config.finance_settlement_contract import (
        PARTNER_STATEMENT_LINE_KIND_MATERIAL,
    )

    if not lines:
        return []
    if not any(
        str(ln.get("line_kind") or "").strip() == PARTNER_STATEMENT_LINE_KIND_MATERIAL
        for ln in lines
    ):
        return [dict(ln) for ln in lines]

    groups: Dict[Tuple[str, int], Dict[str, Any]] = {}
    order: List[Tuple[str, int]] = []
    passthrough: List[Dict[str, Any]] = []

    material_field_keys = frozenset(
        {
            "material_id",
            "material_code",
            "material_name",
            "material_spec",
            "unit",
            "quantity",
            "source_line_id",
            "line_kind",
            "invoice_occupied_amount",
            "invoiceable_amount",
        }
    )

    ordered_out: List[Dict[str, Any]] = []
    for ln in lines:
        if str(ln.get("line_kind") or "").strip() != PARTNER_STATEMENT_LINE_KIND_MATERIAL:
            ordered_out.append(dict(ln))
            continue
        key = _line_doc_key(ln.get("doc_type"), ln.get("doc_id"))
        if not key:
            ordered_out.append(dict(ln))
            continue
        stmt = _line_statement_amount(ln)
        if key not in groups:
            base = {
                k: v
                for k, v in ln.items()
                if k not in material_field_keys
            }
            base["doc_amount"] = 0.0
            base["statement_amount"] = 0.0
            base["prior_stated_amount"] = 0.0
            base["remaining_amount"] = 0.0
            base["debit"] = 0.0
            base["credit"] = 0.0
            groups[key] = base
            order.append(key)
            ordered_out.append(base)
        row = groups[key]
        row["doc_amount"] = float(
            _q_money(Decimal(str(row.get("doc_amount") or 0)) + _q_money(ln.get("doc_amount")))
        )
        row["statement_amount"] = float(_q_money(Decimal(str(row["statement_amount"])) + stmt))
        row["prior_stated_amount"] = float(
            _q_money(
                Decimal(str(row.get("prior_stated_amount") or 0))
                + _q_money(ln.get("prior_stated_amount"))
            )
        )
        row["remaining_amount"] = float(
            _q_money(
                Decimal(str(row.get("remaining_amount") or 0))
                + _q_money(ln.get("remaining_amount"))
            )
        )
        ln_debit = _q_money(ln.get("debit", 0))
        ln_credit = _q_money(ln.get("credit", 0))
        is_debit = ln_debit > 0 or (ln_debit == 0 and ln_credit == 0)
        if is_debit:
            row["debit"] = float(_q_money(Decimal(str(row.get("debit") or 0)) + stmt))
        else:
            row["credit"] = float(_q_money(Decimal(str(row.get("credit") or 0)) + stmt))

    return ordered_out


def _line_is_debit_side(ln: Dict[str, Any]) -> bool:
    return _q_money(ln.get("debit", 0)) > 0


def _apply_statement_amount_to_line(
    ln: Dict[str, Any],
    statement_amount: Decimal,
    doc_amount: Decimal,
    prior_stated: Decimal,
    remaining: Decimal,
) -> Dict[str, Any]:
    row = dict(ln)
    row["doc_amount"] = float(doc_amount)
    row["prior_stated_amount"] = float(prior_stated)
    row["remaining_amount"] = float(remaining)
    row["statement_amount"] = float(statement_amount)
    amt = float(statement_amount)
    if _line_is_debit_side(ln):
        row["debit"] = amt
        row["credit"] = 0.0
    else:
        row["debit"] = 0.0
        row["credit"] = amt
    return row


def _normalize_statement_line_amounts(ln: Dict[str, Any]) -> Dict[str, Any]:
    """旧快照补齐单据/已对/未对/本次对账金额字段。"""
    row = dict(ln)
    doc_amount = _line_doc_amount(row)
    prior = _q_money(row.get("prior_stated_amount", 0))
    statement_amount = _line_statement_amount(row)
    remaining = _q_money(doc_amount - prior)
    return _apply_statement_amount_to_line(row, statement_amount, doc_amount, prior, remaining)


def _extract_waste_quantities(other_checks: Any) -> Tuple[Optional[float], Optional[float]]:
    """从检验 other_checks JSON 提取工废/料废数量。"""
    if not isinstance(other_checks, dict):
        return None, None

    def _pick(*keys: str) -> Optional[float]:
        for key in keys:
            val = other_checks.get(key)
            if val is not None and val != "":
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
        return None

    process_waste = _pick("process_waste_qty", "process_waste", "工废", "工废数量")
    material_waste = _pick("material_waste_qty", "material_waste", "料废", "料废数量")
    return process_waste, material_waste


def _inspection_passed(inspection: Any) -> Optional[bool]:
    if inspection is None:
        return None
    result = str(getattr(inspection, "inspection_result", "") or "").strip()
    quality = str(getattr(inspection, "quality_status", "") or "").strip()
    if result in ("合格", "通过") or quality == "合格":
        return True
    if result in ("不合格", "未通过", "拒收") or quality == "不合格":
        return False
    return None


def period_to_date_range(period: str) -> Tuple[date, date]:
    """YYYY-MM -> (月初, 月末)"""
    try:
        year_s, month_s = period.split("-", 1)
        year, month = int(year_s), int(month_s)
    except (ValueError, AttributeError) as e:
        raise ValidationError("对账周期格式应为 YYYY-MM") from e
    if month < 1 or month > 12:
        raise ValidationError("对账周期月份无效")
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    return start, end


class PartnerStatementService(AppBaseService[PartnerStatement]):
    """往来对账单服务

    对账单明细行 doc_type 与前端展示说明（唯一文案来源）：
    - 应收单：销售出库/开票等正向应收
    - 收款单：客户正常收款（贷方）
    - 收款退款：settlement_type=refund 或负金额收款（借方冲回）
    - 销售退货：销售退货关联红字应收（贷方冲减）
    - 应付单：采购入库/委外等正向应付
    - 付款单：供应商正常付款（贷方）
    - 付款退款：settlement_type=refund 或负金额付款（借方冲回）
    - 采购退货：采购退货关联红字应付（贷方冲减）
    """

    async def _get_tenant_company_name(self, tenant_id: int) -> str:
        tenant = await Tenant.get_or_none(id=tenant_id)
        return (tenant.name if tenant else "") or "本公司"

    async def _load_partner_snapshot(
        self, tenant_id: int, partner_id: int, partner_type: str
    ) -> Dict[str, Any]:
        if partner_type == "Customer":
            obj = await Customer.get_or_none(tenant_id=tenant_id, id=partner_id, deleted_at__isnull=True)
            if not obj:
                raise NotFoundError(f"客户不存在: {partner_id}")
            return {
                "id": obj.id,
                "name": obj.name or str(partner_id),
                "finance_contact_name": getattr(obj, "finance_contact_name", None),
                "finance_contact_phone": getattr(obj, "finance_contact_phone", None),
                "finance_contact_email": getattr(obj, "finance_contact_email", None),
            }
        if partner_type in ("Supplier", "Outsource"):
            obj = await Supplier.get_or_none(tenant_id=tenant_id, id=partner_id, deleted_at__isnull=True)
            if not obj:
                raise NotFoundError(f"供应商不存在: {partner_id}")
            return {
                "id": obj.id,
                "name": obj.name or str(partner_id),
                "finance_contact_name": getattr(obj, "finance_contact_name", None),
                "finance_contact_phone": getattr(obj, "finance_contact_phone", None),
                "finance_contact_email": getattr(obj, "finance_contact_email", None),
            }
        raise ValidationError("partner_type 必须为 Customer、Supplier 或 Outsource")

    # 对账明细中属「按月结对账单立账」业务源单的类型（与预览真源一致）
    _STATEMENT_LEDGER_LINE_DOC_TYPES = frozenset(
        {
            "采购入库",
            "采购退货",
            "销售出库",
            "销售退货",
            "委外收货",
            "工序委外收货",
        }
    )

    async def _partner_uses_statement_ledger(
        self, tenant_id: int, partner_id: int, partner_type: str
    ) -> bool:
        from infra.services.business_config_service import BusinessConfigService

        cfg = BusinessConfigService()
        if partner_type == "Customer":
            resolved = await cfg.resolve_revenue_recognition(tenant_id, partner_id)
            return resolved == "on_partner_statement"
        if partner_type == "Outsource":
            return True
        resolved = await cfg.resolve_payable_recognition(tenant_id, partner_id)
        return resolved == "on_partner_statement"

    @classmethod
    def _lines_support_statement_ledger(cls, lines: Any) -> bool:
        if not isinstance(lines, list):
            return False
        for ln in lines:
            if not isinstance(ln, dict):
                continue
            if int(ln.get("tree_level") or 0) > 0:
                continue
            if str(ln.get("doc_type") or "").strip() in cls._STATEMENT_LEDGER_LINE_DOC_TYPES:
                return True
        return False

    async def _statement_supports_ledger_modes(self, obj: PartnerStatement) -> bool:
        """客商默认按月结，或本单明细已是月结业务源单时，允许选立即/按发票立账。"""
        if await self._partner_uses_statement_ledger(
            int(obj.tenant_id), int(obj.partner_id), str(obj.partner_type)
        ):
            return True
        details = obj.transaction_details or {}
        return self._lines_support_statement_ledger(
            details.get("lines") if isinstance(details, dict) else None
        )

    def _approved_doc_filter(self) -> Q:
        return Q(review_status__in=_APPROVED_REVIEW) | Q(review_status__isnull=True)

    async def _sum_debits_before(
        self, tenant_id: int, partner_id: int, partner_type: str, before_date: date
    ) -> Decimal:
        total = Decimal("0")
        if partner_type == "Customer":
            rows = await Receivable.filter(
                tenant_id=tenant_id,
                customer_id=partner_id,
                business_date__lt=before_date,
                deleted_at__isnull=True,
            ).exclude(review_status__in=_EXCLUDED_REVIEW).exclude(
                source_type=RECEIVABLE_SOURCE_SALES_RETURN
            ).all()
            total += sum((r.total_amount for r in rows), Decimal("0"))

            receipts = await Receipt.filter(
                tenant_id=tenant_id,
                customer_id=partner_id,
                receipt_date__lt=before_date,
                status="Confirmed",
                deleted_at__isnull=True,
            ).all()
            for r in receipts:
                amt = _q_money(r.total_amount)
                if _is_refund_voucher(getattr(r, "settlement_type", None), amt):
                    total += _abs_money(amt)
        else:
            rows = await Payable.filter(
                tenant_id=tenant_id,
                supplier_id=partner_id,
                business_date__lt=before_date,
                deleted_at__isnull=True,
            ).exclude(review_status__in=_EXCLUDED_REVIEW).all()
            total += sum((p.total_amount for p in rows), Decimal("0"))

            payments = await Payment.filter(
                tenant_id=tenant_id,
                supplier_id=partner_id,
                payment_date__lt=before_date,
                status="Confirmed",
                deleted_at__isnull=True,
            ).all()
            for p in payments:
                amt = _q_money(p.total_amount)
                if _is_refund_voucher(getattr(p, "settlement_type", None), amt):
                    total += _abs_money(amt)
        return _q_money(total)

    async def _sum_credits_before(
        self, tenant_id: int, partner_id: int, partner_type: str, before_date: date
    ) -> Decimal:
        total = Decimal("0")
        if partner_type == "Customer":
            rows = await Receipt.filter(
                tenant_id=tenant_id,
                customer_id=partner_id,
                receipt_date__lt=before_date,
                status="Confirmed",
                deleted_at__isnull=True,
            ).all()
            for r in rows:
                amt = _q_money(r.total_amount)
                if not _is_refund_voucher(getattr(r, "settlement_type", None), amt):
                    total += _abs_money(amt)

            return_rows = await Receivable.filter(
                tenant_id=tenant_id,
                customer_id=partner_id,
                business_date__lt=before_date,
                deleted_at__isnull=True,
                source_type=RECEIVABLE_SOURCE_SALES_RETURN,
            ).exclude(review_status__in=_EXCLUDED_REVIEW).all()
            total += sum((r.total_amount for r in return_rows), Decimal("0"))
        else:
            rows = await Payment.filter(
                tenant_id=tenant_id,
                supplier_id=partner_id,
                payment_date__lt=before_date,
                status="Confirmed",
                deleted_at__isnull=True,
            ).all()
            for p in rows:
                amt = _q_money(p.total_amount)
                if not _is_refund_voucher(getattr(p, "settlement_type", None), amt):
                    total += _abs_money(amt)

        return _q_money(total)

    async def _attach_purchase_receipt_amount_parts(
        self, tenant_id: int, lines: List[Dict[str, Any]]
    ) -> None:
        """应付单若来自采购入库，带上入库单已保存的未税、税额、价税合计。不改应付账面金额。"""
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        receipt_ids: List[int] = []
        for ln in lines:
            if ln.get("amount_including_tax") is not None and ln.get("amount_excluding_tax") is not None:
                continue
            rid = None
            if ln.get("inbound_detail_doc_type") == "purchase_receipt":
                rid = ln.get("inbound_detail_doc_id")
            elif ln.get("doc_type") == "采购入库":
                rid = ln.get("doc_id")
            if rid:
                receipt_ids.append(int(rid))
        if not receipt_ids:
            return
        rows = await PurchaseReceipt.filter(
            tenant_id=tenant_id, id__in=list(set(receipt_ids)), deleted_at__isnull=True
        ).all()
        by_id = {int(p.id): p for p in rows}
        for ln in lines:
            if ln.get("amount_including_tax") is not None and ln.get("amount_excluding_tax") is not None:
                continue
            rid = None
            if ln.get("inbound_detail_doc_type") == "purchase_receipt":
                rid = ln.get("inbound_detail_doc_id")
            elif ln.get("doc_type") == "采购入库":
                rid = ln.get("doc_id")
            if not rid or int(rid) not in by_id:
                continue
            receipt = by_id[int(rid)]
            excl = _q_money(receipt.total_amount)
            tax = _q_money(receipt.tax_amount)
            incl = _q_money(receipt.net_amount)
            if incl <= 0:
                incl = excl
            ln["amount_excluding_tax"] = float(excl)
            ln["tax_amount"] = float(tax)
            ln["amount_including_tax"] = float(incl)

    async def _calc_opening_balance(
        self,
        tenant_id: int,
        partner_id: int,
        partner_type: str,
        start_date: date,
        amount_basis: str = AMOUNT_BASIS_TAX_INCLUSIVE,
    ) -> Decimal:
        debits = await self._sum_debits_before(tenant_id, partner_id, partner_type, start_date)
        credits = await self._sum_credits_before(tenant_id, partner_id, partner_type, start_date)
        opening = _q_money(debits - credits)
        from apps.kuaizhizao.services.finance_settlement_source_query import (
            FinanceSettlementSourceQuery,
        )

        q = FinanceSettlementSourceQuery()
        partner_uses_statement_ledger = await self._partner_uses_statement_ledger(
            tenant_id, partner_id, partner_type
        )
        # 单据头为按月结的未立账源单：无论客商默认是否按月结，都并入期初（单据字段为真源）
        if partner_type == "Customer":
            opening += await q.sum_customer_unposted_debits_before(
                tenant_id,
                partner_id,
                start_date,
                require_statement_strategy=not partner_uses_statement_ledger,
            )
        else:
            opening += await q.sum_supplier_unposted_debits_before(
                tenant_id,
                partner_id,
                start_date,
                tax_inclusive=amount_basis != AMOUNT_BASIS_TAX_EXCLUSIVE,
            )
        if not partner_uses_statement_ledger:
            opening += await self._purchase_receipt_payable_basis_delta(
                tenant_id, partner_id, partner_type, start_date, amount_basis
            )
        return _q_money(opening)

    async def _purchase_receipt_payable_basis_delta(
        self,
        tenant_id: int,
        partner_id: int,
        partner_type: str,
        before_date: date,
        amount_basis: str,
    ) -> Decimal:
        """应付账面等于入库未税或价税合计时，期初改到同一口径。"""
        if partner_type == "Customer":
            return Decimal("0")
        rows = await Payable.filter(
            tenant_id=tenant_id,
            supplier_id=partner_id,
            business_date__lt=before_date,
            deleted_at__isnull=True,
        ).exclude(review_status__in=_EXCLUDED_REVIEW).all()
        matched: List[Payable] = []
        receipt_ids: List[int] = []
        for payable in rows:
            src = str(payable.source_type or "").strip()
            if not payable.source_id:
                continue
            if src not in (
                PAYABLE_SOURCE_PURCHASE_RECEIPT,
                "purchase_receipt",
                "PurchaseReceipt",
            ):
                continue
            matched.append(payable)
            receipt_ids.append(int(payable.source_id))
        if not matched:
            return Decimal("0")
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        receipts = await PurchaseReceipt.filter(
            tenant_id=tenant_id, id__in=list(set(receipt_ids))
        ).all()
        by_id = {int(receipt.id): receipt for receipt in receipts}
        delta = Decimal("0")
        for payable in matched:
            receipt = by_id.get(int(payable.source_id))
            if receipt is None:
                continue
            excl = _q_money(receipt.total_amount)
            incl = _q_money(receipt.net_amount)
            if incl <= 0:
                incl = excl
            signed = _q_money(payable.total_amount)
            magnitude = _abs_money(signed)
            if magnitude != excl and magnitude != incl:
                continue
            target = incl if amount_basis != AMOUNT_BASIS_TAX_EXCLUSIVE else excl
            signed_target = target if signed >= 0 else -target
            delta += signed_target - signed
        return _q_money(delta)

    async def _collect_statement_ledger_period_lines(
        self,
        tenant_id: int,
        partner_id: int,
        partner_type: str,
        start_date: date,
        end_date: date,
        amount_basis: str = AMOUNT_BASIS_TAX_INCLUSIVE,
    ) -> List[Dict[str, Any]]:
        """对账本期明细唯一来源：单据头为按月结对账单的未立账业务源单。

        不含应付单/付款单/应收单/收款单；期初余额仍可由历史收付反映。
        """
        from apps.kuaizhizao.services.finance_settlement_source_query import (
            FinanceSettlementSourceQuery,
        )

        q = FinanceSettlementSourceQuery()
        lines: List[Dict[str, Any]] = []
        if partner_type == "Customer":
            lines.extend(
                await q.list_customer_unposted_lines(
                    tenant_id,
                    partner_id,
                    start_date,
                    end_date,
                    require_statement_strategy=True,
                )
            )
        elif partner_type == "Outsource":
            lines.extend(
                await q.list_outsource_supplier_unposted_lines(
                    tenant_id, partner_id, start_date, end_date
                )
            )
        else:
            lines.extend(
                await q.list_supplier_unposted_lines(
                    tenant_id,
                    partner_id,
                    start_date,
                    end_date,
                    tax_inclusive=amount_basis != AMOUNT_BASIS_TAX_EXCLUSIVE,
                )
            )
        lines.sort(key=_statement_line_sort_key)
        for ln in lines:
            ln.pop("sort_date", None)
        await self._attach_purchase_receipt_amount_parts(tenant_id, lines)
        for ln in lines:
            _rewrite_line_stored_amount_basis(ln, amount_basis)
        return lines

    async def _collect_period_raw_lines(
        self,
        tenant_id: int,
        partner_id: int,
        partner_type: str,
        start_date: date,
        end_date: date,
        amount_basis: str = AMOUNT_BASIS_TAX_INCLUSIVE,
    ) -> List[Dict[str, Any]]:
        # 对账来源只认月结业务源单，与客商默认立账策略无关；禁止再扫应付/付款等凭证
        return await self._collect_statement_ledger_period_lines(
            tenant_id, partner_id, partner_type, start_date, end_date, amount_basis
        )

    async def _order_lines_by_settlement_hierarchy(
        self,
        tenant_id: int,
        partner_type: str,
        lines: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not lines:
            return lines
        if partner_type == "Customer":
            return await order_lines_by_settlement_hierarchy(
                tenant_id,
                lines,
                parent_doc_types={"应收单"},
                child_doc_types={"收款单", "收款退款"},
                rel_source="receivable",
                rel_target="receipt",
                debit_doc_type="Receivable",
                credit_doc_type="Receipt",
                return_offset_child_doc_types={"销售退货"},
                return_offset_credit_doc_type=SETTLEMENT_CREDIT_SALES_RETURN_OFFSET,
            )
        return await order_lines_by_settlement_hierarchy(
            tenant_id,
            lines,
            parent_doc_types={"应付单"},
            child_doc_types={"付款单", "付款退款"},
            rel_source="payable",
            rel_target="payment",
            debit_doc_type="Payable",
            credit_doc_type="Payment",
            return_offset_child_doc_types={"采购退货"},
            return_offset_credit_doc_type=SETTLEMENT_CREDIT_PURCHASE_RETURN_OFFSET,
        )

    async def enrich_lines_invoice_dates(
        self,
        tenant_id: int,
        lines: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """对账单行补开票日期：应付单→采购收票，应收单→销项发票（多张取最近）。"""
        if not lines:
            return lines
        from apps.kuaicaiwu.models.invoice import Invoice
        from apps.kuaicaiwu.models.purchase_invoice import PurchaseInvoice
        from apps.kuaizhizao.models.document_relation import DocumentRelation

        excluded_statuses = ("已作废", "已红冲")
        payable_ids = [
            int(ln["doc_id"])
            for ln in lines
            if ln.get("doc_type") == "应付单" and ln.get("doc_id")
        ]
        receivable_ids = [
            int(ln["doc_id"])
            for ln in lines
            if ln.get("doc_type") == "应收单" and ln.get("doc_id")
        ]
        if not payable_ids and not receivable_ids:
            return lines

        dates_by_doc: Dict[Tuple[str, int], List[date]] = defaultdict(list)
        if payable_ids:
            relations = await DocumentRelation.filter(
                tenant_id=tenant_id,
                source_type="payable",
                source_id__in=payable_ids,
                target_type="purchase_invoice",
            ).all()
            invoice_ids = [int(r.target_id) for r in relations if r.target_id]
            if invoice_ids:
                date_by_id = {
                    int(inv.id): inv.invoice_date
                    for inv in await PurchaseInvoice.filter(
                        tenant_id=tenant_id,
                        id__in=invoice_ids,
                        deleted_at__isnull=True,
                    ).exclude(status__in=list(excluded_statuses))
                    if inv.invoice_date
                }
                for rel in relations:
                    if not rel.source_id or not rel.target_id:
                        continue
                    inv_date = date_by_id.get(int(rel.target_id))
                    if inv_date:
                        dates_by_doc[("应付单", int(rel.source_id))].append(inv_date)

        if receivable_ids:
            relations = await DocumentRelation.filter(
                tenant_id=tenant_id,
                source_type="receivable",
                source_id__in=receivable_ids,
                target_type="sales_invoice",
            ).all()
            invoice_ids = [int(r.target_id) for r in relations if r.target_id]
            if invoice_ids:
                date_by_id = {
                    int(inv.id): inv.invoice_date
                    for inv in await Invoice.filter(
                        tenant_id=tenant_id,
                        id__in=invoice_ids,
                        category="OUT",
                        deleted_at__isnull=True,
                    ).exclude(status__in=list(excluded_statuses))
                    if inv.invoice_date
                }
                for rel in relations:
                    if not rel.source_id or not rel.target_id:
                        continue
                    inv_date = date_by_id.get(int(rel.target_id))
                    if inv_date:
                        dates_by_doc[("应收单", int(rel.source_id))].append(inv_date)

        for ln in lines:
            if ln.get("doc_id") is None:
                continue
            dates = dates_by_doc.get((str(ln.get("doc_type") or ""), int(ln["doc_id"])))
            if dates:
                ln["invoice_date"] = to_api_isoformat(max(dates))
        return lines

    async def ensure_statement_line_hierarchy(
        self,
        tenant_id: int,
        partner_type: str,
        opening_balance: Decimal,
        lines: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """补齐层级并重算行余额（含本次对账金额）。"""
        if not lines:
            return lines
        working = [_normalize_statement_line_amounts(dict(ln)) for ln in lines]
        # 始终按核销真源重排：付款已嵌套时，退货冲减仍需挂到蓝字应付/应收下
        ordered = await self._order_lines_by_settlement_hierarchy(
            tenant_id, partner_type, working
        )
        _, _, _, with_bal = self._apply_running_balance(opening_balance, ordered)
        return with_bal

    def _apply_running_balance(
        self, opening_balance: Decimal, lines: List[Dict[str, Any]]
    ) -> Tuple[Decimal, Decimal, Decimal, List[Dict[str, Any]]]:
        balance = opening_balance
        debit_total = Decimal("0")
        credit_total = Decimal("0")
        result: List[Dict[str, Any]] = []
        for ln in lines:
            debit = _q_money(ln.get("debit", 0))
            credit = _q_money(ln.get("credit", 0))
            debit_total += debit
            credit_total += credit
            balance = _q_money(balance + debit - credit)
            row = dict(ln)
            row["balance"] = float(balance)
            result.append(row)
        return _q_money(debit_total), _q_money(credit_total), balance, result

    async def _load_prior_stated_amounts(
        self,
        tenant_id: int,
        partner_id: int,
        partner_type: str,
        exclude_statement_id: Optional[int] = None,
    ) -> Dict[Tuple[str, int], Decimal]:
        """其它对账单中已累计的对账金额（按单据族+id）。"""
        rows = await PartnerStatement.filter(
            tenant_id=tenant_id,
            partner_id=partner_id,
            partner_type=partner_type,
            deleted_at__isnull=True,
        ).only("id", "transaction_details").all()
        totals: Dict[Tuple[str, int], Decimal] = defaultdict(Decimal)
        for stmt in rows:
            if exclude_statement_id is not None and int(stmt.id) == int(exclude_statement_id):
                continue
            details = stmt.transaction_details or {}
            stored = details.get("document_lines")
            if not stored:
                stored = collapse_material_lines_to_document_lines(details.get("lines") or [])
            for ln in stored:
                key = _line_doc_key(ln.get("doc_type"), ln.get("doc_id"))
                if not key:
                    continue
                totals[key] += _line_statement_amount(ln)
        return dict(totals)

    def _apply_partial_statement_lines(
        self,
        lines: List[Dict[str, Any]],
        prior_map: Dict[Tuple[str, int], Decimal],
        amount_overrides: Optional[Dict[Tuple[str, int], Decimal]] = None,
    ) -> Tuple[List[Dict[str, Any]], int, Decimal]:
        """
        按累计已对金额计算未对余额；默认本次对账金额=未对金额（用户可改大，不封顶未对金额）。
        已全部对账的行剔除，并将其借贷净额并入期初调节。
        """
        if not lines:
            return [], 0, Decimal("0.00")
        result: List[Dict[str, Any]] = []
        excluded_count = 0
        excluded_net = Decimal("0.00")
        overrides = amount_overrides or {}
        for ln in lines:
            row = dict(ln)
            doc_amount = _line_doc_amount(row)
            key = _line_doc_key(row.get("doc_type"), row.get("doc_id"))
            prior = prior_map.get(key, Decimal("0")) if key else Decimal("0")
            remaining = _q_money(doc_amount - prior)
            if remaining <= 0:
                excluded_count += 1
                excluded_net += _q_money(row.get("debit", 0)) - _q_money(row.get("credit", 0))
                continue
            statement_amount = remaining
            if key and key in overrides:
                statement_amount = _q_money(overrides[key])
            elif row.get("statement_amount") is not None:
                statement_amount = _q_money(row["statement_amount"])
            if statement_amount <= 0:
                code = row.get("doc_code") or row.get("doc_id")
                raise ValidationError(f"单据 {code} 本次对账金额须大于 0")
            result.append(
                _apply_statement_amount_to_line(row, statement_amount, doc_amount, prior, remaining)
            )
        return result, excluded_count, _q_money(excluded_net)

    def _build_line_amount_override_map(
        self, line_amounts: Optional[List[Dict[str, Any]]]
    ) -> Dict[Tuple[str, int], Decimal]:
        overrides: Dict[Tuple[str, int], Decimal] = {}
        if not line_amounts:
            return overrides
        for item in line_amounts:
            key = _line_doc_key(item.get("doc_type"), item.get("doc_id"))
            if not key:
                continue
            overrides[key] = _q_money(item.get("statement_amount"))
        return overrides

    def _apply_line_amount_overrides_to_preview_lines(
        self,
        lines: List[Dict[str, Any]],
        prior_map: Dict[Tuple[str, int], Decimal],
        overrides: Dict[Tuple[str, int], Decimal],
    ) -> List[Dict[str, Any]]:
        if not overrides:
            return [_normalize_statement_line_amounts(dict(ln)) for ln in lines]
        rebuilt: List[Dict[str, Any]] = []
        for ln in lines:
            row = dict(ln)
            key = _line_doc_key(row.get("doc_type"), row.get("doc_id"))
            if not key or key not in overrides:
                continue
            doc_amount = _line_doc_amount(row)
            prior = prior_map.get(key, Decimal("0"))
            remaining = _q_money(doc_amount - prior)
            if remaining <= 0:
                continue
            statement_amount = _q_money(overrides[key])
            if statement_amount <= 0:
                code = row.get("doc_code") or row.get("doc_id")
                raise ValidationError(f"单据 {code} 本次对账金额须大于 0")
            rebuilt.append(
                _apply_statement_amount_to_line(row, statement_amount, doc_amount, prior, remaining)
            )
        return rebuilt

    async def preview_statement(
        self,
        tenant_id: int,
        partner_id: int,
        partner_type: str,
        start_date: date,
        end_date: date,
        amount_basis: str = AMOUNT_BASIS_TAX_INCLUSIVE,
    ) -> Dict[str, Any]:
        if end_date < start_date:
            raise ValidationError("结束日期不能早于开始日期")
        basis = parse_statement_amount_basis(amount_basis)
        partner = await self._load_partner_snapshot(tenant_id, partner_id, partner_type)
        opening = await self._calc_opening_balance(
            tenant_id, partner_id, partner_type, start_date, basis
        )
        raw_lines = await self._collect_period_raw_lines(
            tenant_id, partner_id, partner_type, start_date, end_date, basis
        )
        prior_map = await self._load_prior_stated_amounts(tenant_id, partner_id, partner_type)
        before_count = len(raw_lines)
        raw_lines, excluded_from_period, excluded_net = self._apply_partial_statement_lines(
            raw_lines, prior_map
        )
        # 已纳入其它对账单的本期发生额并入期初，剩余行续算余额
        opening = _q_money(opening + excluded_net)
        debit_total, credit_total, closing, lines = self._apply_running_balance(opening, raw_lines)
        lines = await self.enrich_lines_invoice_dates(tenant_id, lines)
        company_name = await self._get_tenant_company_name(tenant_id)
        balance_label = "应收余额" if partner_type == "Customer" else "应付余额"
        stmt_period = start_date.strftime("%Y-%m")
        existing = await self._get_active_period_statement(
            tenant_id, partner_id, partner_type, stmt_period
        )
        partner_default_statement = await self._partner_uses_statement_ledger(
            tenant_id, partner_id, partner_type
        )
        supports_ledger_modes = partner_default_statement or self._lines_support_statement_ledger(
            lines
        )
        from apps.kuaicaiwu.services.partner_statement_line_service import (
            PartnerStatementLineService,
        )

        line_svc = PartnerStatementLineService()
        material_lines = await line_svc.expand_preview_lines_to_material_lines(
            tenant_id, lines, self
        )
        return {
            "partner_id": partner_id,
            "partner_name": partner["name"],
            "partner_type": partner_type,
            "start_date": to_api_isoformat(start_date),
            "end_date": to_api_isoformat(end_date),
            "company_name": company_name,
            "balance_label": balance_label,
            "summary": {
                "opening_balance": float(opening),
                "debit_total": float(debit_total),
                "credit_total": float(credit_total),
                "closing_balance": float(closing),
            },
            "lines": material_lines,
            "document_lines": lines,
            "partner_snapshot": partner,
            "excluded_from_period": excluded_from_period,
            # 仅提示：同月可有多张对账单；是否可生成看 lines 是否仍有未纳入单据
            "existing_period_statement_id": existing.id if existing else None,
            "existing_period_statement_code": existing.statement_code if existing else None,
            "existing_period": stmt_period if existing else None,
            "amount_basis": basis,
            "partner_uses_statement_ledger": supports_ledger_modes,
        }

    async def _get_active_period_statement(
        self,
        tenant_id: int,
        partner_id: int,
        partner_type: str,
        statement_period: str,
    ) -> Optional[PartnerStatement]:
        """同往来同月份最近一张未删除对账单（仅作预览提示，不拦截再生成）。"""
        return (
            await PartnerStatement.filter(
                tenant_id=tenant_id,
                partner_id=partner_id,
                partner_type=partner_type,
                statement_period=statement_period,
                deleted_at__isnull=True,
            )
            .order_by("-id")
            .first()
        )

    def _no_remaining_lines_message(
        self,
        period_label: str,
        *,
        existing_code: Optional[str] = None,
    ) -> str:
        if existing_code:
            return (
                f"该往来单位在 {period_label} 的单据已全部纳入对账单 "
                f"{existing_code}，没有可再生成的明细"
            )
        return f"该往来单位在 {period_label} 没有可纳入对账单的已审核应收/应付或已确认收/付款"

    async def _generate_statement_code(self, tenant_id: int) -> str:
        today = today_site_str()
        return await self.generate_code(tenant_id, "PARTNER_STATEMENT_CODE", prefix=f"DZ{today}")

    async def create_statement(
        self,
        tenant_id: int,
        partner_id: int,
        partner_type: str,
        period: str,
        created_by: int,
        notes: Optional[str] = None,
        attachments: Optional[list] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        line_amounts: Optional[List[Dict[str, Any]]] = None,
        ledger_posting_mode: Optional[str] = None,
        amount_basis: str = AMOUNT_BASIS_TAX_INCLUSIVE,
    ) -> PartnerStatement:
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError("结束日期不能早于起始日期")
            period_label = f"{to_api_isoformat(start_date)}~{to_api_isoformat(end_date)}"
            # 列表「对账期间」展示用起始月 YYYY-MM；同月允许多张（按单据去重）
            stmt_period = period or start_date.strftime("%Y-%m")
        else:
            start_date, end_date = period_to_date_range(period)
            period_label = period
            stmt_period = period

        basis = parse_statement_amount_basis(amount_basis)
        preview = await self.preview_statement(
            tenant_id, partner_id, partner_type, start_date, end_date, basis
        )
        if not (preview.get("lines") or []):
            existing_code = preview.get("existing_period_statement_code")
            raise BusinessLogicError(
                self._no_remaining_lines_message(
                    period_label,
                    existing_code=str(existing_code) if existing_code else None,
                )
            )

        code = await self._generate_statement_code(tenant_id)
        company_name = preview["company_name"]
        summary = dict(preview["summary"])
        document_lines = list(preview.get("document_lines") or [])
        if not document_lines:
            document_lines = collapse_material_lines_to_document_lines(
                list(preview.get("lines") or [])
            )
        overrides = self._build_line_amount_override_map(line_amounts)
        if line_amounts is not None and not overrides:
            raise BusinessLogicError("请至少勾选一行对账明细")
        workflow_lines = document_lines
        if overrides:
            prior_map = await self._load_prior_stated_amounts(tenant_id, partner_id, partner_type)
            workflow_lines = self._apply_line_amount_overrides_to_preview_lines(
                document_lines, prior_map, overrides
            )
            if not workflow_lines:
                raise BusinessLogicError("对账明细不能为空")
            opening = _q_money(summary["opening_balance"])
            debit_total, credit_total, closing, workflow_lines = self._apply_running_balance(
                opening, workflow_lines
            )
            summary = {
                "opening_balance": float(opening),
                "debit_total": float(debit_total),
                "credit_total": float(credit_total),
                "closing_balance": float(closing),
            }
        details = {
            "summary": summary,
            "document_lines": workflow_lines,
            "partner_snapshot": preview["partner_snapshot"],
            "balance_label": preview["balance_label"],
            "period_label": period_label,
            "amount_basis": basis,
        }

        mode = str(ledger_posting_mode or "immediate").strip()
        if mode not in PARTNER_STATEMENT_LEDGER_MODES:
            raise ValidationError("ledger_posting_mode 须为 immediate 或 by_invoice")
        # 明细已是月结业务源单，或客商默认按月结：允许立即/按发票；否则强制立即立账
        allows_ledger_modes = await self._partner_uses_statement_ledger(
            tenant_id, partner_id, partner_type
        ) or self._lines_support_statement_ledger(workflow_lines)
        if not allows_ledger_modes:
            mode = "immediate"

        user_info = await self.get_user_info(created_by)
        from apps.kuaicaiwu.services.partner_statement_line_service import (
            PartnerStatementLineService,
        )
        from apps.kuaicaiwu.config.finance_settlement_contract import (
            STATEMENT_LINE_GRANULARITY_MATERIAL,
        )

        line_svc = PartnerStatementLineService()
        material_lines = await line_svc.expand_preview_lines_to_material_lines(
            tenant_id, workflow_lines, self
        )
        details["lines"] = material_lines

        from tortoise.transactions import in_transaction

        async with in_transaction():
            obj = await PartnerStatement.create(
                tenant_id=tenant_id,
                statement_code=code,
                partner_id=partner_id,
                partner_name=preview["partner_name"],
                partner_type=partner_type,
                statement_period=stmt_period,
                start_date=start_date,
                end_date=end_date,
                opening_balance=_q_money(summary["opening_balance"]),
                debit_total=_q_money(summary["debit_total"]),
                credit_total=_q_money(summary["credit_total"]),
                closing_balance=_q_money(summary["closing_balance"]),
                status="Draft",
                transaction_details=details,
                company_name=company_name,
                notes=notes,
                attachments=attachments,
                statement_line_granularity=STATEMENT_LINE_GRANULARITY_MATERIAL,
                ledger_posting_mode=mode,
                created_by=created_by,
                created_by_name=user_info["name"],
                updated_by=created_by,
                updated_by_name=user_info["name"],
            )
            await line_svc.replace_statement_lines(
                tenant_id, obj, material_lines, amount_basis=basis, is_read_only=False
            )
        return obj

    async def list_statements(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        partner_type: Optional[str] = None,
        partner_id: Optional[int] = None,
        statement_period: Optional[str] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        statement_code: Optional[str] = None,
        partner_name: Optional[str] = None,
        created_start_date: Optional[str] = None,
        created_end_date: Optional[str] = None,
        updated_start_date: Optional[str] = None,
        updated_end_date: Optional[str] = None,
        sort_field: Optional[str] = None,
        sort_order: Optional[str] = None,
    ) -> Tuple[List[PartnerStatement], int]:
        from apps.kuaicaiwu.services.finance_list_core import apply_finance_partner_statement_list_filters

        query = PartnerStatement.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if partner_type:
            query = query.filter(partner_type=partner_type)
        if partner_id:
            query = query.filter(partner_id=partner_id)
        if status:
            query = query.filter(status=status)

        query, order_expr = apply_finance_partner_statement_list_filters(
            query,
            keyword=keyword,
            statement_code=statement_code,
            partner_name=partner_name,
            statement_period=statement_period,
            created_start_date=created_start_date,
            created_end_date=created_end_date,
            updated_start_date=updated_start_date,
            updated_end_date=updated_end_date,
            sort_field=sort_field,
            sort_order=sort_order,
        )

        total = await query.count()
        items = await query.offset(skip).limit(limit).order_by(order_expr, "-id")
        return items, total

    async def get_statement(self, tenant_id: int, statement_id: int) -> PartnerStatement:
        obj = await PartnerStatement.get_or_none(
            tenant_id=tenant_id, id=statement_id, deleted_at__isnull=True
        )
        if not obj:
            raise NotFoundError(f"对账单不存在: {statement_id}")
        return obj

    _BIZ_CONFIRM_REVIEWS = frozenset(
        {"", "草稿", "draft", "驳回", "已驳回", "rejected", "SUBMITTED"}
    )

    def _statement_content_editable(self, obj: PartnerStatement) -> bool:
        """草稿/异议，或已业务确认但未送审/已驳回时可改本次对账金额；待审与已审锁定。"""
        rs = str(obj.review_status or "").strip()
        if rs in (
            "待审核",
            "已审核",
            "pending_review",
            "PENDING_REVIEW",
            "approved",
            "已提交",
            "pending",
        ):
            return False
        if obj.status in ("Draft", "Disputed"):
            return rs in self._BIZ_CONFIRM_REVIEWS or rs in ("草稿", "draft", "驳回", "已驳回", "rejected")
        # 业务确认后、提交审核前（及反审核回草稿）仍可调整本次对账金额
        if obj.status == "Confirmed" and rs in (
            "",
            "草稿",
            "draft",
            "驳回",
            "已驳回",
            "rejected",
        ):
            return True
        return False

    async def confirm_business_statement(
        self, tenant_id: int, statement_id: int, user_id: int
    ) -> PartnerStatement:
        """业务确认对账：status=Confirmed，review 归草稿；与提交审核分离。"""
        from apps.kuaicaiwu.services.finance_audit_workflow import _updated_audit_kwargs
        from core.utils.timezone_utils import resolve_business_datetime

        obj = await self.get_statement(tenant_id, statement_id)
        if obj.status not in ("Draft", "Disputed"):
            raise BusinessLogicError("仅草稿或有异议的对账单可确认对账")
        if not self._statement_content_editable(obj):
            raise BusinessLogicError("当前状态不可确认对账，请先撤回审核或处理在途审批")
        from apps.common.audit_actor import operator_name_from_user

        operator = await User.filter(id=user_id).first()
        operator_name = operator_name_from_user(operator) if operator else ""
        now = resolve_business_datetime()
        await PartnerStatement.filter(tenant_id=tenant_id, id=statement_id).update(
            status="Confirmed",
            review_status="草稿",
            reviewer_id=None,
            reviewer_name=None,
            review_time=None,
            review_remarks=None,
            confirmed_at=now,
            confirmed_by=user_id,
            updated_by=user_id,
            updated_by_name=operator_name,
        )
        return await self.get_statement(tenant_id, statement_id)

    async def commit_statement(
        self, tenant_id: int, statement_id: int, submitted_by: int
    ) -> PartnerStatement:
        """UniAudit「提交」：业务确认对账（不再写 SUBMITTED）。"""
        return await self.confirm_business_statement(tenant_id, statement_id, submitted_by)

    async def submit_statement_for_review(
        self, tenant_id: int, statement_id: int, submitted_by: int
    ) -> PartnerStatement:
        """提交审核：草稿/异议态在送审前内部落业务确认（与保存对账金额等效，无需单独确认按钮）。"""
        from apps.kuaicaiwu.services.finance_audit_workflow import submit_finance_review

        obj = await self.get_statement(tenant_id, statement_id)
        if obj.status in ("Draft", "Disputed"):
            await self.confirm_business_statement(tenant_id, statement_id, submitted_by)
            obj = await self.get_statement(tenant_id, statement_id)
        if obj.status != "Confirmed":
            raise BusinessLogicError("当前状态不可提交审核")
        rs = str(obj.review_status or "").strip()
        if rs in ("待审核", "已审核", "pending_review", "PENDING_REVIEW", "approved"):
            raise BusinessLogicError("当前审核状态不可再次提交审核")
        if rs not in ("", "草稿", "draft", "驳回", "已驳回", "rejected"):
            raise BusinessLogicError("请先保存对账金额后再提交审核")
        await submit_finance_review(
            model=PartnerStatement,
            tenant_id=tenant_id,
            doc_id=statement_id,
            updated_by=submitted_by,
            doc_label="往来对账单",
            node_key="partner_statement",
        )
        return await self.get_statement(tenant_id, statement_id)

    async def submit_statement(
        self, tenant_id: int, statement_id: int, submitted_by: int
    ) -> PartnerStatement:
        """兼容：业务确认后立即提交审核。"""
        obj = await self.get_statement(tenant_id, statement_id)
        if obj.status in ("Draft", "Disputed"):
            await self.confirm_business_statement(tenant_id, statement_id, submitted_by)
        return await self.submit_statement_for_review(tenant_id, statement_id, submitted_by)

    async def approve_statement(
        self,
        tenant_id: int,
        statement_id: int,
        approved_by: int,
        rejection_reason: Optional[str] = None,
        *,
        is_auto_approve: bool = False,
    ) -> PartnerStatement:
        """审核往来对账单；通过时仅更新 review，业务确认须已在前序步骤完成。"""
        from apps.kuaicaiwu.services.finance_audit_workflow import (
            assert_finance_pending_approval_flow,
            _PENDING_REVIEW,
            _norm_review,
        )
        from apps.common.audit_actor import operator_name_from_user
        from core.services.approval.uni_audit_service import UniAuditService
        from core.utils.timezone_utils import resolve_business_datetime
        from tortoise.transactions import in_transaction

        async def _do_approve() -> PartnerStatement:
            async with in_transaction():
                obj = await self.get_statement(tenant_id, statement_id)
                rs = _norm_review(obj.review_status)
                if rs not in _PENDING_REVIEW:
                    raise BusinessLogicError(
                        f"往来对账单审核状态不是待审核，当前: {obj.review_status!r}"
                    )
                if obj.status not in ("Draft", "Disputed", "Confirmed"):
                    raise BusinessLogicError("当前状态不可审核")
                user = await User.filter(id=approved_by).first()
                approver_name = operator_name_from_user(user) if user else ""
                now = resolve_business_datetime()
                if rejection_reason:
                    await PartnerStatement.filter(tenant_id=tenant_id, id=statement_id).update(
                        reviewer_id=approved_by,
                        reviewer_name=approver_name,
                        review_time=now,
                        review_status="驳回",
                        review_remarks=rejection_reason,
                        updated_by=approved_by,
                        updated_by_name=approver_name,
                    )
                else:
                    approve_patch: Dict[str, Any] = {
                        "reviewer_id": approved_by,
                        "reviewer_name": approver_name,
                        "review_time": now,
                        "review_status": "已审核",
                        "review_remarks": None,
                        "updated_by": approved_by,
                        "updated_by_name": approver_name,
                    }
                    if obj.status in ("Draft", "Disputed"):
                        approve_patch["status"] = "Confirmed"
                        if obj.confirmed_at is None:
                            approve_patch["confirmed_at"] = now
                            approve_patch["confirmed_by"] = approved_by
                    await PartnerStatement.filter(
                        tenant_id=tenant_id, id=statement_id
                    ).update(**approve_patch)
                return await self.get_statement(tenant_id, statement_id)

        async def _after_review_approve(
            stmt: PartnerStatement, *, prior_review_status: str
        ) -> PartnerStatement:
            if rejection_reason:
                return stmt
            if str(stmt.review_status or "").strip() not in ("已审核", "approved"):
                return stmt
            landing = prior_review_status if prior_review_status in _PENDING_REVIEW else "草稿"
            try:
                return await self._auto_post_ledger_if_immediate_after_review_approve(
                    tenant_id, statement_id, approved_by
                )
            except Exception:
                await self._rollback_review_after_immediate_post_failure(
                    tenant_id, statement_id, landing_review_status=landing
                )
                raise

        async def _approve_then_immediate_post(
            prior_review_status: str,
        ) -> PartnerStatement:
            stmt = await _do_approve()
            return await _after_review_approve(stmt, prior_review_status=prior_review_status)

        if is_auto_approve:
            obj0 = await self.get_statement(tenant_id, statement_id)
            return await _approve_then_immediate_post(str(obj0.review_status or "").strip())

        await assert_finance_pending_approval_flow(
            tenant_id=tenant_id,
            doc_id=statement_id,
            node_key="partner_statement",
            doc_label="往来对账单",
            verb="驳回" if rejection_reason else "审核",
        )

        if rejection_reason:
            result = await UniAuditService.reject_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="partner_statement",
                entity_id=statement_id,
                approver_id=approved_by,
                reason=rejection_reason,
                flow_reject=lambda _reason=None: _do_approve(),
            )
            return result if result is not None else await self.get_statement(tenant_id, statement_id)
        obj_before = await self.get_statement(tenant_id, statement_id)
        prior_review = str(obj_before.review_status or "").strip()

        async def _flow_approve() -> PartnerStatement:
            return await _do_approve()

        result = await UniAuditService.approve_with_flow_fallback(
            tenant_id=tenant_id,
            entity_type="partner_statement",
            entity_id=statement_id,
            approver_id=approved_by,
            flow_approve=_flow_approve,
        )
        stmt = result if result is not None else await self.get_statement(tenant_id, statement_id)
        return await _after_review_approve(stmt, prior_review_status=prior_review)

    async def withdraw_statement(
        self, tenant_id: int, statement_id: int, withdrawn_by: int
    ) -> PartnerStatement:
        """撤销提交：已提交→草稿；撤回审核：待审核→已提交。"""
        from apps.kuaicaiwu.services.finance_audit_workflow import (
            _PENDING_REVIEW,
            _norm_review,
            _updated_audit_kwargs,
        )
        from core.services.approval.approval_instance_service import ApprovalInstanceService
        from tortoise.transactions import in_transaction

        obj = await self.get_statement(tenant_id, statement_id)
        raw = str(obj.review_status or "").strip()
        if (
            obj.status == "Draft"
            and raw == "SUBMITTED"
        ):
            await PartnerStatement.filter(tenant_id=tenant_id, id=statement_id).update(
                review_status="草稿",
                **(await _updated_audit_kwargs(withdrawn_by)),
            )
            return await self.get_statement(tenant_id, statement_id)
        if obj.status == "Confirmed" and raw in ("", "草稿", "draft", "SUBMITTED"):
            from apps.common.audit_actor import operator_name_from_user

            operator = await User.filter(id=withdrawn_by).first()
            operator_name = operator_name_from_user(operator) if operator else ""
            await PartnerStatement.filter(tenant_id=tenant_id, id=statement_id).update(
                status="Draft",
                review_status="草稿",
                confirmed_at=None,
                confirmed_by=None,
                updated_by=withdrawn_by,
                updated_by_name=operator_name,
            )
            return await self.get_statement(tenant_id, statement_id)
        if _norm_review(raw) in _PENDING_REVIEW:
            async with in_transaction():
                cancelled = await ApprovalInstanceService.cancel_approval(
                    tenant_id=tenant_id,
                    entity_type="partner_statement",
                    entity_id=statement_id,
                    operator_id=withdrawn_by,
                )
                if cancelled is False:
                    raise BusinessLogicError("撤回失败：无法取消审批流程，请重试")
                await PartnerStatement.filter(tenant_id=tenant_id, id=statement_id).update(
                    review_status="草稿",
                    reviewer_id=None,
                    reviewer_name=None,
                    review_time=None,
                    review_remarks=None,
                    **(await _updated_audit_kwargs(withdrawn_by)),
                )
            return await self.get_statement(tenant_id, statement_id)
        raise BusinessLogicError("当前状态不可撤回")

    async def _unpost_statement_ledger(
        self, tenant_id: int, obj: PartnerStatement, operator_id: int
    ) -> None:
        """撤销审核立账：删除本单生成的未结算应收/应付，状态回到 Confirmed。"""
        from apps.kuaicaiwu.services.purchase_receipt_line_finance_occupancy_service import (
            PurchaseReceiptLineFinanceOccupancyService,
        )
        from core.utils.timezone_utils import resolve_business_datetime

        stmt_code = str(obj.statement_code or "").strip()
        if not stmt_code:
            raise BusinessLogicError("对账单号缺失，无法撤销立账")
        marker = f"对账单 {stmt_code} 审核立账"
        now = resolve_business_datetime()
        stmt_id = int(obj.id)

        payables = await Payable.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).filter(
            Q(notes__contains=marker)
            | Q(source_type=PAYABLE_SOURCE_PARTNER_STATEMENT, source_id=stmt_id)
        ).all()
        receivables = await Receivable.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).filter(
            Q(notes__contains=marker)
            | Q(source_type=RECEIVABLE_SOURCE_PARTNER_STATEMENT, source_id=stmt_id)
        ).all()

        for p in payables:
            if Decimal(p.paid_amount or 0) > 0:
                raise BusinessLogicError(
                    f"已立账产生的应付单 {p.payable_code} 已有付款，无法反审核；请先处理付款后再试"
                )
            if Decimal(getattr(p, "refunded_amount", 0) or 0) > 0:
                raise BusinessLogicError(
                    f"已立账产生的应付单 {p.payable_code} 已有退款，无法反审核"
                )
        for r in receivables:
            if Decimal(r.received_amount or 0) > 0:
                raise BusinessLogicError(
                    f"已立账产生的应收单 {r.receivable_code} 已有收款，无法反审核；请先处理收款后再试"
                )
            if Decimal(getattr(r, "refunded_amount", 0) or 0) > 0:
                raise BusinessLogicError(
                    f"已立账产生的应收单 {r.receivable_code} 已有退款，无法反审核"
                )

        occ_svc = PurchaseReceiptLineFinanceOccupancyService()
        for p in payables:
            await occ_svc.soft_delete_by_target(tenant_id, "Payable", int(p.id))
            await Payable.filter(tenant_id=tenant_id, id=int(p.id)).update(deleted_at=now)
        for r in receivables:
            await Receivable.filter(tenant_id=tenant_id, id=int(r.id)).update(deleted_at=now)

        await PartnerStatement.filter(tenant_id=tenant_id, id=int(obj.id)).update(
            status="Confirmed",
            ledger_posted_at=None,
            ledger_posted_by=None,
            updated_by=operator_id,
        )

    async def revoke_statement(
        self, tenant_id: int, statement_id: int, revoked_by: int
    ) -> PartnerStatement:
        from apps.kuaicaiwu.services.finance_audit_workflow import revoke_finance_review
        from tortoise.transactions import in_transaction

        obj = await self.get_statement(tenant_id, statement_id)
        status = str(obj.status or "").strip()
        if status == "Sent":
            raise BusinessLogicError("已发送的对账单不可撤销审核")
        if status not in ("Confirmed", "LedgerPosted"):
            raise BusinessLogicError("仅已确认或已立账（且未发送）的对账单可撤销审核")
        async with in_transaction():
            if status == "LedgerPosted":
                await self._unpost_statement_ledger(tenant_id, obj, revoked_by)
            await revoke_finance_review(
                model=PartnerStatement,
                tenant_id=tenant_id,
                doc_id=statement_id,
                updated_by=revoked_by,
                doc_label="往来对账单",
                node_key="partner_statement",
            )
            return await self.get_statement(tenant_id, statement_id)

    async def confirm_statement(
        self, tenant_id: int, statement_id: int, user_id: int
    ) -> PartnerStatement:
        """业务确认对账。"""
        return await self.confirm_business_statement(tenant_id, statement_id, user_id)

    async def _purchase_receipt_has_approved_invoice(
        self, tenant_id: int, receipt_id: int
    ) -> bool:
        from apps.kuaicaiwu.models.purchase_invoice import PurchaseInvoice
        from apps.kuaicaiwu.models.purchase_receipt_line_finance_occupancy import (
            PurchaseReceiptLineFinanceOccupancy,
        )
        from apps.kuaizhizao.models.document_relation import DocumentRelation

        async def _invoice_approved(inv_id: int) -> bool:
            inv = await PurchaseInvoice.get_or_none(
                tenant_id=tenant_id,
                id=int(inv_id),
                deleted_at__isnull=True,
            )
            if not inv:
                return False
            rs = str(inv.review_status or "").strip()
            return rs in ("已审核", "approved")

        occ_rows = await PurchaseReceiptLineFinanceOccupancy.filter(
            tenant_id=tenant_id,
            purchase_receipt_id=receipt_id,
            occupancy_kind="invoice",
            deleted_at__isnull=True,
        ).all()
        for occ in occ_rows:
            tid = int(getattr(occ, "target_doc_id", 0) or 0)
            if tid > 0 and await _invoice_approved(tid):
                return True

        rels = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="purchase_receipt",
            source_id=int(receipt_id),
            target_type="purchase_invoice",
        ).all()
        for rel in rels:
            tid = int(getattr(rel, "target_id", 0) or 0)
            if tid > 0 and await _invoice_approved(tid):
                return True
        return False

    async def try_complete_ledger_after_purchase_invoice_approved(
        self,
        tenant_id: int,
        invoice_id: int,
        operator_id: int,
    ) -> None:
        """
        对账单「根据发票立账」：对账单先审时可能尚无已审发票而无法立账；
        关联入库的进项发票审核通过后补跑立账。
        """
        from apps.kuaicaiwu.models.purchase_invoice import PurchaseInvoice
        from apps.kuaizhizao.models.document_relation import DocumentRelation

        invoice = await PurchaseInvoice.get_or_none(
            tenant_id=tenant_id,
            id=int(invoice_id),
            deleted_at__isnull=True,
        )
        if not invoice:
            return
        rels = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="purchase_receipt",
            target_type="purchase_invoice",
            target_id=int(invoice_id),
        ).all()
        receipt_ids = {
            int(r.source_id)
            for r in rels
            if getattr(r, "source_id", None) is not None and int(r.source_id) > 0
        }
        if not receipt_ids:
            return

        statements = await PartnerStatement.filter(
            tenant_id=tenant_id,
            partner_id=int(invoice.supplier_id),
            partner_type="Supplier",
            deleted_at__isnull=True,
        ).all()
        for stmt in statements:
            rs = str(getattr(stmt, "review_status", None) or "").strip()
            if rs not in ("已审核", "approved"):
                continue
            if str(stmt.status or "").strip() not in ("Confirmed", "Sent", "LedgerPosted"):
                continue
            if stmt.ledger_posted_at is not None and str(stmt.status or "").strip() == "LedgerPosted":
                continue
            details = dict(stmt.transaction_details or {})
            lines = list(details.get("lines") or [])
            if not any(
                str(ln.get("doc_type") or "").strip() == "采购入库"
                and int(ln.get("doc_id") or 0) in receipt_ids
                for ln in lines
                if isinstance(ln, dict)
            ):
                continue
            try:
                await self.post_ledger(tenant_id, int(stmt.id), operator_id)
            except BusinessLogicError as exc:
                logger.info(
                    "进项发票 {} 审核后补立账跳过对账单 {}: {}",
                    invoice_id,
                    stmt.id,
                    exc,
                )

    async def _sales_delivery_has_approved_invoice(
        self, tenant_id: int, delivery_id: int
    ) -> bool:
        from apps.kuaicaiwu.models.invoice import Invoice
        from apps.kuaizhizao.models.document_relation import DocumentRelation

        # DocumentRelation 无软删字段，禁止 deleted_at__isnull
        rels = await DocumentRelation.filter(
            tenant_id=tenant_id,
            target_type="sales_delivery",
            target_id=delivery_id,
        ).all()
        invoice_ids: List[int] = []
        for rel in rels:
            if str(rel.source_type or "").strip() in (
                "sales_invoice",
                "invoice",
                "Invoice",
            ) and rel.source_id:
                invoice_ids.append(int(rel.source_id))
        if not invoice_ids:
            return False
        inv = await Invoice.filter(
            tenant_id=tenant_id,
            id__in=list(set(invoice_ids)),
            category="OUT",
            deleted_at__isnull=True,
        ).exclude(status__in=("DRAFT", "VOID", "void", "作废", "草稿")).first()
        return inv is not None

    async def _auto_post_ledger_if_immediate_after_review_approve(
        self, tenant_id: int, statement_id: int, operator_id: int
    ) -> PartnerStatement:
        """审核通过后自动立账：仅「立即立账」；「根据发票立账」先完成对账审核，待发票审核后补跑。"""
        obj = await self.get_statement(tenant_id, statement_id)
        mode = str(obj.ledger_posting_mode or "immediate").strip()
        if mode == "by_invoice":
            return obj
        if obj.ledger_posted_at is not None:
            return obj
        if str(obj.review_status or "").strip() not in ("已审核", "approved"):
            raise BusinessLogicError("须在审核通过后自动立账")
        if obj.status not in ("Confirmed", "Sent", "LedgerPosted"):
            raise BusinessLogicError(
                f"须先确认对账后再审核立账，当前业务状态: {obj.status!r}"
            )
        if not await self._statement_supports_ledger_modes(obj):
            raise BusinessLogicError("当前对账单明细不支持立账，无法完成审核立账")
        return await self.post_ledger(tenant_id, statement_id, operator_id)

    async def _rollback_review_after_immediate_post_failure(
        self, tenant_id: int, statement_id: int, *, landing_review_status: str
    ) -> None:
        """审核通过自动立账失败时撤销本次审核通过，避免「已审核但未立账」。"""
        await PartnerStatement.filter(tenant_id=tenant_id, id=statement_id).update(
            review_status=landing_review_status,
            reviewer_id=None,
            reviewer_name=None,
            review_time=None,
            review_remarks=None,
        )

    async def post_ledger(
        self, tenant_id: int, statement_id: int, operator_id: int
    ) -> PartnerStatement:
        """审核立账：按对账明细净额生成一张应收/应付（来源：往来对账单）。"""
        from apps.kuaicaiwu.schemas.finance import PayableCreate, ReceivableCreate
        from apps.kuaicaiwu.services.finance_due_date import resolve_partner_due_date
        from apps.kuaicaiwu.services.finance_service import PayableService, ReceivableService
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
        from apps.kuaizhizao.models.purchase_return import PurchaseReturn
        from apps.kuaizhizao.models.sales_delivery import SalesDelivery
        from apps.kuaizhizao.models.sales_return import SalesReturn
        from apps.kuaizhizao.services.finance_settlement_source_query import (
            _posted_payable_source_ids,
            _posted_receivable_source_ids,
            partner_statement_ledger_posted_doc_ids,
        )
        from core.utils.timezone_utils import resolve_business_datetime, to_site_date
        from tortoise.transactions import in_transaction

        obj = await self.get_statement(tenant_id, statement_id)
        mode = str(obj.ledger_posting_mode or "immediate").strip()
        if obj.ledger_posted_at is not None and mode == "immediate":
            raise BusinessLogicError("该对账单已完成审核立账")
        if obj.status not in ("Confirmed", "Sent", "LedgerPosted"):
            raise BusinessLogicError("请先审核确认对账单后再审核立账")
        if str(obj.review_status or "").strip() not in ("已审核", "approved"):
            raise BusinessLogicError("对账单须已审核通过后才能立账")
        if not await self._statement_supports_ledger_modes(obj):
            raise BusinessLogicError("当前对账单无可按月结立账的业务源单，无法审核立账")

        details = dict(obj.transaction_details or {})
        lines = list(details.get("lines") or [])
        if not lines:
            raise BusinessLogicError("对账单无明细，无法立账")

        payable_svc = PayableService()
        receivable_svc = ReceivableService()
        skipped_by_invoice = 0
        stmt_code = str(obj.statement_code or "")
        stmt_covered = await partner_statement_ledger_posted_doc_ids(
            tenant_id, int(obj.partner_id), str(obj.partner_type)
        )
        eligible: List[Dict[str, Any]] = []

        for ln in lines:
            if int(ln.get("tree_level") or 0) > 0:
                continue
            doc_type = str(ln.get("doc_type") or "").strip()
            if doc_type not in self._STATEMENT_LEDGER_LINE_DOC_TYPES:
                continue
            doc_id = ln.get("doc_id")
            if doc_id is None:
                continue
            try:
                source_id = int(doc_id)
            except (TypeError, ValueError):
                continue
            amount = _q_money(ln.get("statement_amount") or ln.get("doc_amount") or 0)
            if amount <= 0:
                continue
            if (doc_type, source_id) in stmt_covered:
                continue

            if obj.partner_type == "Supplier":
                if doc_type == "采购入库":
                    if mode == "by_invoice":
                        receipt_id = int(
                            ln.get("inbound_detail_doc_id")
                            or ln.get("settlement_source_id")
                            or source_id
                        )
                        if not await self._purchase_receipt_has_approved_invoice(
                            tenant_id, receipt_id
                        ):
                            skipped_by_invoice += 1
                            continue
                    posted = await _posted_payable_source_ids(
                        tenant_id, PAYABLE_SOURCE_PURCHASE_RECEIPT, [source_id]
                    )
                    if source_id in posted:
                        continue
                    receipt = await PurchaseReceipt.get_or_none(
                        tenant_id=tenant_id, id=source_id, deleted_at__isnull=True
                    )
                    if not receipt:
                        continue
                    eligible.append(ln)
                elif doc_type == "采购退货":
                    posted = await _posted_payable_source_ids(
                        tenant_id, PAYABLE_SOURCE_PURCHASE_RETURN, [source_id]
                    )
                    if source_id in posted:
                        continue
                    ret = await PurchaseReturn.get_or_none(
                        tenant_id=tenant_id, id=source_id, deleted_at__isnull=True
                    )
                    if not ret:
                        continue
                    eligible.append(ln)
            elif obj.partner_type == "Customer":
                if doc_type == "销售出库":
                    if mode == "by_invoice":
                        if not await self._sales_delivery_has_approved_invoice(
                            tenant_id, source_id
                        ):
                            skipped_by_invoice += 1
                            continue
                    posted = await _posted_receivable_source_ids(
                        tenant_id, RECEIVABLE_SOURCE_SALES_DELIVERY, [source_id]
                    )
                    if source_id in posted:
                        continue
                    delivery = await SalesDelivery.get_or_none(
                        tenant_id=tenant_id, id=source_id, deleted_at__isnull=True
                    )
                    if not delivery:
                        continue
                    eligible.append(ln)
                elif doc_type == "销售退货":
                    posted = await _posted_receivable_source_ids(
                        tenant_id, RECEIVABLE_SOURCE_SALES_RETURN, [source_id]
                    )
                    if source_id in posted:
                        continue
                    ret = await SalesReturn.get_or_none(
                        tenant_id=tenant_id, id=source_id, deleted_at__isnull=True
                    )
                    if not ret:
                        continue
                    eligible.append(ln)

        if not eligible:
            if mode == "by_invoice" and skipped_by_invoice > 0:
                raise BusinessLogicError(
                    "根据发票立账模式下，所选行尚无已审核发票，未生成应收/应付"
                )
            raise BusinessLogicError("没有可立账的未立账源单行")

        voucher_amount = _net_statement_ledger_amount(eligible)
        biz_date = obj.end_date
        due = await resolve_partner_due_date(
            tenant_id,
            "supplier" if obj.partner_type == "Supplier" else "customer",
            int(obj.partner_id),
            biz_date,
        )
        ledger_notes = f"对账单 {stmt_code} 审核立账"

        async with in_transaction():
            if obj.partner_type == "Supplier":
                if voucher_amount <= 0:
                    raise BusinessLogicError("本期对账净额不需生成应付单")
                await payable_svc.create_payable(
                    tenant_id=tenant_id,
                    payable_data=PayableCreate(
                        source_type=PAYABLE_SOURCE_PARTNER_STATEMENT,
                        source_id=statement_id,
                        source_code=stmt_code,
                        supplier_id=int(obj.partner_id),
                        supplier_name=str(obj.partner_name or ""),
                        total_amount=voucher_amount,
                        paid_amount=Decimal("0"),
                        remaining_amount=voucher_amount,
                        due_date=due,
                        business_date=biz_date,
                        status="未付款",
                        notes=ledger_notes,
                    ),
                    created_by=operator_id,
                )
            elif obj.partner_type == "Customer":
                if voucher_amount <= 0:
                    raise BusinessLogicError("本期对账净额不需生成应收单")
                await receivable_svc.create_receivable(
                    tenant_id=tenant_id,
                    receivable_data=ReceivableCreate(
                        source_type=RECEIVABLE_SOURCE_PARTNER_STATEMENT,
                        source_id=statement_id,
                        source_code=stmt_code,
                        customer_id=int(obj.partner_id),
                        customer_name=str(obj.partner_name or ""),
                        total_amount=voucher_amount,
                        received_amount=Decimal("0"),
                        remaining_amount=voucher_amount,
                        due_date=due,
                        business_date=biz_date,
                        status="未收款",
                        notes=ledger_notes,
                    ),
                    created_by=operator_id,
                )
            else:
                raise BusinessLogicError("当前往来类型不支持审核立账")

            now = resolve_business_datetime()
            user = await User.filter(id=operator_id).first()
            operator_name = user.full_name if user and user.full_name else ""
            finalize = mode == "immediate" or (
                mode == "by_invoice" and skipped_by_invoice == 0
            )
            patch: Dict[str, Any] = {
                "updated_by": operator_id,
                "updated_by_name": operator_name,
            }
            if finalize:
                patch["ledger_posted_at"] = now
                patch["ledger_posted_by"] = operator_id
                patch["status"] = "LedgerPosted"
            await PartnerStatement.filter(tenant_id=tenant_id, id=statement_id).update(
                **patch
            )

        return await self.get_statement(tenant_id, statement_id)

    async def mark_sent(
        self,
        tenant_id: int,
        statement_id: int,
        user_id: int,
        channel: str,
        notes: Optional[str] = None,
    ) -> PartnerStatement:
        obj = await self.get_statement(tenant_id, statement_id)
        if obj.status != "Confirmed":
            raise BusinessLogicError("请先确认对账单后再标记发送")
        if str(obj.review_status or "").strip() not in ("已审核", "approved"):
            raise BusinessLogicError("请先审核通过对账单后再标记发送")
        allowed = ("export", "print", "wechat_manual", "email_manual", "other")
        if channel not in allowed:
            raise ValidationError(f"发送渠道无效，可选: {', '.join(allowed)}")
        obj.status = "Sent"
        obj.sent_at = tortoise_timezone.now()
        obj.sent_by = user_id
        obj.sent_channel = channel
        if notes:
            obj.notes = (obj.notes or "") + ("\n" if obj.notes else "") + notes
        operator = await User.filter(id=user_id).first()
        apply_update_audit(obj, operator)
        await obj.save()
        return obj

    async def dispute_statement(
        self, tenant_id: int, statement_id: int, reason: str, user_id: Optional[int] = None
    ) -> PartnerStatement:
        obj = await self.get_statement(tenant_id, statement_id)
        if obj.status not in ("Sent", "Confirmed"):
            raise BusinessLogicError("仅已确认或已发送的对账单可记录异议")
        obj.status = "Disputed"
        obj.dispute_reason = reason.strip()
        obj.disputed_at = tortoise_timezone.now()
        if user_id is not None:
            operator = await User.filter(id=user_id).first()
            apply_update_audit(obj, operator)
        await obj.save()
        return obj

    def _ensure_statement_content_editable(self, obj: PartnerStatement) -> None:
        if not self._statement_content_editable(obj):
            raise BusinessLogicError("当前状态不可修改对账内容，请先撤回审核或撤销确认")

    @staticmethod
    def _line_amount_inputs_from_stored_lines(
        lines: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        by_key: Dict[Tuple[str, int], Dict[str, Any]] = {}
        for ln in collapse_material_lines_to_document_lines(lines):
            if int(ln.get("tree_level") or 0) > 0:
                continue
            doc_id = ln.get("doc_id")
            doc_type = ln.get("doc_type")
            key = _line_doc_key(doc_type, doc_id)
            if not key:
                continue
            raw = ln.get("statement_amount")
            if raw is None:
                raw = ln.get("remaining_amount")
            if raw is None:
                raw = ln.get("doc_amount")
            if raw is None:
                debit = float(ln.get("debit") or 0)
                credit = float(ln.get("credit") or 0)
                raw = debit if debit > 0 else credit
            amount = _q_money(raw)
            if amount <= 0:
                continue
            prev = by_key.get(key)
            if prev is None:
                by_key[key] = {
                    "doc_type": doc_type,
                    "doc_id": int(doc_id),
                    "statement_amount": float(amount),
                }
            else:
                prev["statement_amount"] = float(_q_money(prev["statement_amount"]) + amount)
        return list(by_key.values())

    async def update_statement_header(
        self,
        tenant_id: int,
        statement_id: int,
        *,
        ledger_posting_mode: Optional[str] = None,
        user_id: int,
    ) -> PartnerStatement:
        obj = await self.get_statement(tenant_id, statement_id)
        self._ensure_statement_content_editable(obj)
        if ledger_posting_mode is None:
            raise ValidationError("请提供立账方式")
        mode = str(ledger_posting_mode).strip()
        if mode not in PARTNER_STATEMENT_LEDGER_MODES:
            raise ValidationError("ledger_posting_mode 须为 immediate 或 by_invoice")
        if not await self._statement_supports_ledger_modes(obj):
            if mode != "immediate":
                raise ValidationError("当前对账单无可按月结立账的业务源单，立账方式须为立即立账")
            mode = "immediate"
        obj.ledger_posting_mode = mode
        operator = await User.filter(id=user_id).first()
        apply_update_audit(obj, operator)
        await obj.save()
        return obj

    async def refresh_statement_preview(
        self,
        tenant_id: int,
        statement_id: int,
        amount_basis: str,
        user_id: int,
    ) -> Tuple[PartnerStatement, List[str]]:
        obj = await self.get_statement(tenant_id, statement_id)
        self._ensure_statement_content_editable(obj)
        basis = parse_statement_amount_basis(amount_basis)
        details = dict(obj.transaction_details or {})
        current_lines = list(details.get("document_lines") or [])
        if not current_lines:
            current_lines = collapse_material_lines_to_document_lines(
                list(details.get("lines") or [])
            )
        if not current_lines:
            raise BusinessLogicError("对账单无明细行")
        line_amounts = self._line_amount_inputs_from_stored_lines(current_lines)
        if not line_amounts:
            raise BusinessLogicError("对账单无对账明细，无法刷新")

        prior_keys: set[Tuple[str, int]] = set()
        doc_code_by_key: Dict[Tuple[str, int], str] = {}
        for ln in current_lines:
            if int(ln.get("tree_level") or 0) > 0:
                continue
            key = _line_doc_key(ln.get("doc_type"), ln.get("doc_id"))
            if not key:
                continue
            prior_keys.add(key)
            doc_code_by_key[key] = str(ln.get("doc_code") or ln.get("doc_id") or "")

        preview = await self.preview_statement(
            tenant_id,
            obj.partner_id,
            obj.partner_type,
            obj.start_date,
            obj.end_date,
            basis,
        )
        preview_doc_lines = list(preview.get("document_lines") or [])
        if not preview_doc_lines:
            preview_doc_lines = collapse_material_lines_to_document_lines(
                list(preview.get("lines") or [])
            )
        prior_map = await self._load_prior_stated_amounts(
            tenant_id,
            obj.partner_id,
            obj.partner_type,
            exclude_statement_id=statement_id,
        )
        overrides = self._build_line_amount_override_map(line_amounts)
        rebuilt = self._apply_line_amount_overrides_to_preview_lines(
            preview_doc_lines, prior_map, overrides
        )
        if not rebuilt:
            raise BusinessLogicError("刷新后无有效对账明细，请检查期间与勾选")

        new_keys = {
            k
            for ln in rebuilt
            if (k := _line_doc_key(ln.get("doc_type"), ln.get("doc_id")))
        }
        warnings: List[str] = []
        for key in prior_keys:
            if key not in new_keys:
                code = doc_code_by_key.get(key) or str(key[1])
                warnings.append(f"单据 {code} 在新预览中不可再纳入")

        opening = _q_money(preview["summary"]["opening_balance"])
        rebuilt = await self._order_lines_by_settlement_hierarchy(
            tenant_id, obj.partner_type, rebuilt
        )
        debit_total, credit_total, closing, lines = self._apply_running_balance(opening, rebuilt)
        summary = {
            "opening_balance": float(opening),
            "debit_total": float(debit_total),
            "credit_total": float(credit_total),
            "closing_balance": float(closing),
        }
        from apps.kuaicaiwu.services.partner_statement_line_service import (
            PartnerStatementLineService,
        )

        line_svc = PartnerStatementLineService()
        material_lines = await line_svc.expand_preview_lines_to_material_lines(
            tenant_id, lines, self
        )
        details["document_lines"] = lines
        details["lines"] = material_lines
        details["summary"] = summary
        details["amount_basis"] = basis
        obj.transaction_details = details
        obj.opening_balance = opening
        obj.debit_total = debit_total
        obj.credit_total = credit_total
        obj.closing_balance = closing
        operator = await User.filter(id=user_id).first()
        apply_update_audit(obj, operator)
        read_only = str(obj.review_status or "") in ("已审核", "approved", "APPROVED")
        from tortoise.transactions import in_transaction

        async with in_transaction():
            await obj.save()
            await line_svc.replace_statement_lines(
                tenant_id, obj, material_lines, amount_basis=basis, is_read_only=read_only
            )
        return obj, warnings

    async def update_statement_lines(
        self,
        tenant_id: int,
        statement_id: int,
        line_amounts: List[Dict[str, Any]],
        user_id: int,
    ) -> PartnerStatement:
        obj = await self.get_statement(tenant_id, statement_id)
        self._ensure_statement_content_editable(obj)
        details = dict(obj.transaction_details or {})
        current_lines = list(details.get("document_lines") or [])
        if not current_lines:
            current_lines = collapse_material_lines_to_document_lines(
                list(details.get("lines") or [])
            )
        if not current_lines:
            raise BusinessLogicError("对账单无明细行")
        prior_map = await self._load_prior_stated_amounts(
            tenant_id,
            obj.partner_id,
            obj.partner_type,
            exclude_statement_id=statement_id,
        )
        overrides = self._build_line_amount_override_map(line_amounts)
        if not overrides:
            raise ValidationError("请提供至少一行对账金额")
        rebuilt = self._apply_line_amount_overrides_to_preview_lines(
            current_lines, prior_map, overrides
        )
        if not rebuilt:
            raise BusinessLogicError("对账明细不能为空")
        opening = _q_money(obj.opening_balance)
        rebuilt = await self._order_lines_by_settlement_hierarchy(
            tenant_id, obj.partner_type, rebuilt
        )
        debit_total, credit_total, closing, lines = self._apply_running_balance(opening, rebuilt)
        summary = {
            "opening_balance": float(opening),
            "debit_total": float(debit_total),
            "credit_total": float(credit_total),
            "closing_balance": float(closing),
        }
        basis = str(details.get("amount_basis") or "tax_inclusive")
        from apps.kuaicaiwu.services.partner_statement_line_service import (
            PartnerStatementLineService,
        )

        line_svc = PartnerStatementLineService()
        material_lines = await line_svc.expand_preview_lines_to_material_lines(
            tenant_id, lines, self
        )
        details["document_lines"] = lines
        details["lines"] = material_lines
        details["summary"] = summary
        obj.transaction_details = details
        obj.debit_total = debit_total
        obj.credit_total = credit_total
        obj.closing_balance = closing
        operator = await User.filter(id=user_id).first()
        apply_update_audit(obj, operator)
        read_only = str(obj.review_status or "") in ("已审核", "approved", "APPROVED")
        from tortoise.transactions import in_transaction

        async with in_transaction():
            await obj.save()
            await line_svc.replace_statement_lines(
                tenant_id, obj, material_lines, amount_basis=basis, is_read_only=read_only
            )
        if obj.status in ("Draft", "Disputed"):
            return await self.confirm_business_statement(tenant_id, statement_id, user_id)
        return await self.get_statement(tenant_id, statement_id)

    async def delete_statement(self, tenant_id: int, statement_id: int) -> None:
        obj = await self.get_statement(tenant_id, statement_id)
        if obj.status != "Draft":
            raise BusinessLogicError("仅草稿状态的对账单可删除")
        obj.deleted_at = tortoise_timezone.now()
        await obj.save()

    _PURCHASE_RECEIPT_DOC_TYPES = frozenset({
        "purchase_receipt", "采购入库", "purchase_receipts",
    })
    _OUTSOURCE_RECEIPT_DOC_TYPES = frozenset({
        "outsource_material_receipt",
        "outsource_order_receipt",
        "委外收货",
        "工序委外收货",
        "outsource_receipt",
    })
    _SALES_DELIVERY_DOC_TYPES = frozenset({
        "sales_delivery", "销售出库", "sales_deliveries",
    })

    def _normalize_inbound_doc_type(self, doc_type: str) -> str:
        normalized = (doc_type or "").strip()
        if normalized in self._PURCHASE_RECEIPT_DOC_TYPES:
            return "purchase_receipt"
        if normalized in self._OUTSOURCE_RECEIPT_DOC_TYPES:
            return "outsource_material_receipt"
        if normalized in self._SALES_DELIVERY_DOC_TYPES:
            return "sales_delivery"
        raise ValidationError(
            "doc_type 仅支持 purchase_receipt/采购入库、"
            "outsource_material_receipt/委外收货 或 sales_delivery/销售出库"
        )

    async def get_statement_line_detail(
        self, tenant_id: int, doc_type: str, doc_id: int
    ) -> Dict[str, Any]:
        """返回采购入库、销售出库或委外收货明细行（含质检字段），供对账单明细展开与弹窗。"""
        kind = self._normalize_inbound_doc_type(doc_type)
        if kind == "purchase_receipt":
            return await self._build_purchase_receipt_line_detail(tenant_id, doc_id)
        if kind == "sales_delivery":
            return await self._build_sales_delivery_line_detail(tenant_id, doc_id)
        return await self._build_outsource_receipt_line_detail(tenant_id, doc_id)

    async def _build_sales_delivery_line_detail(
        self, tenant_id: int, delivery_id: int
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.sales_delivery import SalesDelivery
        from apps.kuaizhizao.models.sales_delivery_item import SalesDeliveryItem
        from apps.kuaizhizao.constants.price_type import normalize_price_type
        from apps.kuaizhizao.utils.sales_price_amount import stored_sales_line_amount

        delivery = await SalesDelivery.get_or_none(
            tenant_id=tenant_id, id=delivery_id, deleted_at__isnull=True
        )
        if not delivery:
            raise NotFoundError(f"销售出库单不存在: {delivery_id}")
        price_type = normalize_price_type(getattr(delivery, "price_type", None))
        items = await SalesDeliveryItem.filter(
            tenant_id=tenant_id, delivery_id=delivery_id, deleted_at__isnull=True
        ).order_by("id").all()
        detail_items: List[Dict[str, Any]] = []
        for item in items:
            qty = float(item.delivery_quantity or 0)
            unit_price = float(item.unit_price or 0)
            tax_rate = float(getattr(item, "tax_rate", 0) or 0)
            line_amount = float(
                stored_sales_line_amount(
                    qty,
                    unit_price,
                    tax_rate,
                    price_type,
                    is_gift=bool(getattr(item, "is_gift", False)),
                )
            )
            detail_items.append({
                "id": item.id,
                "source_line_id": item.id,
                "material_id": item.material_id,
                "material_code": item.material_code,
                "material_name": item.material_name,
                "material_spec": getattr(item, "material_spec", None),
                "unit": item.material_unit,
                "quantity": qty,
                "unit_price": unit_price,
                "amount": line_amount,
            })
        return {
            "doc_type": "sales_delivery",
            "doc_id": delivery.id,
            "doc_code": delivery.delivery_code,
            "partner_name": delivery.customer_name,
            "items": detail_items,
        }

    async def _build_purchase_receipt_line_detail(
        self, tenant_id: int, receipt_id: int
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
        from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem
        from apps.kuaizhizao.models.incoming_inspection import IncomingInspection

        receipt = await PurchaseReceipt.get_or_none(
            tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
        )
        if not receipt:
            raise NotFoundError(f"采购入库单不存在: {receipt_id}")

        items = await PurchaseReceiptItem.filter(
            tenant_id=tenant_id, receipt_id=receipt_id, deleted_at__isnull=True
        ).order_by("id").all()
        inspections = await IncomingInspection.filter(
            tenant_id=tenant_id,
            purchase_receipt_id=receipt_id,
            deleted_at__isnull=True,
        ).all()
        inspection_by_material: Dict[int, IncomingInspection] = {}
        for insp in inspections:
            mid = int(insp.material_id)
            if mid not in inspection_by_material:
                inspection_by_material[mid] = insp

        detail_items: List[Dict[str, Any]] = []
        for item in items:
            insp = inspection_by_material.get(int(item.material_id))
            process_waste, material_waste = _extract_waste_quantities(
                getattr(insp, "other_checks", None) if insp else None
            )
            inspection_date = None
            if insp and insp.inspection_time:
                inspection_date = to_api_isoformat(insp.inspection_time)
            insp_qty = None
            if insp is not None and getattr(insp, "inspection_quantity", None) is not None:
                insp_qty = float(insp.inspection_quantity)
            detail_items.append({
                "id": item.id,
                "source_line_id": item.id,
                "material_id": item.material_id,
                "material_code": item.material_code,
                "material_name": item.material_name,
                "material_spec": item.material_spec,
                "unit": item.material_unit,
                "quantity": float(item.receipt_quantity or 0),
                "unit_price": float(item.unit_price or 0),
                "amount": float(item.total_amount or 0),
                "inspection_quantity": insp_qty,
                "qualified_quantity": float(
                    (insp.qualified_quantity if insp and insp.qualified_quantity is not None else item.qualified_quantity)
                    or 0
                ),
                "unqualified_quantity": float(
                    (
                        insp.unqualified_quantity
                        if insp and insp.unqualified_quantity is not None
                        else item.unqualified_quantity
                    )
                    or 0
                ),
                "quality_status": (
                    getattr(insp, "quality_status", None) if insp else None
                ) or item.quality_status,
                "inspection_date": inspection_date,
                "inspection_passed": _inspection_passed(insp),
                "defect_reason": getattr(insp, "nonconformance_reason", None) if insp else None,
                "process_waste_qty": process_waste,
                "material_waste_qty": material_waste,
            })

        return {
            "doc_type": "purchase_receipt",
            "doc_id": receipt.id,
            "doc_code": receipt.receipt_code,
            "partner_name": receipt.supplier_name,
            "items": detail_items,
        }

    async def _build_outsource_receipt_line_detail(
        self, tenant_id: int, receipt_id: int
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.outsource_work_order import (
            OutsourceMaterialReceipt,
            OutsourceWorkOrder,
        )

        receipt = await OutsourceMaterialReceipt.get_or_none(
            tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
        )
        if not receipt:
            raise NotFoundError(f"委外收货单不存在: {receipt_id}")

        work_order = await OutsourceWorkOrder.get_or_none(
            tenant_id=tenant_id,
            id=receipt.outsource_work_order_id,
            deleted_at__isnull=True,
        )
        unit_price = Decimal(str(work_order.unit_price or 0)) if work_order else Decimal("0")
        receipt_qty = Decimal(str(receipt.quantity or 0))
        # 与应付生成一致：按合格数量（无合格则按收货数量）× 委外单价
        settle_qty = Decimal(str(receipt.qualified_quantity or receipt.quantity or 0))
        amount = (settle_qty * unit_price).quantize(_MONEY)
        inspection_date = (
            to_api_isoformat(receipt.received_at) if receipt.received_at else None
        )
        unqualified = Decimal(str(receipt.unqualified_quantity or 0))
        qualified = Decimal(str(receipt.qualified_quantity or 0))
        passed = None
        if receipt.received_at is not None or (qualified + unqualified) > 0:
            passed = unqualified <= 0
        process_waste_raw = receipt.process_waste_qty
        material_waste_raw = receipt.material_waste_qty
        defect_reason = receipt.nonconformance_reason or ((receipt.remarks or "").strip() or None)

        detail_items = [{
            "material_code": work_order.product_code if work_order else "",
            "material_name": work_order.product_name if work_order else "",
            "material_spec": getattr(work_order, "product_spec", None) if work_order else None,
            "unit": receipt.unit,
            "quantity": float(receipt_qty),
            "unit_price": float(unit_price),
            "amount": float(amount),
            "inspection_quantity": float(receipt_qty),
            "qualified_quantity": float(qualified),
            "unqualified_quantity": float(unqualified),
            "quality_status": "合格" if passed else ("不合格" if passed is False else None),
            "inspection_date": inspection_date,
            "inspection_passed": passed,
            "defect_reason": defect_reason,
            "process_waste_qty": float(process_waste_raw) if process_waste_raw is not None else None,
            "material_waste_qty": float(material_waste_raw) if material_waste_raw is not None else None,
        }]

        return {
            "doc_type": "outsource_material_receipt",
            "doc_id": receipt.id,
            "doc_code": receipt.code,
            "partner_name": work_order.supplier_name if work_order else None,
            "items": detail_items,
        }

    async def _statement_export_context(self, obj: PartnerStatement) -> Dict[str, Any]:
        details = dict(obj.transaction_details or {})
        lines = await self.ensure_statement_line_hierarchy(
            obj.tenant_id,
            obj.partner_type,
            _q_money(obj.opening_balance),
            list(details.get("lines") or []),
        )
        lines = await self.enrich_lines_invoice_dates(obj.tenant_id, lines)
        return {
            "statement_code": obj.statement_code,
            "company_name": obj.company_name or "本公司",
            "partner_name": obj.partner_name,
            "partner_type": obj.partner_type,
            "period": obj.statement_period,
            "start_date": to_api_isoformat(obj.start_date),
            "end_date": to_api_isoformat(obj.end_date),
            "status": obj.status,
            "balance_label": details.get("balance_label") or (
                "应收余额" if obj.partner_type == "Customer" else "应付余额"
            ),
            "summary": details.get("summary") or {
                "opening_balance": float(obj.opening_balance),
                "debit_total": float(obj.debit_total),
                "credit_total": float(obj.credit_total),
                "closing_balance": float(obj.closing_balance),
            },
            "lines": lines,
            "partner_snapshot": details.get("partner_snapshot") or {},
            "notes": obj.notes,
            "amount_basis": details.get("amount_basis"),
        }

    @staticmethod
    def _export_stored_amount(ln: Dict[str, Any], key: str):
        if ln.get(key) is None:
            return "—"
        return float(_q_money(ln[key]))

    @staticmethod
    def _export_doc_type_label(ln: Dict[str, Any]) -> str:
        doc_type = str(ln.get("doc_type") or "")
        if int(ln.get("tree_level") or 0) > 0:
            return f"  └ {doc_type}"
        return doc_type

    async def export_excel(self, obj: PartnerStatement) -> BytesIO:
        ctx = await self._statement_export_context(obj)
        wb = Workbook()
        ws = wb.active
        ws.title = "往来对账单"
        title_font = Font(name="Microsoft YaHei", size=14, bold=True)
        header_font = Font(name="Microsoft YaHei", size=11, bold=True)
        body_font = Font(name="Microsoft YaHei", size=11)

        ws["A1"] = f"{ctx['company_name']} — 往来对账单"
        ws["A1"].font = title_font
        ws.merge_cells("A1:L1")
        ws["A2"] = f"对账单号：{ctx['statement_code']}"
        ws["A3"] = f"往来单位：{ctx['partner_name']}"
        ws["A4"] = f"对账期间：{ctx['start_date']} 至 {ctx['end_date']}"
        if ctx.get("amount_basis") == AMOUNT_BASIS_TAX_INCLUSIVE:
            ws["A6"] = "金额口径：含税"
        elif ctx.get("amount_basis") == AMOUNT_BASIS_TAX_EXCLUSIVE:
            ws["A6"] = "金额口径：不含税"
        snap = ctx.get("partner_snapshot") or {}
        if snap.get("finance_contact_name"):
            ws["A5"] = f"财务联系人：{snap.get('finance_contact_name')} {snap.get('finance_contact_phone') or ''}"

        row = 7
        summary = ctx["summary"]
        ws.cell(row, 1, "期初余额").font = header_font
        ws.cell(row, 2, summary["opening_balance"])
        ws.cell(row, 3, "本期借方").font = header_font
        ws.cell(row, 4, summary["debit_total"])
        ws.cell(row, 5, "本期贷方").font = header_font
        ws.cell(row, 6, summary["credit_total"])
        ws.cell(row, 7, "期末余额").font = header_font
        row += 1
        ws.cell(row, 1, summary["opening_balance"])
        ws.cell(row, 3, summary["debit_total"])
        ws.cell(row, 5, summary["credit_total"])
        ws.cell(row, 7, summary["closing_balance"])

        row += 2
        headers = [
            "日期", "单据类型", "单号", "摘要", "开票日期",
            "不含税金额", "税额", "价税合计", "单据金额",
            "借方", "贷方", ctx["balance_label"],
        ]
        for col, h in enumerate(headers, 1):
            c = ws.cell(row, col, h)
            c.font = header_font
            c.alignment = Alignment(horizontal="center")
        row += 1
        for ln in ctx["lines"]:
            ws.cell(row, 1, ln.get("date", "")).font = body_font
            ws.cell(row, 2, self._export_doc_type_label(ln)).font = body_font
            ws.cell(row, 3, ln.get("doc_code", "")).font = body_font
            ws.cell(row, 4, ln.get("summary", "")).font = body_font
            ws.cell(row, 5, ln.get("invoice_date") or "—").font = body_font
            ws.cell(row, 6, self._export_stored_amount(ln, "amount_excluding_tax")).font = body_font
            ws.cell(row, 7, self._export_stored_amount(ln, "tax_amount")).font = body_font
            ws.cell(row, 8, self._export_stored_amount(ln, "amount_including_tax")).font = body_font
            ws.cell(row, 9, ln.get("doc_amount") if ln.get("doc_amount") is not None else "—").font = body_font
            ws.cell(row, 10, ln.get("debit", 0)).font = body_font
            ws.cell(row, 11, ln.get("credit", 0)).font = body_font
            ws.cell(row, 12, ln.get("balance", 0)).font = body_font
            row += 1

        row += 1
        ws.cell(row, 1, "请于收到本对账单后 7 个工作日内核对并回复；如有异议请注明。").font = body_font

        out = BytesIO()
        wb.save(out)
        out.seek(0)
        return out
    async def render_html(self, obj: PartnerStatement) -> str:
        ctx = await self._statement_export_context(obj)
        summary = ctx["summary"]
        snap = ctx.get("partner_snapshot") or {}
        contact = ""
        if snap.get("finance_contact_name"):
            contact = f"<p>财务联系人：{snap['finance_contact_name']} {snap.get('finance_contact_phone') or ''}</p>"
        basis_label = ""
        if ctx.get("amount_basis") == AMOUNT_BASIS_TAX_INCLUSIVE:
            basis_label = "<p>金额口径：含税</p>"
        elif ctx.get("amount_basis") == AMOUNT_BASIS_TAX_EXCLUSIVE:
            basis_label = "<p>金额口径：不含税</p>"

        def _html_amount(ln: Dict[str, Any], key: str) -> str:
            if ln.get(key) is None:
                return "—"
            return f"{float(_q_money(ln[key])):,.2f}"

        rows_html = ""
        for ln in ctx["lines"]:
            doc_amount = "—" if ln.get("doc_amount") is None else f"{float(_q_money(ln.get('doc_amount'))):,.2f}"
            rows_html += f"""
            <tr>
              <td>{ln.get('date', '')}</td>
              <td>{self._export_doc_type_label(ln)}</td>
              <td>{ln.get('doc_code', '')}</td>
              <td>{ln.get('summary', '')}</td>
              <td>{ln.get('invoice_date') or '—'}</td>
              <td class="num">{_html_amount(ln, 'amount_excluding_tax')}</td>
              <td class="num">{_html_amount(ln, 'tax_amount')}</td>
              <td class="num">{_html_amount(ln, 'amount_including_tax')}</td>
              <td class="num">{doc_amount}</td>
              <td class="num">{ln.get('debit', 0):,.2f}</td>
              <td class="num">{ln.get('credit', 0):,.2f}</td>
              <td class="num">{ln.get('balance', 0):,.2f}</td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>往来对账单 {ctx['statement_code']}</title>
<style>
  body {{ font-family: "Microsoft YaHei", sans-serif; font-size: 12px; color: #333; padding: 24px; }}
  h1 {{ font-size: 18px; text-align: center; margin-bottom: 8px; }}
  .meta p {{ margin: 4px 0; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 8px; }}
  th {{ background: #f5f5f5; }}
  .num {{ text-align: right; }}
  .summary {{ margin-top: 12px; }}
  .footer {{ margin-top: 20px; color: #666; font-size: 11px; }}
  @media print {{ body {{ padding: 0; }} }}
</style></head><body>
<h1>{ctx['company_name']} — 往来对账单</h1>
<div class="meta">
  <p>对账单号：{ctx['statement_code']}</p>
  <p>往来单位：{ctx['partner_name']}</p>
  <p>对账期间：{ctx['start_date']} 至 {ctx['end_date']}</p>
  {contact}
</div>
<div class="summary">
  <p>期初余额：<strong>{summary['opening_balance']:,.2f}</strong>
     &nbsp;|&nbsp; 本期借方：<strong>{summary['debit_total']:,.2f}</strong>
     &nbsp;|&nbsp; 本期贷方：<strong>{summary['credit_total']:,.2f}</strong>
     &nbsp;|&nbsp; 期末余额：<strong>{summary['closing_balance']:,.2f}</strong></p>
</div>
<table>
  <thead><tr>
    <th>日期</th><th>单据类型</th><th>单号</th><th>摘要</th>
    <th>借方</th><th>贷方</th><th>{ctx['balance_label']}</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>
<p class="footer">请于收到本对账单后 7 个工作日内核对并回复；如有异议请注明。</p>
</body></html>"""

    async def export_pdf(self, obj: PartnerStatement) -> Tuple[bytes, str]:
        html = await self.render_html(obj)
        from apps.kuaizhizao.services.print_service import html_to_pdf_bytes

        pdf_bytes, _ = await html_to_pdf_bytes(html)
        return pdf_bytes, "application/pdf"
