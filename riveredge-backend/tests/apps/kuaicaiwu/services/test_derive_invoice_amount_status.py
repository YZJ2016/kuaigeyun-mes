from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from apps.kuaicaiwu.schemas.finance import ReceivableResponse
from apps.kuaicaiwu.constants.finance_source_types import (
    PAYABLE_SOURCE_PURCHASE_INVOICE_DISCOUNT,
    is_payable_red_total_source,
    payable_total_must_be_negative,
)
from apps.kuaicaiwu.services.purchase_invoice_amounts import (
    purchase_invoice_discount,
    purchase_invoice_face_total,
    purchase_invoice_occupancy_amount,
)


def test_purchase_invoice_occupancy_is_face_plus_discount():
    invoice = SimpleNamespace(total_amount=Decimal("950"), discount_amount=Decimal("50"))
    assert purchase_invoice_face_total(invoice) == Decimal("950.00")
    assert purchase_invoice_discount(invoice) == Decimal("50.00")
    assert purchase_invoice_occupancy_amount(invoice) == Decimal("1000.00")


def test_purchase_invoice_occupancy_negative_discount():
    invoice = SimpleNamespace(total_amount=Decimal("1030"), discount_amount=Decimal("-30"))
    assert purchase_invoice_occupancy_amount(invoice) == Decimal("1000.00")


def test_discount_adjustment_source_is_signed_payable():
    assert is_payable_red_total_source(PAYABLE_SOURCE_PURCHASE_INVOICE_DISCOUNT)
    assert not payable_total_must_be_negative(PAYABLE_SOURCE_PURCHASE_INVOICE_DISCOUNT)


@pytest.mark.asyncio
async def test_purchase_invoice_approved_payable_keeps_upstream_early_return(monkeypatch):
    from apps.kuaicaiwu.services import purchase_invoice_payable_auto as auto
    from apps.kuaicaiwu.services import finance_audit_workflow as workflow

    invoice = SimpleNamespace(id=7, payable_id=12, payable_code="AP12", adjust_payable=True)
    monkeypatch.setattr(auto.PurchaseInvoice, "get_or_none", AsyncMock(return_value=invoice))
    monkeypatch.setattr(
        auto.Payable, "get_or_none", AsyncMock(return_value=SimpleNamespace(review_status="已审核"))
    )
    adjustment = AsyncMock()
    submit = AsyncMock()
    monkeypatch.setattr(auto, "maybe_create_discount_adjustment_payable_for_purchase_invoice", adjustment)
    monkeypatch.setattr(workflow, "submit_finance_review", submit)

    assert await auto.ensure_payable_after_purchase_invoice_approved(
        tenant_id=3, invoice_id=7, user_id=2
    ) == 12
    adjustment.assert_not_awaited()
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_purchase_invoice_generated_payable_uses_face_not_occupancy(monkeypatch):
    from apps.kuaicaiwu.services import purchase_invoice_payable_auto as auto

    invoice = SimpleNamespace(
        id=7, payable_id=None, invoice_code="PI7", supplier_id=9, supplier_name="供应商",
        total_amount=Decimal("950"), discount_amount=Decimal("50"),
        invoice_date=None, invoice_number="INV7",
    )
    monkeypatch.setattr(
        auto, "resolve_payable_recognition_for_purchase_invoice",
        AsyncMock(return_value="on_purchase_invoice"),
    )
    monkeypatch.setattr(
        auto._business_config, "should_auto_generate_payable_from_purchase_invoice_effective",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(auto._business_config, "check_node_enabled", AsyncMock(return_value=True))
    from apps.kuaicaiwu.services import finance_due_date
    from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService

    monkeypatch.setattr(finance_due_date, "resolve_partner_due_date", AsyncMock(return_value="2026-12-01"))
    create = AsyncMock(return_value=SimpleNamespace(id=12, payable_code="AP12"))
    monkeypatch.setattr(auto._payable_service, "create_payable", create)
    update = AsyncMock()
    monkeypatch.setattr(
        auto.PurchaseInvoice, "filter", lambda **kwargs: SimpleNamespace(update=update),
    )
    monkeypatch.setattr(DocumentRelationNewService, "create_relation", AsyncMock())

    assert await auto.maybe_auto_generate_payable_for_purchase_invoice(
        tenant_id=3, invoice=invoice, created_by=2,
    ) == (12, "AP12")
    payload = create.call_args.kwargs["payable_data"]
    assert payload.total_amount == Decimal("950")
    assert payload.remaining_amount == Decimal("950")
    assert create.call_args.kwargs["submit_review"] is False
    update.assert_awaited_once_with(payable_id=12, payable_code="AP12")


def test_receivable_response_accepts_negative_invoiced_amount():
    payload = ReceivableResponse.model_validate(
        {
            "id": 1,
            "tenant_id": 1,
            "receivable_code": "AR20260901001",
            "source_type": "sales_order",
            "source_id": 1,
            "source_code": "SO20260901001",
            "customer_id": 1,
            "customer_name": "测试客户",
            "total_amount": Decimal("1000.00"),
            "received_amount": Decimal("0"),
            "remaining_amount": Decimal("1000.00"),
            "status": "未结清",
            "review_status": "已审核",
            "business_date": "2026-09-01",
            "due_date": "2026-10-01",
            "invoiced_amount": Decimal("-888.00"),
            "remaining_invoice_amount": Decimal("1888.00"),
            "invoice_status": "未开票",
            "created_at": "2026-09-01T00:00:00",
            "updated_at": "2026-09-01T00:00:00",
        }
    )
    assert payload.invoiced_amount == Decimal("-888.00")
