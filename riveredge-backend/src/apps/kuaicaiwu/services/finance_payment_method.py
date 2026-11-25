"""应收/应付付款方式字段：从来源单据或伙伴主数据解析。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional, Tuple

from apps.master_data.config.payment_method_mix import (
    PARTNER_MIXED_PAYMENT_METHOD,
    format_payment_method_mix_label_zh,
)


def payment_method_fields_from_source(
    source: Any,
) -> Tuple[Optional[str], Optional[Decimal], Optional[Decimal], Optional[str]]:
    """从来源对象读取 payment_method_code 与比例，并生成 mix 展示摘要。"""
    code = getattr(source, "payment_method_code", None)
    wire = getattr(source, "payment_wire_percent", None)
    acceptance = getattr(source, "payment_acceptance_percent", None)
    summary = None
    if str(code or "").strip() == PARTNER_MIXED_PAYMENT_METHOD:
        summary = format_payment_method_mix_label_zh(wire, acceptance)
    return (
        str(code).strip() if code else None,
        Decimal(str(wire)) if wire is not None else None,
        Decimal(str(acceptance)) if acceptance is not None else None,
        summary,
    )


def payment_method_fields_from_customer(customer: Any) -> Tuple[Optional[str], Optional[Decimal], Optional[Decimal]]:
    code = getattr(customer, "default_payment_method_code", None)
    wire = getattr(customer, "default_payment_wire_percent", None)
    acceptance = getattr(customer, "default_payment_acceptance_percent", None)
    return (
        str(code).strip() if code else None,
        Decimal(str(wire)) if wire is not None else None,
        Decimal(str(acceptance)) if acceptance is not None else None,
    )


async def resolve_payable_payment_method_for_source(
    tenant_id: int,
    *,
    supplier_id: int,
    source_type: Optional[str],
    source_id: Optional[int],
) -> Tuple[Optional[str], Optional[Decimal], Optional[Decimal], Optional[str]]:
    """按应付来源解析付款方式（优先采购订单）。"""
    from apps.kuaicaiwu.constants.finance_source_types import (
        PAYABLE_SOURCE_PURCHASE_RECEIPT,
    )

    st = str(source_type or "").strip()
    sid = int(source_id or 0)
    po_id: Optional[int] = None

    if st in {"purchase_receipt", "PurchaseReceipt", PAYABLE_SOURCE_PURCHASE_RECEIPT} and sid > 0:
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        receipt = await PurchaseReceipt.get_or_none(
            tenant_id=tenant_id, id=sid, deleted_at__isnull=True
        )
        if receipt and receipt.purchase_order_id:
            po_id = int(receipt.purchase_order_id)

    if po_id:
        from apps.kuaizhizao.models.purchase_order import PurchaseOrder

        order = await PurchaseOrder.get_or_none(
            tenant_id=tenant_id, id=po_id, deleted_at__isnull=True
        )
        if order:
            return payment_method_fields_from_source(order)

    from apps.master_data.models.supplier import Supplier

    supplier = await Supplier.get_or_none(
        tenant_id=tenant_id, id=int(supplier_id), deleted_at__isnull=True
    )
    if supplier:
        code, wire, acceptance = payment_method_fields_from_supplier(supplier)
        summary = (
            format_payment_method_mix_label_zh(wire, acceptance)
            if code == PARTNER_MIXED_PAYMENT_METHOD
            else None
        )
        return code, wire, acceptance, summary
    return None, None, None, None


def payment_method_fields_from_supplier(supplier: Any) -> Tuple[Optional[str], Optional[Decimal], Optional[Decimal]]:
    code = getattr(supplier, "default_payment_method_code", None)
    wire = getattr(supplier, "default_payment_wire_percent", None)
    acceptance = getattr(supplier, "default_payment_acceptance_percent", None)
    return (
        str(code).strip() if code else None,
        Decimal(str(wire)) if wire is not None else None,
        Decimal(str(acceptance)) if acceptance is not None else None,
    )