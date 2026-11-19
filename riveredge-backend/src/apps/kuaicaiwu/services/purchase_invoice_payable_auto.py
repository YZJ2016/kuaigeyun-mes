"""采购发票审核通过后按立账策略自动生成应付（对齐销项发票→应收）。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional, Tuple

from loguru import logger

from apps.kuaicaiwu.constants.finance_source_types import (
    PAYABLE_SOURCE_PURCHASE_INVOICE_DISCOUNT,
)
from apps.kuaicaiwu.models.payable import Payable
from apps.kuaicaiwu.models.purchase_invoice import PurchaseInvoice
from apps.kuaicaiwu.schemas.finance import PayableCreate
from apps.kuaicaiwu.services.purchase_invoice_amounts import (
    purchase_invoice_discount,
    purchase_invoice_face_total,
)
from apps.kuaicaiwu.services.finance_service import PayableService
from apps.kuaizhizao.services.document_recognition import (
    resolve_payable_recognition_for_purchase_invoice,
    should_auto_payable_on_purchase_invoice,
)
from core.utils.timezone_utils import resolve_business_datetime, to_site_date
from infra.services.business_config_service import BusinessConfigService

_business_config = BusinessConfigService()
_payable_service = PayableService()


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


async def maybe_auto_generate_payable_for_purchase_invoice(
    *,
    tenant_id: int,
    invoice: PurchaseInvoice | Any,
    created_by: int,
) -> Tuple[Optional[int], Optional[str]]:
    """按单据/组织立账策略尝试生成应付；已有 payable_id 则跳过。"""
    if getattr(invoice, "payable_id", None):
        return int(invoice.payable_id), getattr(invoice, "payable_code", None)

    strategy = await resolve_payable_recognition_for_purchase_invoice(tenant_id, invoice)
    if not should_auto_payable_on_purchase_invoice(strategy):
        return None, None
    supplier_id = getattr(invoice, "supplier_id", None)
    if not await _business_config.should_auto_generate_payable_from_purchase_invoice_effective(
        tenant_id,
        int(supplier_id) if supplier_id is not None else None,
        resolved_strategy=strategy,
    ):
        return None, None
    if not await _business_config.check_node_enabled(tenant_id, "payable"):
        return None, None

    total = _money(getattr(invoice, "total_amount", None))
    if total <= 0:
        return None, None

    from apps.kuaicaiwu.services.finance_due_date import resolve_partner_due_date

    biz_date = getattr(invoice, "invoice_date", None) or to_site_date(resolve_business_datetime())
    due = await resolve_partner_due_date(
        tenant_id, "supplier", int(invoice.supplier_id), biz_date
    )
    payable = await _payable_service.create_payable(
        tenant_id=tenant_id,
        payable_data=PayableCreate(
            source_type="PurchaseInvoice",
            source_id=invoice.id,
            source_code=invoice.invoice_code,
            supplier_id=invoice.supplier_id,
            supplier_name=invoice.supplier_name,
            total_amount=total,
            paid_amount=Decimal("0.00"),
            remaining_amount=total,
            due_date=due,
            business_date=biz_date,
            status="未付款",
            invoice_received=True,
            invoice_number=invoice.invoice_number,
        ),
        created_by=created_by,
        submit_review=False,
    )
    await PurchaseInvoice.filter(tenant_id=tenant_id, id=invoice.id).update(
        payable_id=payable.id,
        payable_code=payable.payable_code,
    )
    invoice.payable_id = payable.id
    invoice.payable_code = payable.payable_code
    try:
        from apps.kuaizhizao.schemas.document_relation import DocumentRelationCreate
        from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService

        rel_svc = DocumentRelationNewService()
        await rel_svc.create_relation(
            tenant_id=tenant_id,
            relation_data=DocumentRelationCreate(
                source_type="purchase_invoice",
                source_id=invoice.id,
                source_code=invoice.invoice_code,
                source_name=None,
                target_type="payable",
                target_id=payable.id,
                target_code=payable.payable_code,
                target_name=None,
                relation_type="source",
                relation_mode="push",
                relation_desc="采购发票自动生成应付单",
            ),
            created_by=created_by,
        )
    except Exception as rel_e:
        logger.warning("创建采购发票→应付单 单据关联失败: {}", rel_e)
    return int(payable.id), payable.payable_code


async def maybe_create_discount_adjustment_payable_for_purchase_invoice(
    *,
    tenant_id: int,
    invoice: PurchaseInvoice | Any,
    created_by: int,
) -> Tuple[Optional[int], Optional[str]]:
    """从应付收票且勾选调整应付时，生成金额 -D 的优惠调整应付。"""
    if not bool(getattr(invoice, "adjust_payable", False)):
        return None, None
    if not getattr(invoice, "payable_id", None):
        return None, None
    discount = purchase_invoice_discount(invoice)
    if discount == 0:
        return None, None

    existing = await Payable.get_or_none(
        tenant_id=tenant_id,
        source_type=PAYABLE_SOURCE_PURCHASE_INVOICE_DISCOUNT,
        source_id=int(invoice.id),
        deleted_at__isnull=True,
    )
    if existing:
        return int(existing.id), existing.payable_code

    adj_total = _money(-discount)
    if adj_total == 0:
        return None, None
    if not await _business_config.check_node_enabled(tenant_id, "payable"):
        return None, None

    from apps.kuaicaiwu.services.finance_due_date import resolve_partner_due_date

    biz_date = getattr(invoice, "invoice_date", None) or to_site_date(resolve_business_datetime())
    due = await resolve_partner_due_date(
        tenant_id, "supplier", int(invoice.supplier_id), biz_date
    )
    payable = await _payable_service.create_payable(
        tenant_id=tenant_id,
        payable_data=PayableCreate(
            source_type=PAYABLE_SOURCE_PURCHASE_INVOICE_DISCOUNT,
            source_id=invoice.id,
            source_code=invoice.invoice_code,
            supplier_id=invoice.supplier_id,
            supplier_name=invoice.supplier_name,
            total_amount=adj_total,
            paid_amount=Decimal("0.00"),
            remaining_amount=adj_total,
            due_date=due,
            business_date=biz_date,
            status="未付款",
            invoice_received=True,
            invoice_number=invoice.invoice_number,
            notes=f"采购收票优惠调整(票面{purchase_invoice_face_total(invoice)},优惠{discount})",
        ),
        created_by=created_by,
        submit_review=False,
    )
    try:
        from apps.kuaizhizao.schemas.document_relation import DocumentRelationCreate
        from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService

        rel_svc = DocumentRelationNewService()
        await rel_svc.create_relation(
            tenant_id=tenant_id,
            relation_data=DocumentRelationCreate(
                source_type="purchase_invoice",
                source_id=invoice.id,
                source_code=invoice.invoice_code,
                source_name=None,
                target_type="payable",
                target_id=payable.id,
                target_code=payable.payable_code,
                target_name=None,
                relation_type="source",
                relation_mode="push",
                relation_desc="采购收票优惠调整应付",
            ),
            created_by=created_by,
        )
    except Exception as rel_e:
        logger.warning("创建采购发票→优惠调整应付 单据关联失败: {}", rel_e)
    return int(payable.id), payable.payable_code


async def ensure_payable_after_purchase_invoice_approved(
    *,
    tenant_id: int,
    invoice_id: int,
    user_id: int,
) -> Optional[int]:
    """采购发票已审核后：按策略生成应付，并对草稿应付送审。"""
    from apps.kuaicaiwu.services.finance_audit_workflow import (
        _APPROVED_REVIEW,
        _PENDING_REVIEW,
        _norm_review,
        submit_finance_review,
    )

    invoice = await PurchaseInvoice.get_or_none(
        tenant_id=tenant_id, id=invoice_id, deleted_at__isnull=True
    )
    if not invoice:
        return None

    auto_id, _ = await maybe_auto_generate_payable_for_purchase_invoice(
        tenant_id=tenant_id,
        invoice=invoice,
        created_by=user_id,
    )
    payable_id = auto_id or (
        int(invoice.payable_id) if getattr(invoice, "payable_id", None) else None
    )
    if not payable_id:
        return None

    payable = await Payable.get_or_none(
        tenant_id=tenant_id, id=int(payable_id), deleted_at__isnull=True
    )
    if not payable:
        return None

    rs = _norm_review(getattr(payable, "review_status", None))
    if rs in _APPROVED_REVIEW or rs in _PENDING_REVIEW:
        return int(payable_id)

    await submit_finance_review(
        model=Payable,
        tenant_id=tenant_id,
        doc_id=int(payable_id),
        updated_by=user_id,
        doc_label="应付单",
        node_key="payable",
    )

    invoice = await PurchaseInvoice.get_or_none(
        tenant_id=tenant_id, id=invoice_id, deleted_at__isnull=True
    )
    if invoice:
        adj_id, _ = await maybe_create_discount_adjustment_payable_for_purchase_invoice(
            tenant_id=tenant_id,
            invoice=invoice,
            created_by=user_id,
        )
        if adj_id:
            adj_payable = await Payable.get_or_none(
                tenant_id=tenant_id, id=int(adj_id), deleted_at__isnull=True
            )
            if adj_payable:
                rs_adj = _norm_review(getattr(adj_payable, "review_status", None))
                if rs_adj not in _APPROVED_REVIEW and rs_adj not in _PENDING_REVIEW:
                    await submit_finance_review(
                        model=Payable,
                        tenant_id=tenant_id,
                        doc_id=int(adj_id),
                        updated_by=user_id,
                        doc_label="应付单",
                        node_key="payable",
                    )
    return int(payable_id)
