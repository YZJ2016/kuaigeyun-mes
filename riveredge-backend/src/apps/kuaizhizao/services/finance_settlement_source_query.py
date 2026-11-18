"""
只读：按对账单立账策略下，尚未生成应收/应付的业务源单查询。
供 kuaicaiwu 往来对账单预览与期初调节使用，禁止在此模块写入 kuaizhizao 表。
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

_EXCLUDED_REVIEW = ("待审核", "驳回", "已驳回", "rejected", "审核驳回", "草稿", "PENDING", "DRAFT")
_MONEY = Decimal("0.01")


def _q_money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value or 0)).quantize(_MONEY)


def _business_date_from_row(dt: Optional[datetime]) -> Optional[date]:
    if dt is None:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt
    return dt.date()


def _in_date_range(biz: Optional[date], start: date, end: date) -> bool:
    if biz is None:
        return False
    return start <= biz <= end


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
    ) -> List[Dict[str, Any]]:
        lines: List[Dict[str, Any]] = []

        deliveries = await SalesDelivery.filter(
            tenant_id=tenant_id,
            customer_id=customer_id,
            status="已出库",
            deleted_at__isnull=True,
        ).exclude(review_status__in=_EXCLUDED_REVIEW).order_by("delivery_time", "id").all()

        delivery_ids = [int(d.id) for d in deliveries]
        posted_del = await _posted_receivable_source_ids(
            tenant_id, RECEIVABLE_SOURCE_SALES_DELIVERY, delivery_ids
        )
        for d in deliveries:
            biz = _business_date_from_row(d.delivery_time) or _business_date_from_row(d.review_time)
            if not _in_date_range(biz, start_date, end_date):
                continue
            if int(d.id) in posted_del:
                continue
            amt = _q_money(d.total_amount)
            if amt <= 0:
                continue
            lines.append(
                _settlement_line(
                    biz_date=biz,
                    doc_type="销售出库",
                    doc_code=d.delivery_code,
                    doc_id=int(d.id),
                    amount=amt,
                    finance_source_type=RECEIVABLE_SOURCE_SALES_DELIVERY,
                    is_credit=False,
                    summary=f"销售出库 {d.delivery_code}",
                )
            )

        returns = await SalesReturn.filter(
            tenant_id=tenant_id,
            customer_id=customer_id,
            deleted_at__isnull=True,
        ).exclude(review_status__in=_EXCLUDED_REVIEW).order_by("return_time", "id").all()

        return_ids = [int(r.id) for r in returns]
        posted_ret = await _posted_receivable_source_ids(
            tenant_id, RECEIVABLE_SOURCE_SALES_RETURN, return_ids
        )
        for r in returns:
            biz = _business_date_from_row(r.return_time) or _business_date_from_row(r.review_time)
            if not _in_date_range(biz, start_date, end_date):
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

        lines.sort(key=lambda x: (x["sort_date"], x["doc_type"], x.get("doc_id", 0)))
        for ln in lines:
            ln.pop("sort_date", None)
        return lines

    async def list_supplier_unposted_lines(
        self,
        tenant_id: int,
        supplier_id: int,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        lines: List[Dict[str, Any]] = []

        receipts = await PurchaseReceipt.filter(
            tenant_id=tenant_id,
            supplier_id=supplier_id,
            status="已入库",
            deleted_at__isnull=True,
        ).exclude(review_status__in=_EXCLUDED_REVIEW).order_by("receipt_time", "id").all()

        receipt_ids = [int(p.id) for p in receipts]
        posted_rc = await _posted_payable_source_ids(
            tenant_id, PAYABLE_SOURCE_PURCHASE_RECEIPT, receipt_ids
        )
        for p in receipts:
            biz = _business_date_from_row(p.receipt_time) or _business_date_from_row(p.review_time)
            if not _in_date_range(biz, start_date, end_date):
                continue
            if int(p.id) in posted_rc:
                continue
            amt = _q_money(p.total_amount)
            if amt <= 0:
                continue
            lines.append(
                _settlement_line(
                    biz_date=biz,
                    doc_type="采购入库",
                    doc_code=p.receipt_code,
                    doc_id=int(p.id),
                    amount=amt,
                    finance_source_type=PAYABLE_SOURCE_PURCHASE_RECEIPT,
                    is_credit=False,
                    summary=f"采购入库 {p.receipt_code}",
                    extra={
                        "inbound_detail_doc_type": "purchase_receipt",
                        "inbound_detail_doc_id": int(p.id),
                    },
                )
            )

        returns = await PurchaseReturn.filter(
            tenant_id=tenant_id,
            supplier_id=supplier_id,
            deleted_at__isnull=True,
        ).exclude(review_status__in=_EXCLUDED_REVIEW).order_by("return_time", "id").all()

        return_ids = [int(r.id) for r in returns]
        posted_ret = await _posted_payable_source_ids(
            tenant_id, PAYABLE_SOURCE_PURCHASE_RETURN, return_ids
        )
        for r in returns:
            biz = _business_date_from_row(r.return_time) or _business_date_from_row(r.review_time)
            if not _in_date_range(biz, start_date, end_date):
                continue
            if int(r.id) in posted_ret:
                continue
            amt = _q_money(r.total_amount)
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

        lines.sort(key=lambda x: (x["sort_date"], x["doc_type"], x.get("doc_id", 0)))
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
                payable_recognition="on_partner_statement",
            ).all()
            order_by_id = {int(o.id): o for o in orders}
            for b in batch_rows:
                oo = order_by_id.get(int(b.outsource_order_id))
                if not oo:
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

        receipts = await OutsourceMaterialReceipt.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            status="completed",
        ).order_by("received_at", "id").all()
        if receipts:
            from apps.kuaizhizao.models.outsource_work_order import OutsourceWorkOrder

            owo_ids = {int(r.outsource_work_order_id) for r in receipts}
            orders = await OutsourceWorkOrder.filter(
                tenant_id=tenant_id,
                id__in=list(owo_ids),
                supplier_id=supplier_id,
                deleted_at__isnull=True,
                payable_recognition="on_partner_statement",
            ).all()
            owo_by_id = {int(o.id): o for o in orders}
            receipt_ids = [int(r.id) for r in receipts if int(r.outsource_work_order_id) in owo_by_id]
            posted = await _posted_payable_source_ids(
                tenant_id, PAYABLE_SOURCE_OUTSOURCE_RECEIPT, receipt_ids
            )
            for r in receipts:
                if int(r.outsource_work_order_id) not in owo_by_id:
                    continue
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

        lines.sort(key=lambda x: (x["sort_date"], x["doc_type"], x.get("doc_id", 0)))
        for ln in lines:
            ln.pop("sort_date", None)
        return lines

    async def sum_customer_unposted_debits_before(
        self, tenant_id: int, customer_id: int, before_date: date
    ) -> Decimal:
        start = date(1970, 1, 1)
        end = before_date.fromordinal(before_date.toordinal() - 1) if before_date.toordinal() > 1 else before_date
        if end < start:
            return Decimal("0")
        lines = await self.list_customer_unposted_lines(tenant_id, customer_id, start, end)
        total = Decimal("0")
        for ln in lines:
            total += _q_money(ln.get("debit", 0)) - _q_money(ln.get("credit", 0))
        return _q_money(total)

    async def sum_supplier_unposted_debits_before(
        self, tenant_id: int, supplier_id: int, before_date: date
    ) -> Decimal:
        start = date(1970, 1, 1)
        end = before_date.fromordinal(before_date.toordinal() - 1) if before_date.toordinal() > 1 else before_date
        if end < start:
            return Decimal("0")
        lines = await self.list_supplier_unposted_lines(tenant_id, supplier_id, start, end)
        total = Decimal("0")
        for ln in lines:
            total += _q_money(ln.get("debit", 0)) - _q_money(ln.get("credit", 0))
        return _q_money(total)
