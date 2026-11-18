"""应付/应收「付款条件」展示文案：从采购订单或供应商账期解析。"""

from __future__ import annotations

from typing import Optional

from apps.kuaicaiwu.constants.finance_source_types import (
    PAYABLE_SOURCE_ORDER_MILESTONE,
    PAYABLE_SOURCE_PURCHASE_RECEIPT,
)
from apps.master_data.config.partner_settlement_codes import coerce_partner_settlement_terms_code
from apps.master_data.models.supplier import Supplier

_SETTLEMENT_TERMS_CN = {
    "prepaid": "预付款",
    "pay_before_ship": "款到发货",
    "spot": "现款现货",
    "cod": "货到付款",
    "net_terms": "账期结算",
    "installment": "分期付款",
    "progress": "进度款",
    "monthly": "月结",
    "bimonthly": "双月结",
    "quarterly": "季结",
}

_PURCHASE_RECEIPT_SOURCE_TYPES = frozenset(
    {
        "purchase_receipt",
        "PurchaseReceipt",
        PAYABLE_SOURCE_PURCHASE_RECEIPT,
    }
)


def _format_payment_terms_text(
    settlement_terms_code: Optional[str],
    payment_terms_days: Optional[int],
) -> Optional[str]:
    parts: list[str] = []
    if settlement_terms_code:
        code = coerce_partner_settlement_terms_code(settlement_terms_code)
        label = _SETTLEMENT_TERMS_CN.get(str(code or "").strip())
        if label:
            parts.append(label)
    if payment_terms_days is not None:
        days = int(payment_terms_days)
        if days >= 0:
            parts.append(f"{days}天")
    if not parts:
        return None
    return " ".join(parts)


async def resolve_supplier_payable_payment_terms(
    tenant_id: int,
    *,
    supplier_id: int,
    purchase_order_id: Optional[int] = None,
) -> Optional[str]:
    """解析供应商侧付款条件（结算方式 + 账期天数），供应付单落库与列表展示。"""
    settlement_code: Optional[str] = None
    terms_days: Optional[int] = None

    if purchase_order_id:
        from apps.kuaizhizao.models.purchase_order import PurchaseOrder

        order = await PurchaseOrder.get_or_none(
            tenant_id=tenant_id,
            id=int(purchase_order_id),
            deleted_at__isnull=True,
        )
        if order:
            settlement_code = getattr(order, "settlement_terms_code", None)
            terms_days = getattr(order, "payment_terms_days", None)

    supplier = await Supplier.get_or_none(
        tenant_id=tenant_id, id=int(supplier_id), deleted_at__isnull=True
    )
    if supplier:
        if settlement_code is None:
            settlement_code = getattr(supplier, "settlement_terms_code", None)
        if terms_days is None:
            raw_days = getattr(supplier, "payment_terms_days", None)
            if raw_days is not None:
                terms_days = int(raw_days)

    return _format_payment_terms_text(settlement_code, terms_days)


async def resolve_payable_payment_terms_for_source(
    tenant_id: int,
    *,
    supplier_id: int,
    source_type: Optional[str],
    source_id: Optional[int],
) -> Optional[str]:
    """按应付来源解析付款条件（采购入库、订单里程碑等）。"""
    st = str(source_type or "").strip()
    sid = int(source_id or 0)
    po_id: Optional[int] = None

    if st in _PURCHASE_RECEIPT_SOURCE_TYPES and sid > 0:
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        receipt = await PurchaseReceipt.get_or_none(
            tenant_id=tenant_id, id=sid, deleted_at__isnull=True
        )
        if receipt and receipt.purchase_order_id:
            po_id = int(receipt.purchase_order_id)
    elif st == PAYABLE_SOURCE_ORDER_MILESTONE and sid > 0:
        from apps.kuaizhizao.models.purchase_order_milestone import PurchaseOrderMilestone

        milestone = await PurchaseOrderMilestone.get_or_none(
            tenant_id=tenant_id, id=sid, deleted_at__isnull=True
        )
        if milestone and milestone.purchase_order_id:
            po_id = int(milestone.purchase_order_id)

    return await resolve_supplier_payable_payment_terms(
        tenant_id,
        supplier_id=int(supplier_id),
        purchase_order_id=po_id,
    )


async def enrich_payable_payment_terms_fields(tenant_id: int, payables) -> None:
    """列表/详情展示：库内未写 payment_terms 时从来源订单或供应商解析（不落库）。"""
    for row in payables or []:
        if str(getattr(row, "payment_terms", "") or "").strip():
            continue
        supplier_id = getattr(row, "supplier_id", None)
        if not supplier_id:
            continue
        text = await resolve_payable_payment_terms_for_source(
            tenant_id,
            supplier_id=int(supplier_id),
            source_type=getattr(row, "source_type", None),
            source_id=getattr(row, "source_id", None),
        )
        if text:
            row.payment_terms = text
