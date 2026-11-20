"""采购订单账款发票生命周期：开票/付款进度与追溯关联（真源：发票、应付、DocumentRelation）。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Set

from apps.common.app_orm import finance_orm_ready

_EXCLUDED_INVOICE_STATUSES = frozenset({"已作废", "已红冲"})
_RECEIPT_PAYABLE_SOURCE_TYPES = frozenset(
    {
        "采购入库",
        "purchase_receipt",
        "PurchaseReceipt",
    }
)


@dataclass(frozen=True)
class PurchaseOrderFinanceLifecycleSnapshot:
    has_purchase_invoice: bool
    invoice_amount_progress: float
    payment_progress: float
    effective_paid_total: Decimal = Decimal("0")
    obligation_total: Decimal = Decimal("0")
    payment_settlement: Optional[str] = None


_MONEY_EPSILON = Decimal("0.01")


def resolve_purchase_order_payment_settlement(
    paid: Decimal,
    obligation: Decimal,
) -> Optional[str]:
    """付款状态：未付款 unpaid / 部分付款 partial / 已付款 paid（相对订单结算总额）。"""
    paid = paid.quantize(_money_scale())
    obligation = obligation.quantize(_money_scale())
    if obligation <= _MONEY_EPSILON:
        if paid <= _MONEY_EPSILON:
            return None
        return "paid"
    if paid <= _MONEY_EPSILON:
        return "unpaid"
    if paid + _MONEY_EPSILON >= obligation:
        return "paid"
    return "partial"


def purchase_order_shows_payment_settlement(order: object) -> bool:
    """审核通过后才展示付款状态（与付款申请列表一致）。"""
    from apps.kuaizhizao.services.document_lifecycle_service import _is_approved

    return _is_approved(getattr(order, "review_status", None))


async def _sum_prepayment_unsettled_for_order(tenant_id: int, order_id: int) -> Decimal:
    """采购订单关联已确认预付付款单的待核销余额（未核销=已付现金尚未冲应付）。"""
    from apps.kuaicaiwu.models.payment import Payment
    from apps.kuaizhizao.models.document_relation import DocumentRelation

    payment_ids = await DocumentRelation.filter(
        tenant_id=tenant_id,
        source_type="purchase_order",
        source_id=int(order_id),
        target_type="payment",
    ).values_list("target_id", flat=True)
    ids = [int(x) for x in payment_ids if x]
    if not ids:
        return Decimal("0")
    rows = await Payment.filter(
        tenant_id=tenant_id,
        id__in=ids,
        settlement_type="prepayment",
        status="Confirmed",
        deleted_at__isnull=True,
    ).values_list("unsettled_amount", flat=True)
    total = sum((Decimal(str(x or 0)) for x in rows), Decimal("0"))
    return max(Decimal("0"), total.quantize(_money_scale()))


async def batch_sum_prepayment_unsettled_by_order_ids(
    tenant_id: int,
    order_ids: List[int],
) -> Dict[int, Decimal]:
    """批量：订单 → 预付付款单待核销合计。"""
    from apps.kuaicaiwu.models.payment import Payment
    from apps.kuaizhizao.models.document_relation import DocumentRelation

    if not order_ids:
        return {}
    result: Dict[int, Decimal] = {int(oid): Decimal("0") for oid in order_ids}
    rel_rows = await DocumentRelation.filter(
        tenant_id=tenant_id,
        source_type="purchase_order",
        source_id__in=[int(x) for x in order_ids],
        target_type="payment",
    ).values_list("source_id", "target_id")
    if not rel_rows:
        return result
    payment_ids = sorted({int(tid) for _, tid in rel_rows if tid})
    unsettled_by_payment: Dict[int, Decimal] = {}
    if payment_ids:
        pay_rows = await Payment.filter(
            tenant_id=tenant_id,
            id__in=payment_ids,
            settlement_type="prepayment",
            status="Confirmed",
            deleted_at__isnull=True,
        ).values_list("id", "unsettled_amount")
        for pid, unsettled in pay_rows:
            unsettled_by_payment[int(pid)] = Decimal(str(unsettled or 0))
    for source_id, target_id in rel_rows:
        oid = int(source_id or 0)
        pid = int(target_id or 0)
        if oid not in result or pid not in unsettled_by_payment:
            continue
        result[oid] += unsettled_by_payment[pid]
    scale = _money_scale()
    return {oid: max(Decimal("0"), amt.quantize(scale)) for oid, amt in result.items()}


async def batch_purchase_order_payment_settlement(
    tenant_id: int,
    orders: Sequence[object],
) -> Dict[int, Optional[str]]:
    """列表批量解析付款状态（含预付付款单，未入库也可展示）。"""
    if not finance_orm_ready():
        return {}
    from apps.kuaicaiwu.services.purchase_settlement import (
        purchase_order_settlement_gross,
    )

    eligible = [o for o in orders if purchase_order_shows_payment_settlement(o)]
    if not eligible:
        return {}
    order_ids = [int(o.id) for o in eligible]
    prepay_unsettled_map = await batch_sum_prepayment_unsettled_by_order_ids(
        tenant_id, order_ids
    )
    settlements: Dict[int, Optional[str]] = {}
    for order in eligible:
        oid = int(order.id)
        gross = purchase_order_settlement_gross(order)
        snap = await compute_purchase_order_finance_lifecycle(
            tenant_id,
            oid,
            gross,
            prepayment_unsettled=prepay_unsettled_map.get(oid),
        )
        if not purchase_order_shows_payment_settlement(order):
            settlements[oid] = None
        else:
            settlements[oid] = snap.payment_settlement
    return settlements


def _money_scale() -> Decimal:
    return Decimal("0.01")


async def purchase_order_has_linked_purchase_receipt(tenant_id: int, order_id: int) -> bool:
    """采购订单是否已有入库（表头 purchase_order_id 或 PO→入库 单据关联）。"""
    from apps.kuaizhizao.models.document_relation import DocumentRelation
    from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

    if await PurchaseReceipt.filter(
        tenant_id=tenant_id,
        purchase_order_id=int(order_id),
        deleted_at__isnull=True,
    ).exists():
        return True
    return await DocumentRelation.filter(
        tenant_id=tenant_id,
        source_type="purchase_order",
        source_id=int(order_id),
        target_type="purchase_receipt",
    ).exists()


async def _receipt_ids_for_purchase_order(tenant_id: int, order_id: int) -> Set[int]:
    from apps.kuaizhizao.models.document_relation import DocumentRelation
    from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

    ids: Set[int] = set()
    rows = await PurchaseReceipt.filter(
        tenant_id=tenant_id,
        purchase_order_id=int(order_id),
        deleted_at__isnull=True,
    ).values_list("id", flat=True)
    ids.update(int(x) for x in rows)
    rel_rows = await DocumentRelation.filter(
        tenant_id=tenant_id,
        source_type="purchase_order",
        source_id=int(order_id),
        target_type="purchase_receipt",
    ).values_list("target_id", flat=True)
    ids.update(int(x) for x in rel_rows if x)
    return ids


async def _invoice_ids_for_purchase_order(tenant_id: int, order_id: int) -> Set[int]:
    from apps.kuaicaiwu.models.purchase_invoice import PurchaseInvoice
    from apps.kuaizhizao.models.document_relation import DocumentRelation

    ids: Set[int] = set()
    rows = await PurchaseInvoice.filter(
        tenant_id=tenant_id,
        purchase_order_id=int(order_id),
        deleted_at__isnull=True,
    ).exclude(status__in=list(_EXCLUDED_INVOICE_STATUSES)).values_list("id", flat=True)
    ids.update(int(x) for x in rows)

    rel_rows = await DocumentRelation.filter(
        tenant_id=tenant_id,
        source_type="purchase_order",
        source_id=int(order_id),
        target_type="purchase_invoice",
    ).values_list("target_id", flat=True)
    if rel_rows:
        valid = await PurchaseInvoice.filter(
            tenant_id=tenant_id,
            id__in=list(rel_rows),
            deleted_at__isnull=True,
        ).exclude(status__in=list(_EXCLUDED_INVOICE_STATUSES)).values_list("id", flat=True)
        ids.update(int(x) for x in valid)
    return ids


async def compute_purchase_order_finance_lifecycle(
    tenant_id: int,
    order_id: int,
    order_gross: Decimal,
    *,
    prepayment_unsettled: Optional[Decimal] = None,
) -> PurchaseOrderFinanceLifecycleSnapshot:
    scale = _money_scale()
    if not finance_orm_ready():
        return PurchaseOrderFinanceLifecycleSnapshot(
            has_purchase_invoice=False,
            invoice_amount_progress=0.0,
            payment_progress=0.0,
            obligation_total=Decimal("0"),
        )

    from apps.kuaicaiwu.models.purchase_invoice import PurchaseInvoice
    from apps.kuaicaiwu.models.payable import Payable

    invoice_ids = await _invoice_ids_for_purchase_order(tenant_id, order_id)
    invoiced_total = Decimal("0")
    if invoice_ids:
        inv_rows = await PurchaseInvoice.filter(
            tenant_id=tenant_id,
            id__in=list(invoice_ids),
            deleted_at__isnull=True,
        ).exclude(status__in=list(_EXCLUDED_INVOICE_STATUSES))
        from apps.kuaicaiwu.services.purchase_invoice_amounts import (
            purchase_invoice_occupancy_amount,
        )

        invoiced_total = sum(
            (purchase_invoice_occupancy_amount(inv) for inv in inv_rows), Decimal("0")
        )

    order_gross = order_gross.quantize(scale)
    if order_gross <= 0:
        unsettled = prepayment_unsettled
        if unsettled is None:
            unsettled = await _sum_prepayment_unsettled_for_order(tenant_id, order_id)
        effective_paid = unsettled.quantize(scale)
        return PurchaseOrderFinanceLifecycleSnapshot(
            has_purchase_invoice=False,
            invoice_amount_progress=0.0,
            payment_progress=0.0,
            effective_paid_total=effective_paid,
            obligation_total=order_gross,
            payment_settlement=resolve_purchase_order_payment_settlement(
                effective_paid, order_gross
            ),
        )
    invoiced_total = invoiced_total.quantize(scale)

    invoice_amount_progress = float(
        min(Decimal("100"), (invoiced_total / order_gross) * Decimal("100"))
    )
    has_purchase_invoice = invoiced_total > 0 or bool(invoice_ids)

    receipt_ids = await _receipt_ids_for_purchase_order(tenant_id, order_id)
    payable_total = Decimal("0")
    paid_total = Decimal("0")
    if receipt_ids:
        payables = await Payable.filter(
            tenant_id=tenant_id,
            source_id__in=list(receipt_ids),
            deleted_at__isnull=True,
        ).values_list("source_type", "total_amount", "paid_amount")
        for source_type, total_amount, paid_amount in payables:
            if str(source_type or "").strip() not in _RECEIPT_PAYABLE_SOURCE_TYPES:
                continue
            payable_total += Decimal(str(total_amount or 0))
            paid_total += Decimal(str(paid_amount or 0))

    if payable_total <= 0 and invoice_ids:
        inv_payables = await Payable.filter(
            tenant_id=tenant_id,
            source_type__in=("PurchaseInvoice", "purchase_invoice"),
            source_id__in=list(invoice_ids),
            deleted_at__isnull=True,
        ).values_list("total_amount", "paid_amount")
        for total_amount, paid_amount in inv_payables:
            payable_total += Decimal(str(total_amount or 0))
            paid_total += Decimal(str(paid_amount or 0))

    payable_total = payable_total.quantize(scale)
    paid_total = paid_total.quantize(scale)
    if prepayment_unsettled is None:
        prepayment_unsettled = await _sum_prepayment_unsettled_for_order(tenant_id, order_id)
    prepayment_unsettled = prepayment_unsettled.quantize(scale)
    effective_paid = (paid_total + prepayment_unsettled).quantize(scale)
    if order_gross > 0:
        payment_progress = float(
            min(Decimal("100"), (effective_paid / order_gross) * Decimal("100"))
        )
    elif effective_paid > 0:
        payment_progress = 100.0
    else:
        payment_progress = 0.0

    return PurchaseOrderFinanceLifecycleSnapshot(
        has_purchase_invoice=has_purchase_invoice,
        invoice_amount_progress=round(invoice_amount_progress, 1),
        payment_progress=round(payment_progress, 1),
        effective_paid_total=effective_paid,
        obligation_total=order_gross,
        payment_settlement=resolve_purchase_order_payment_settlement(
            effective_paid, order_gross
        ),
    )


async def link_purchase_invoice_to_order_receipt_payables(
    tenant_id: int,
    *,
    purchase_order_id: int,
    invoice_id: int,
    invoice_code: str,
    created_by: int,
) -> None:
    """从采购订单开进项发票后，关联同订单入库应付，全链路 PI→PY→PK 可串联。"""
    from apps.kuaicaiwu.models.payable import Payable
    from apps.kuaicaiwu.services.finance_integration_hooks import link_finance_document_relation
    receipt_ids = await _receipt_ids_for_purchase_order(tenant_id, int(purchase_order_id))
    if not receipt_ids:
        return

    payables = await Payable.filter(
        tenant_id=tenant_id,
        source_id__in=list(receipt_ids),
        deleted_at__isnull=True,
    ).all()
    from apps.kuaizhizao.models.document_relation import DocumentRelation

    for payable in payables:
        if str(getattr(payable, "source_type", "") or "").strip() not in _RECEIPT_PAYABLE_SOURCE_TYPES:
            continue
        exists = await DocumentRelation.get_or_none(
            tenant_id=tenant_id,
            source_type="purchase_invoice",
            source_id=int(invoice_id),
            target_type="payable",
            target_id=int(payable.id),
        )
        if exists:
            continue
        await link_finance_document_relation(
            tenant_id=tenant_id,
            source_type="purchase_invoice",
            source_id=int(invoice_id),
            source_code=invoice_code,
            target_type="payable",
            target_id=int(payable.id),
            target_code=str(payable.payable_code or payable.id),
            relation_desc="采购订单进项发票关联入库应付",
            created_by=created_by,
        )


async def backfill_purchase_invoice_payable_links_for_order(
    tenant_id: int,
    order_id: int,
    *,
    created_by: int = 0,
) -> int:
    """补写已有进项发票→入库应付关联（幂等，供迁移或运维调用）。"""
    from apps.kuaicaiwu.models.purchase_invoice import PurchaseInvoice

    invoice_ids = await _invoice_ids_for_purchase_order(tenant_id, int(order_id))
    if not invoice_ids:
        return 0
    rows = await PurchaseInvoice.filter(
        tenant_id=tenant_id,
        id__in=list(invoice_ids),
        deleted_at__isnull=True,
    ).values_list("id", "invoice_code")
    linked = 0
    for iid, code in rows:
        await link_purchase_invoice_to_order_receipt_payables(
            tenant_id,
            purchase_order_id=int(order_id),
            invoice_id=int(iid),
            invoice_code=str(code or iid),
            created_by=created_by,
        )
        linked += 1
    return linked
