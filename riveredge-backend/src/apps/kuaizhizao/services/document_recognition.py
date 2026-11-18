"""业务单据头立账策略：默认解析与门控（单据字段为真源）。"""

from __future__ import annotations

from typing import Any, Optional

from core.config.finance_recognition import (
    PAYABLE_RECOGNITION_VALUES,
    REVENUE_RECOGNITION_VALUES,
)
from infra.services.business_config_service import BusinessConfigService

DEFAULT_REVENUE_RECOGNITION = "on_shipment"
DEFAULT_PAYABLE_RECOGNITION = "on_receipt"

_business_config = BusinessConfigService()


def coerce_revenue_recognition(value: Any, *, fallback: str = DEFAULT_REVENUE_RECOGNITION) -> str:
    s = str(value or "").strip()
    return s if s in REVENUE_RECOGNITION_VALUES else fallback


def coerce_payable_recognition(value: Any, *, fallback: str = DEFAULT_PAYABLE_RECOGNITION) -> str:
    s = str(value or "").strip()
    return s if s in PAYABLE_RECOGNITION_VALUES else fallback


def revenue_recognition_from_doc(doc: Any, *, fallback: str = DEFAULT_REVENUE_RECOGNITION) -> str:
    return coerce_revenue_recognition(getattr(doc, "revenue_recognition", None), fallback=fallback)


def payable_recognition_from_doc(doc: Any, *, fallback: str = DEFAULT_PAYABLE_RECOGNITION) -> str:
    return coerce_payable_recognition(getattr(doc, "payable_recognition", None), fallback=fallback)


async def default_revenue_recognition(tenant_id: int, customer_id: Optional[int]) -> str:
    return await _business_config.resolve_revenue_recognition(tenant_id, customer_id)


async def default_payable_recognition(tenant_id: int, supplier_id: Optional[int]) -> str:
    return await _business_config.resolve_payable_recognition(tenant_id, supplier_id)


async def ensure_revenue_recognition_on_create(
    tenant_id: int,
    customer_id: Optional[int],
    provided: Any,
) -> str:
    if provided is not None and str(provided).strip() in REVENUE_RECOGNITION_VALUES:
        return str(provided).strip()
    return await default_revenue_recognition(tenant_id, customer_id)


async def ensure_payable_recognition_on_create(
    tenant_id: int,
    supplier_id: Optional[int],
    provided: Any,
) -> str:
    if provided is not None and str(provided).strip() in PAYABLE_RECOGNITION_VALUES:
        return str(provided).strip()
    return await default_payable_recognition(tenant_id, supplier_id)


async def resolve_revenue_for_downstream(
    tenant_id: int,
    customer_id: Optional[int],
    *,
    upstream: Any = None,
    provided: Any = None,
) -> str:
    if provided is not None and str(provided).strip() in REVENUE_RECOGNITION_VALUES:
        return str(provided).strip()
    if upstream is not None:
        return revenue_recognition_from_doc(upstream)
    return await default_revenue_recognition(tenant_id, customer_id)


async def resolve_payable_for_downstream(
    tenant_id: int,
    supplier_id: Optional[int],
    *,
    upstream: Any = None,
    provided: Any = None,
) -> str:
    if provided is not None and str(provided).strip() in PAYABLE_RECOGNITION_VALUES:
        return str(provided).strip()
    if upstream is not None:
        return payable_recognition_from_doc(upstream)
    return await default_payable_recognition(tenant_id, supplier_id)


def should_auto_receivable_on_sales_delivery(strategy: str) -> bool:
    return coerce_revenue_recognition(strategy) in ("on_shipment", "mixed")


def should_auto_receivable_on_sales_return(strategy: str) -> bool:
    s = coerce_revenue_recognition(strategy)
    return s not in ("manual", "on_partner_statement")


def should_auto_payable_on_purchase_receipt(strategy: str) -> bool:
    return coerce_payable_recognition(strategy) == "on_receipt"


def should_auto_payable_on_purchase_invoice(strategy: str) -> bool:
    return coerce_payable_recognition(strategy) == "on_purchase_invoice"


def should_auto_payable_on_purchase_return(strategy: str) -> bool:
    s = coerce_payable_recognition(strategy)
    return s not in ("manual", "on_partner_statement")


