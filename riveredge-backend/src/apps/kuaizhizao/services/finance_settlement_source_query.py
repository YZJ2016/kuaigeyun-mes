"""
只读：按对账单立账策略下，尚未生成应收/应付的业务源单查询。
供 kuaicaiwu 往来对账单预览与期初调节使用，禁止在此模块写入 kuaizhizao 表。

纳入条件以**单据头** revenue_recognition / payable_recognition == on_partner_statement 为真源，
禁止只认客商/组织默认策略而漏掉单据已选「按月结对账单」的入库/出库。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

from tortoise.expressions import Q

from apps.kuaicaiwu.constants.finance_source_types import (
    PAYABLE_SOURCE_OUTSOURCE_ORDER_RECEIPT,
    PAYABLE_SOURCE_OUTSOURCE_RECEIPT,
    PAYABLE_SOURCE_PURCHASE_RECEIPT,
    PAYABLE_SOURCE_PURCHASE_RETURN,
    RECEIVABLE_SOURCE_SALES_DELIVERY,
    RECEIVABLE_SOURCE_SALES_RETURN,
)
from apps.kuaicaiwu.models.payable import Payable
from apps.kuaicaiwu.models.receivable import Receivable
from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
from apps.kuaizhizao.models.purchase_return import PurchaseReturn
from apps.kuaizhizao.models.sales_delivery import SalesDelivery
from apps.kuaizhizao.models.sales_return import SalesReturn
from apps.kuaizhizao.services.document_recognition import (
    payable_recognition_from_doc,
    revenue_recognition_from_doc,
)
from core.utils.timezone_utils import to_site_date

_EXCLUDED_REVIEW = ("待审核", "驳回", "已驳回", "rejected", "审核驳回", "草稿", "PENDING", "DRAFT")
_MONEY = Decimal("0.01")
# 与仓储确认态对齐：禁止只认「已入库/已出库」漏掉「已完成」等同义状态
_PURCHASE_RECEIPT_POSTED_STATUSES = ("已入库", "已完成", "completed", "COMPLETED", "processed", "POSTED")
_SALES_DELIVERY_POSTED_STATUSES = ("已出库", "已完成", "completed", "COMPLETED", "processed", "POSTED", "done", "DONE")
_SALES_RETURN_POSTED_STATUSES = ("已退货", "completed", "已完成", "RETURNED")
_PURCHASE_RETURN_POSTED_STATUSES = ("已退货", "completed", "已完成", "RETURNED")


def _q_money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value or 0)).quantize(_MONEY)


async def _sales_delivery_amount_parts(
    tenant_id: int,
    delivery: SalesDelivery,
) -> Dict[str, float]:
    """按出库明细汇总未税、税额、价税合计（与价类一致）。"""
    from apps.kuaizhizao.constants.price_type import normalize_price_type
    from apps.kuaizhizao.models.sales_delivery_item import SalesDeliveryItem
    from apps.kuaizhizao.utils.sales_price_amount import calc_sales_line_amounts

    items = await SalesDeliveryItem.filter(
        tenant_id=tenant_id,
        delivery_id=int(delivery.id),
        deleted_at__isnull=True,
    ).all()
    price_type = normalize_price_type(getattr(delivery, "price_type", None))
    excl = Decimal("0")
    tax = Decimal("0")
    incl = Decimal("0")
    for it in items:
        if bool(getattr(it, "is_gift", False)):
            continue
        line_excl, line_tax, line_incl = calc_sales_line_amounts(
            Decimal(str(getattr(it, "delivery_quantity", 0) or 0)),
            Decimal(str(getattr(it, "unit_price", 0) or 0)),
            Decimal(str(getattr(it, "tax_rate", 0) or 0)),
            price_type,
        )
        excl += line_excl
        tax += line_tax
        incl += line_incl
    if incl <= 0:
        incl = _q_money(getattr(delivery, "total_amount", 0) or 0)
    if excl <= 0 and incl > 0 and tax <= 0:
        excl = incl
    return {
        "amount_excluding_tax": float(_q_money(excl)),
        "tax_amount": float(_q_money(tax)),
        "amount_including_tax": float(_q_money(incl if incl > 0 else excl)),
    }


def _business_date_from_row(dt: Optional[datetime]) -> Optional[date]:
    if dt is None:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt
    return to_site_date(dt)


def _coerce_sort_date(value: Any) -> date:
    """排序/区间比较统一为 date，避免 str 与 date 混比。"""
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


def _line_sort_key(ln: Dict[str, Any]) -> Tuple[date, str, int]:
    raw = ln.get("sort_date")
    if raw is None:
        raw = ln.get("date")
    try:
        doc_id = int(ln.get("doc_id") or 0)
    except (TypeError, ValueError):
        doc_id = 0
    return (_coerce_sort_date(raw), str(ln.get("doc_type") or ""), doc_id)


def _in_date_range(
    biz: Optional[date | datetime | str],
    start: date | datetime | str,
    end: date | datetime | str,
) -> bool:
    if biz is None:
        return False
    return _coerce_sort_date(start) <= _coerce_sort_date(biz) <= _coerce_sort_date(end)


async def _posted_source_ids(
    tenant_id: int,
    source_type: str,
    source_ids: List[int],
) -> Set[int]:
    if not source_ids:
        return set()
    rows = await Receivable.filter(
        tenant_id=tenant_id,
        source_type=source_type,
        source_id__in=source_ids,
        deleted_at__isnull=True,
    ).only("source_id").all()
    posted = {int(r.source_id) for r in rows if r.source_id is not None}
    rows_p = await Payable.filter(
        tenant_id=tenant_id,
        source_type=source_type,
        source_id__in=source_ids,
        deleted_at__isnull=True,
    ).only("source_id").all()
    posted |= {int(p.source_id) for p in rows_p if p.source_id is not None}
    return posted


async def _posted_receivable_source_ids(
    tenant_id: int,
    source_type: str,
    source_ids: List[int],
) -> Set[int]:
    if not source_ids:
        return set()
    rows = await Receivable.filter(
        tenant_id=tenant_id,
        source_type=source_type,
        source_id__in=source_ids,
        deleted_at__isnull=True,
    ).only("source_id").all()
    return {int(r.source_id) for r in rows if r.source_id is not None}


async def _posted_payable_source_ids(
    tenant_id: int,
    source_type: str,
    source_ids: List[int],
) -> Set[int]:
    if not source_ids:
        return set()
    rows = await Payable.filter(
        tenant_id=tenant_id,
        source_type=source_type,
        source_id__in=source_ids,
        deleted_at__isnull=True,
    ).only("source_id").all()
    return {int(p.source_id) for p in rows if p.source_id is not None}


async def partner_statement_ledger_posted_doc_ids(
    tenant_id: int,
    partner_id: int,
    partner_type: str,
) -> Set[Tuple[str, int]]:
    """已对账立账的 (doc_type, doc_id)，含按行旧应付与整单对账立账。"""
    from apps.kuaicaiwu.models.partner_statement import PartnerStatement

    out: Set[Tuple[str, int]] = set()
    rows = await PartnerStatement.filter(
        tenant_id=tenant_id,
        partner_id=partner_id,
        partner_type=partner_type,
        ledger_posted_at__not_isnull=True,
        deleted_at__isnull=True,
    ).only("transaction_details").all()
    for stmt in rows:
        details = stmt.transaction_details if isinstance(stmt.transaction_details, dict) else {}
        for ln in details.get("lines") or []:
            if int(ln.get("tree_level") or 0) > 0:
                continue
            dt = str(ln.get("doc_type") or "").strip()
            did = ln.get("doc_id")
            if not dt or did is None:
                continue
            try:
                out.add((dt, int(did)))
            except (TypeError, ValueError):
                continue
    return out


def _settlement_line(
    *,
    biz_date: date,
    doc_type: str,
    doc_code: str,
    doc_id: int,
    amount: Decimal,
    finance_source_type: str,
    is_credit: bool,
    summary: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    amt = float(_q_money(amount))
    row: Dict[str, Any] = {
        "date": biz_date.isoformat(),
        "sort_date": biz_date,
        "doc_type": doc_type,
        "doc_code": doc_code,
        "summary": summary,
        "debit": 0.0 if is_credit else amt,
        "credit": amt if is_credit else 0.0,
        "doc_id": doc_id,
        "doc_amount": amt,
        "finance_source_type": finance_source_type,
        "settlement_source_id": doc_id,
    }
    if extra:
        row.update(extra)
    return row


class FinanceSettlementSourceQuery:
    """未立账业务源单只读查询。"""

    async def list_customer_unposted_lines(
        self,
        tenant_id: int,
        customer_id: int,
        start_date: date,
        end_date: date,
        *,
        require_statement_strategy: bool = True,
    ) -> List[Dict[str, Any]]:
        lines: List[Dict[str, Any]] = []

        deliveries = await SalesDelivery.filter(
            tenant_id=tenant_id,
            customer_id=customer_id,
            status__in=list(_SALES_DELIVERY_POSTED_STATUSES),
            deleted_at__isnull=True,
        ).exclude(review_status__in=_EXCLUDED_REVIEW).order_by("delivery_time", "id").all()

        delivery_ids = [int(d.id) for d in deliveries]
        posted_del = await _posted_receivable_source_ids(
            tenant_id, RECEIVABLE_SOURCE_SALES_DELIVERY, delivery_ids
        )
        stmt_covered = await partner_statement_ledger_posted_doc_ids(
            tenant_id, customer_id, "Customer"
        )
        for d in deliveries:
            if (
                require_statement_strategy
                and revenue_recognition_from_doc(d) != "on_partner_statement"
            ):
                continue
            biz = _business_date_from_row(d.delivery_time) or _business_date_from_row(d.review_time)
            if not _in_date_range(biz, start_date, end_date):
                continue
            if ("销售出库", int(d.id)) in stmt_covered:
                continue
            if int(d.id) in posted_del:
                continue
            parts = await _sales_delivery_amount_parts(tenant_id, d)
            active = _q_money(
                parts["amount_including_tax"]
                if parts["amount_including_tax"] > 0
                else d.total_amount
            )
            if active <= 0:
                continue
            lines.append(
                _settlement_line(
                    biz_date=biz,
                    doc_type="销售出库",
                    doc_code=d.delivery_code,
                    doc_id=int(d.id),
                    amount=active,
                    finance_source_type=RECEIVABLE_SOURCE_SALES_DELIVERY,
                    is_credit=False,
                    summary=f"销售出库 {d.delivery_code}",
                    extra={
                        "inbound_detail_doc_type": "sales_delivery",
                        "inbound_detail_doc_id": int(d.id),
                        **parts,
                    },
                )
            )

        returns = await SalesReturn.filter(
            tenant_id=tenant_id,
            customer_id=customer_id,
            status__in=list(_SALES_RETURN_POSTED_STATUSES),
            deleted_at__isnull=True,
        ).exclude(review_status__in=_EXCLUDED_REVIEW).order_by("return_time", "id").all()

        return_ids = [int(r.id) for r in returns]
        posted_ret = await _posted_receivable_source_ids(
            tenant_id, RECEIVABLE_SOURCE_SALES_RETURN, return_ids
        )
        for r in returns:
            if (
                require_statement_strategy
                and revenue_recognition_from_doc(r) != "on_partner_statement"
            ):
                continue
            biz = _business_date_from_row(r.return_time) or _business_date_from_row(r.review_time)
            if not _in_date_range(biz, start_date, end_date):
                continue
            if ("销售退货", int(r.id)) in stmt_covered:
                continue
            if int(r.id) in posted_ret:
                continue
            amt = _q_money(r.total_amount)
            if amt <= 0:
                continue
            extra: Dict[str, Any] = {}
            if r.sales_delivery_id:
                extra["offset_source_id"] = int(r.sales_delivery_id)
            lines.append(
                _settlement_line(
                    biz_date=biz,
                    doc_type="销售退货",
                    doc_code=r.return_code,
                    doc_id=int(r.id),
                    amount=amt,
                    finance_source_type=RECEIVABLE_SOURCE_SALES_RETURN,
                    is_credit=True,
                    summary=f"销售退货 {r.return_code}",
                    extra=extra,
                )
            )

        lines.sort(key=_line_sort_key)
        for ln in lines:
            ln.pop("sort_date", None)
        return lines

    async def list_supplier_unposted_lines(
        self,
        tenant_id: int,
        supplier_id: int,
        start_date: date,
        end_date: date,
        *,
        tax_inclusive: bool = True,
    ) -> List[Dict[str, Any]]:
        lines: List[Dict[str, Any]] = []

        receipts = await PurchaseReceipt.filter(
            tenant_id=tenant_id,
            supplier_id=supplier_id,
            status__in=list(_PURCHASE_RECEIPT_POSTED_STATUSES),
            deleted_at__isnull=True,
        ).exclude(review_status__in=_EXCLUDED_REVIEW).order_by("receipt_time", "id").all()

        receipt_ids = [int(p.id) for p in receipts]
        posted_rc = await _posted_payable_source_ids(
            tenant_id, PAYABLE_SOURCE_PURCHASE_RECEIPT, receipt_ids
        )
        stmt_covered = await partner_statement_ledger_posted_doc_ids(
            tenant_id, supplier_id, "Supplier"
        )
        for p in receipts:
            if payable_recognition_from_doc(p) != "on_partner_statement":
                continue
            biz = _business_date_from_row(p.receipt_time) or _business_date_from_row(p.review_time)
            if not _in_date_range(biz, start_date, end_date):
                continue
            if ("采购入库", int(p.id)) in stmt_covered:
                continue
            if int(p.id) in posted_rc:
                continue
            # total_amount=未税合计，tax_amount=税额，net_amount=价税合计。对账口径只取已保存字段。
            excl = _q_money(p.total_amount)
            tax = _q_money(p.tax_amount)
            incl = _q_money(p.net_amount)
            if incl <= 0:
                incl = excl
            active = incl if tax_inclusive else excl
            if active <= 0:
                continue
            lines.append(
                _settlement_line(
                    biz_date=biz,
                    doc_type="采购入库",
                    doc_code=p.receipt_code,
                    doc_id=int(p.id),
                    amount=active,
                    finance_source_type=PAYABLE_SOURCE_PURCHASE_RECEIPT,
                    is_credit=False,
                    summary=f"采购入库 {p.receipt_code}",
                    extra={
                        "inbound_detail_doc_type": "purchase_receipt",
                        "inbound_detail_doc_id": int(p.id),
                        "amount_excluding_tax": float(excl),
                        "tax_amount": float(tax),
                        "amount_including_tax": float(incl),
                    },
                )
            )

        returns = await PurchaseReturn.filter(
            tenant_id=tenant_id,
            supplier_id=supplier_id,
            status__in=list(_PURCHASE_RETURN_POSTED_STATUSES),
            deleted_at__isnull=True,
        ).exclude(review_status__in=_EXCLUDED_REVIEW).order_by("return_time", "id").all()

        return_ids = [int(r.id) for r in returns]
        posted_ret = await _posted_payable_source_ids(
            tenant_id, PAYABLE_SOURCE_PURCHASE_RETURN, return_ids
        )
        for r in returns:
            if payable_recognition_from_doc(r) != "on_partner_statement":
                continue
            biz = _business_date_from_row(r.return_time) or _business_date_from_row(r.review_time)
            if not _in_date_range(biz, start_date, end_date):
                continue
            if ("采购退货", int(r.id)) in stmt_covered:
                continue
            if int(r.id) in posted_ret:
                continue
            from apps.kuaicaiwu.services.return_open_balance_offset_service import (
                _resolve_purchase_return_amount,
            )

            amt = await _resolve_purchase_return_amount(
                tenant_id, r, tax_inclusive=tax_inclusive
            )
            if amt <= 0:
                continue
            extra: Dict[str, Any] = {}
            if r.purchase_receipt_id:
                extra["offset_source_id"] = int(r.purchase_receipt_id)
            lines.append(
                _settlement_line(
                    biz_date=biz,
                    doc_type="采购退货",
                    doc_code=r.return_code,
                    doc_id=int(r.id),
                    amount=amt,
                    finance_source_type=PAYABLE_SOURCE_PURCHASE_RETURN,
                    is_credit=True,
                    summary=f"采购退货 {r.return_code}",
                    extra=extra,
                )
            )

        outsource_lines = await self.list_outsource_supplier_unposted_lines(
            tenant_id, supplier_id, start_date, end_date
        )
        seen: Set[Tuple[Any, Any]] = {
            (ln.get("doc_type"), ln.get("doc_id"))
            for ln in lines
            if ln.get("doc_id") is not None
        }
        for ln in outsource_lines:
            key = (ln.get("doc_type"), ln.get("doc_id"))
            if ln.get("doc_id") is not None and key in seen:
                continue
            # 委外列表已 pop sort_date，合并前用 date 字符串回填，避免与入库行 date/str 混排
            if ln.get("sort_date") is None and ln.get("date") is not None:
                ln["sort_date"] = _coerce_sort_date(ln.get("date"))
            lines.append(ln)
            if ln.get("doc_id") is not None:
                seen.add(key)
        lines.sort(key=_line_sort_key)
        for ln in lines:
            ln.pop("sort_date", None)
        return lines

    async def list_outsource_supplier_unposted_lines(
        self,
        tenant_id: int,
        supplier_id: int,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        from apps.kuaizhizao.models.outsource_order import OutsourceOrder
        from apps.kuaizhizao.models.outsource_order_receipt import OutsourceOrderReceipt
        from apps.kuaizhizao.models.outsource_work_order import OutsourceMaterialReceipt

        lines: List[Dict[str, Any]] = []
        batch_rows = await OutsourceOrderReceipt.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            ledger_posted=False,
        ).order_by("created_at", "id").all()
        if batch_rows:
            order_ids = {int(b.outsource_order_id) for b in batch_rows}
            orders = await OutsourceOrder.filter(
                tenant_id=tenant_id,
                id__in=list(order_ids),
                supplier_id=supplier_id,
                deleted_at__isnull=True,
            ).all()
            order_by_id = {int(o.id): o for o in orders}
            for b in batch_rows:
                oo = order_by_id.get(int(b.outsource_order_id))
                if not oo:
                    continue
                if payable_recognition_from_doc(b) != "on_partner_statement" and payable_recognition_from_doc(
                    oo
                ) != "on_partner_statement":
                    continue
                biz = _business_date_from_row(b.created_at)
                if not _in_date_range(biz, start_date, end_date):
                    continue
                unit_price = _q_money(oo.unit_price or 0)
                qual = _q_money(b.qualified_quantity or 0)
                amt = (unit_price * qual).quantize(_MONEY)
                if amt <= 0:
                    continue
                lines.append(
                    _settlement_line(
                        biz_date=biz,
                        doc_type="工序委外收货",
                        doc_code=f"{oo.code}-{b.id}",
                        doc_id=int(b.id),
                        amount=amt,
                        finance_source_type=PAYABLE_SOURCE_OUTSOURCE_ORDER_RECEIPT,
                        is_credit=False,
                        summary=f"工序委外 {oo.code} 第{b.id}批",
                        extra={
                            "inbound_detail_doc_type": "outsource_order_receipt",
                            "inbound_detail_doc_id": int(b.id),
                        },
                    )
                )

        # OutsourceMaterialReceipt 无 review_status；门禁用 status=completed（见下方归一）
        receipts = await OutsourceMaterialReceipt.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            status__in=["completed", "draft"],
        ).order_by("received_at", "id").all()
        if receipts:
            from apps.kuaizhizao.models.outsource_work_order import OutsourceWorkOrder
            from apps.kuaizhizao.services.outsource_material_receipt_service import (
                OutsourceMaterialReceiptService,
            )

            await OutsourceMaterialReceiptService()._normalize_legacy_draft_receipts(receipts)
            receipts = [r for r in receipts if str(r.status or "").strip() == "completed"]

            owo_ids = {int(r.outsource_work_order_id) for r in receipts}
            orders = await OutsourceWorkOrder.filter(
                tenant_id=tenant_id,
                id__in=list(owo_ids),
                supplier_id=supplier_id,
                deleted_at__isnull=True,
            ).all()
            owo_by_id = {int(o.id): o for o in orders}
            statement_receipts: List[Any] = []
            for r in receipts:
                wo = owo_by_id.get(int(r.outsource_work_order_id))
                if not wo:
                    continue
                if payable_recognition_from_doc(r) != "on_partner_statement" and payable_recognition_from_doc(
                    wo
                ) != "on_partner_statement":
                    continue
                statement_receipts.append(r)
            receipt_ids = [int(r.id) for r in statement_receipts]
            posted = await _posted_payable_source_ids(
                tenant_id, PAYABLE_SOURCE_OUTSOURCE_RECEIPT, receipt_ids
            )
            for r in statement_receipts:
                if int(r.id) in posted:
                    continue
                biz = _business_date_from_row(r.received_at) or _business_date_from_row(r.created_at)
                if not _in_date_range(biz, start_date, end_date):
                    continue
                amt = _q_money(r.total_amount or 0)
                if amt <= 0:
                    continue
                lines.append(
                    _settlement_line(
                        biz_date=biz,
                        doc_type="委外收货",
                        doc_code=r.code,
                        doc_id=int(r.id),
                        amount=amt,
                        finance_source_type=PAYABLE_SOURCE_OUTSOURCE_RECEIPT,
                        is_credit=False,
                        summary=f"委外收货 {r.code}",
                        extra={
                            "inbound_detail_doc_type": "outsource_material_receipt",
                            "inbound_detail_doc_id": int(r.id),
                        },
                    )
                )

        lines.sort(key=_line_sort_key)
        for ln in lines:
            ln.pop("sort_date", None)
        return lines

    async def sum_customer_unposted_debits_before(
        self,
        tenant_id: int,
        customer_id: int,
        before_date: date,
        *,
        require_statement_strategy: bool = True,
    ) -> Decimal:
        start = date(1970, 1, 1)
        end = before_date.fromordinal(before_date.toordinal() - 1) if before_date.toordinal() > 1 else before_date
        if end < start:
            return Decimal("0")
        lines = await self.list_customer_unposted_lines(
            tenant_id,
            customer_id,
            start,
            end,
            require_statement_strategy=require_statement_strategy,
        )
        total = Decimal("0")
        for ln in lines:
            total += _q_money(ln.get("debit", 0)) - _q_money(ln.get("credit", 0))
        return _q_money(total)

    async def sum_supplier_unposted_debits_before(
        self,
        tenant_id: int,
        supplier_id: int,
        before_date: date,
        *,
        tax_inclusive: bool = True,
    ) -> Decimal:
        start = date(1970, 1, 1)
        end = before_date.fromordinal(before_date.toordinal() - 1) if before_date.toordinal() > 1 else before_date
        if end < start:
            return Decimal("0")
        lines = await self.list_supplier_unposted_lines(
            tenant_id, supplier_id, start, end, tax_inclusive=tax_inclusive
        )
        total = Decimal("0")
        for ln in lines:
            total += _q_money(ln.get("debit", 0)) - _q_money(ln.get("credit", 0))
        return _q_money(total)
