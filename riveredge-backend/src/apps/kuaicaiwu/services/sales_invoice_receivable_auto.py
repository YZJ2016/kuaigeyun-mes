"""销售发票审核通过后按立账策略自动生成应收。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional, Tuple

from loguru import logger

from apps.kuaicaiwu.constants import RECEIVABLE_SOURCE_SALES_INVOICE
from apps.kuaicaiwu.models.invoice import Invoice
from apps.kuaicaiwu.schemas.finance import ReceivableCreate
from apps.kuaicaiwu.services.finance_service import ReceivableService
from apps.kuaizhizao.services.document_recognition import (
    resolve_revenue_recognition_for_sales_invoice,
    should_auto_receivable_on_sales_invoice,
)
from core.utils.timezone_utils import resolve_business_datetime, to_site_date
from infra.services.business_config_service import BusinessConfigService

_business_config = BusinessConfigService()
_receivable_service = ReceivableService()


async def maybe_auto_generate_receivable_for_sales_invoice(
    *,
    tenant_id: int,
    invoice: Invoice | Any,
    created_by: int,
) -> Tuple[Optional[int], Optional[str]]:
    if getattr(invoice, "receivable_id", None):
        return None, None
    partner_id = getattr(invoice, "partner_id", None)
    resolved = await resolve_revenue_recognition_for_sales_invoice(tenant_id, invoice)
    if not should_auto_receivable_on_sales_invoice(resolved):
        return None, None
    if not await _business_config.should_auto_generate_receivable_from_sales_invoice_effective(
        tenant_id,
        int(partner_id) if partner_id is not None else None,
        resolved_strategy=resolved,
    ):
        logger.info(
            "销项发票 {} 跳过自动生成应收：组织门控未放行（解析策略={}）",
            getattr(invoice, "id", None),
            resolved,
        )
        return None, None
    if not await _business_config.check_node_enabled(tenant_id, "receivable"):
        return None, None

    if Decimal(invoice.total_amount or 0) <= 0:
        return None, None

    from apps.kuaicaiwu.services.finance_due_date import resolve_partner_due_date

    biz_date = invoice.invoice_date or to_site_date(resolve_business_datetime())
    due = await resolve_partner_due_date(tenant_id, "customer", int(invoice.partner_id), biz_date)
    receivable = await _receivable_service.create_receivable(
        tenant_id=tenant_id,
        receivable_data=ReceivableCreate(
            source_type=RECEIVABLE_SOURCE_SALES_INVOICE,
            source_id=invoice.id,
            source_code=invoice.invoice_code,
            customer_id=invoice.partner_id,
            customer_name=invoice.partner_name,
            total_amount=Decimal(invoice.total_amount or 0),
            received_amount=Decimal("0.00"),
            remaining_amount=Decimal(invoice.total_amount or 0),
            due_date=due,
            business_date=biz_date,
            status="未收款",
            invoice_issued=True,
            invoice_number=invoice.invoice_number,
        ),
        created_by=created_by,
        submit_review=False,
    )
    await Invoice.filter(tenant_id=tenant_id, id=invoice.id).update(
        receivable_id=receivable.id,
        receivable_code=receivable.receivable_code,
    )
    try:
        from apps.kuaizhizao.schemas.document_relation import DocumentRelationCreate
        from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService

        rel_svc = DocumentRelationNewService()
        await rel_svc.create_relation(
            tenant_id=tenant_id,
            relation_data=DocumentRelationCreate(
                source_type="sales_invoice",
                source_id=invoice.id,
                source_code=invoice.invoice_code,
                source_name=None,
                target_type="receivable",
                target_id=receivable.id,
                target_code=receivable.receivable_code,
                target_name=None,
                relation_type="source",
                relation_mode="push",
                relation_desc="销售发票自动生成应收单",
            ),
            created_by=created_by,
        )
    except Exception as rel_e:
        logger.warning("创建销售发票→应收单 单据关联失败: {}", rel_e)
    return receivable.id, receivable.receivable_code


async def ensure_receivable_after_sales_invoice_approved(
    *,
    tenant_id: int,
    invoice_id: int,
    user_id: int,
) -> Optional[int]:
    """
    销售发票已审核后：按策略生成应收（若尚无），补跑月结「根据发票立账」对账单，并对草稿应收送审。
    对称 ensure_payable_after_purchase_invoice_approved。
    """
    from apps.kuaicaiwu.services.finance_audit_workflow import (
        _APPROVED_REVIEW,
        _PENDING_REVIEW,
        _norm_review,
        submit_finance_review,
    )

    invoice = await Invoice.get_or_none(
        tenant_id=tenant_id,
        id=invoice_id,
        category="OUT",
        deleted_at__isnull=True,
    )
    if not invoice:
        return None

    auto_id, _ = await maybe_auto_generate_receivable_for_sales_invoice(
        tenant_id=tenant_id,
        invoice=invoice,
        created_by=user_id,
    )
    receivable_id = auto_id or (
        int(invoice.receivable_id) if getattr(invoice, "receivable_id", None) else None
    )

    from apps.kuaicaiwu.services.partner_statement_service import PartnerStatementService

    await PartnerStatementService().try_complete_ledger_after_sales_invoice_approved(
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        operator_id=user_id,
    )

    if not receivable_id:
        return None

    from apps.kuaicaiwu.models.receivable import Receivable

    receivable = await Receivable.get_or_none(
        tenant_id=tenant_id, id=int(receivable_id), deleted_at__isnull=True
    )
    if not receivable:
        return None

    rs = _norm_review(getattr(receivable, "review_status", None))
    if rs in _APPROVED_REVIEW or rs in _PENDING_REVIEW:
        return int(receivable_id)

    await submit_finance_review(
        model=Receivable,
        tenant_id=tenant_id,
        doc_id=int(receivable_id),
        updated_by=user_id,
        doc_label="应收单",
        node_key="receivable",
    )
    return int(receivable_id)