def describe_purchase_return_payable_auto_skip(strategy: str) -> str | None:
    """未自动立红字应付时的原因（供 finance_outcome 展示）。"""
    s = coerce_payable_recognition(strategy)
    if s == "manual":
        return "组织应付确认为手工立账，确认退货时未自动生成红字应付"
    if s == "on_partner_statement":
        return "组织应付确认为对账立账，确认退货时未自动生成红字应付"
    return None


def describe_purchase_receipt_payable_auto_skip(strategy: str) -> str | None:
    """确认入库未自动生成蓝字应付时的原因（供 finance_outcome 展示）。"""
    s = coerce_payable_recognition(strategy)
    if s == "on_purchase_invoice":
        return "立账策略为以进项发票为准，确认入库时未自动生成应付"
    if s == "manual":
        return "立账策略为手工立账，确认入库时未自动生成应付"
    if s == "on_partner_statement":
        return "立账策略为对账立账，确认入库时未自动生成应付"
    return None


def describe_purchase_invoice_payable_auto_skip(strategy: str) -> str | None:
    """创建进项发票未自动生成应付时的原因。"""
    s = coerce_payable_recognition(strategy)
    if s == "on_receipt":
        return "立账策略为以采购入库确认为准，创建发票时未自动生成应付"
    if s == "manual":
        return "立账策略为手工立账，创建发票时未自动生成应付"
    if s == "on_partner_statement":
        return "立账策略为对账立账，创建发票时未自动生成应付"
    return None


async def resolve_payable_recognition_for_purchase_invoice(
    tenant_id: int,
    invoice: Any,
) -> str:
    """进项发票自动应付门控：优先读关联采购订单/入库单上的 payable_recognition。"""
    from apps.kuaizhizao.models.purchase_order import PurchaseOrder
    from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
    from apps.kuaicaiwu.models.payable import Payable
    from apps.kuaicaiwu.constants.finance_source_types import PAYABLE_SOURCE_PURCHASE_RECEIPT

    po_id = getattr(invoice, "purchase_order_id", None)
    if po_id:
        po = await PurchaseOrder.get_or_none(
            tenant_id=tenant_id, id=int(po_id), deleted_at__isnull=True
        )
        if po is not None:
            return payable_recognition_from_doc(po)

    payable_id = getattr(invoice, "payable_id", None)
    if payable_id:
        payable = await Payable.get_or_none(
            tenant_id=tenant_id, id=int(payable_id), deleted_at__isnull=True
        )
        if payable and payable.source_id and str(payable.source_type or "").strip() in (
            PAYABLE_SOURCE_PURCHASE_RECEIPT,
            "purchase_receipt",
            "PurchaseReceipt",
        ):
            receipt = await PurchaseReceipt.get_or_none(
                tenant_id=tenant_id, id=int(payable.source_id), deleted_at__isnull=True
            )
            if receipt is not None:
                return payable_recognition_from_doc(receipt)

    from apps.kuaizhizao.models.document_relation import DocumentRelation

    # DocumentRelation 无 deleted_at；加载建票约定 source=入库 → target=发票
    rel = await DocumentRelation.filter(
        tenant_id=tenant_id,
        source_type="purchase_receipt",
        target_type="purchase_invoice",
        target_id=int(invoice.id),
    ).first()
    if rel and rel.source_id:
        receipt = await PurchaseReceipt.get_or_none(
            tenant_id=tenant_id, id=int(rel.source_id), deleted_at__isnull=True
        )
        if receipt is not None:
            return payable_recognition_from_doc(receipt)

    supplier_id = getattr(invoice, "supplier_id", None)
    return await default_payable_recognition(
        tenant_id, int(supplier_id) if supplier_id is not None else None
    )


def should_auto_receivable_on_misc_voucher_approve(strategy: str) -> bool:
    s = coerce_revenue_recognition(strategy)
    return s not in ("manual", "on_partner_statement")


def should_auto_payable_on_misc_voucher_approve(strategy: str) -> bool:
    """其他费用支出：审核通过即确认时点；不含手工/对账立账（与采购入库/收票链路不同构）。"""
    s = coerce_payable_recognition(strategy)
    return s not in ("manual", "on_partner_statement")


def payable_recognition_for_misc_expense_counterparty(
    counterparty_kind: str,
    resolved: str,
) -> str:
    """非供应商往来不自动挂应付，立账策略固定为 manual（写路径真源）。"""
    kind = str(counterparty_kind or "").strip().lower()
    if kind != "supplier":
        return "manual"
    return coerce_payable_recognition(resolved)
