"""采购订单 → 付款申请表头：发票情况、税率、付款方式。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from apps.kuaizhizao.constants.price_type import DEFAULT_PURCHASE_PRICE_TYPE
from apps.kuaicaiwu.constants.payment_method import (
    BANK_ACCEPTANCE_PAYMENT_METHOD,
    BANK_TRANSFER_PAYMENT_METHOD,
    CASH_PAYMENT_METHOD,
    NOTE_PAYMENT_METHOD,
)
from apps.kuaicaiwu.services.finance_payment_method import (
    payment_method_fields_from_source,
)
from apps.kuaicaiwu.services.purchase_settlement import (
    normalize_po_tax_rate_to_percent,
    resolve_purchase_line_tax_rate_percent,
)
from apps.kuaizhizao.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from apps.kuaizhizao.services.payment_application_service import (
    PAYMENT_APPLICATION_INVOICE_STATUSES,
)
from apps.master_data.config.payment_method_mix import (
    PARTNER_MIXED_PAYMENT_METHOD,
    format_payment_method_mix_label_zh,
)

_PARTNER_PAYMENT_METHOD_ZH = {
    "cash": CASH_PAYMENT_METHOD,
    "bank_transfer": BANK_TRANSFER_PAYMENT_METHOD,
    "bank_acceptance": BANK_ACCEPTANCE_PAYMENT_METHOD,
    "commercial_acceptance": NOTE_PAYMENT_METHOD,
    "other": "其他",
}


def payment_method_label_from_purchase_order(order: Any) -> Optional[str]:
    code, wire, acceptance, _ = payment_method_fields_from_source(order)
    if not code:
        return None
    if code == PARTNER_MIXED_PAYMENT_METHOD:
        mix = format_payment_method_mix_label_zh(wire, acceptance)
        return mix or _PARTNER_PAYMENT_METHOD_ZH.get("bank_transfer")
    return _PARTNER_PAYMENT_METHOD_ZH.get(code, code)


async def resolve_tax_rate_percent_from_purchase_order(
    tenant_id: int,
    order: PurchaseOrder,
) -> Decimal:
    """订单行税率优先；多行取首行非零；否则头表税率。"""
    items = (
        await PurchaseOrderItem.filter(tenant_id=tenant_id, order_id=int(order.id))
        .order_by("id")
        .all()
    )
    for it in items:
        pct = resolve_purchase_line_tax_rate_percent(
            line_tax_rate=getattr(it, "tax_rate", None),
            header_tax_rate=getattr(order, "tax_rate", None),
        )
        if pct > 0:
            return pct
    return normalize_po_tax_rate_to_percent(getattr(order, "tax_rate", None))


async def _purchase_order_has_approved_invoice(tenant_id: int, order_id: int) -> bool:
    from apps.kuaicaiwu.models.purchase_invoice import PurchaseInvoice
    approved = ("已审核", "APPROVED", "审核通过")
    inv = (
        await PurchaseInvoice.filter(
            tenant_id=tenant_id,
            purchase_order_id=order_id,
            deleted_at__isnull=True,
            review_status__in=approved,
        )
        .first()
    )
    return inv is not None


async def resolve_invoice_status_from_purchase_order(
    tenant_id: int,
    order: PurchaseOrder,
    *,
    application_kind: str = "prepayment",
) -> str:
    """按采购订单价类/税率/进项票状态推导付款申请发票情况。"""
    custom = str(getattr(order, "invoice_status", None) or "").strip()
    if custom in PAYMENT_APPLICATION_INVOICE_STATUSES:
        return custom

    if await _purchase_order_has_approved_invoice(tenant_id, int(order.id)):
        return "有发票"

    tax_pct = normalize_po_tax_rate_to_percent(getattr(order, "tax_rate", None))
    price_type = str(getattr(order, "price_type", None) or DEFAULT_PURCHASE_PRICE_TYPE).strip()

    if tax_pct <= 0 or price_type == "tax_exclusive":
        return "无发票"

    if str(application_kind or "").strip() == "prepayment":
        return "发票后补"

    return "有发票"


async def payment_application_header_from_purchase_order(
    tenant_id: int,
    order: PurchaseOrder,
    *,
    application_kind: str = "prepayment",
) -> Dict[str, Any]:
    invoice_status = await resolve_invoice_status_from_purchase_order(
        tenant_id, order, application_kind=application_kind
    )
    payment_method = payment_method_label_from_purchase_order(order)
    payload: Dict[str, Any] = {
        "invoice_status": invoice_status,
    }
    if payment_method:
        payload["payment_method"] = payment_method
    return payload