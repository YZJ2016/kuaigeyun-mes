"""Spec 223 Batch 1B: CW-P5 采购发票进项认证与红冲允许「已开票」状态。"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaicaiwu.services.tax.purchase_invoice_tax_service import PurchaseInvoiceTaxService
from apps.kuaicaiwu.services.tax.tax_constants import (
    TAXPAYER_GENERAL,
    VERIFICATION_CERTIFIED,
    VERIFICATION_PENDING,
)
from infra.exceptions.exceptions import ValidationError


def _fake_tx():
    return MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False))


@pytest.mark.asyncio
@pytest.mark.parametrize("status_value", ["已审核", "已开票"])
async def test_certify_allows_approved_and_invoiced(status_value):
    svc = PurchaseInvoiceTaxService()
    inv = SimpleNamespace(
        id=1,
        status=status_value,
        verification_status=VERIFICATION_PENDING,
        verification_date=None,
        original_invoice_id=None,
        save=AsyncMock(),
    )
    with patch.object(
        svc.settings_service,
        "get_or_create",
        AsyncMock(return_value=SimpleNamespace(taxpayer_type=TAXPAYER_GENERAL)),
    ), patch.object(
        svc, "_get_invoice", AsyncMock(return_value=inv)
    ), patch.object(
        svc.period_service, "assert_period_editable", AsyncMock()
    ):
        res = await svc.certify(1, 1, verification_date=date(2026, 5, 15))

    assert res.verification_status == VERIFICATION_CERTIFIED
    assert res.verification_date == date(2026, 5, 15)
    inv.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_certify_rejects_unapproved_status():
    svc = PurchaseInvoiceTaxService()
    inv = SimpleNamespace(
        id=1,
        status="未审核",
        verification_status=VERIFICATION_PENDING,
        original_invoice_id=None,
    )
    with patch.object(
        svc.settings_service,
        "get_or_create",
        AsyncMock(return_value=SimpleNamespace(taxpayer_type=TAXPAYER_GENERAL)),
    ), patch.object(svc, "_get_invoice", AsyncMock(return_value=inv)):
        with pytest.raises(ValidationError, match="仅已审核发票可认证"):
            await svc.certify(1, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_value", ["已审核", "已开票"])
async def test_create_red_flush_allows_approved_and_invoiced(status_value):
    svc = PurchaseInvoiceTaxService()
    orig = SimpleNamespace(
        id=10,
        invoice_code="PI20260501001",
        purchase_order_id=1,
        purchase_order_code="PO001",
        supplier_id=2,
        supplier_name="供应商A",
        invoice_number="INV-001",
        invoice_date=date(2026, 5, 1),
        invoice_type="增值税专用发票",
        tax_period="2026-05",
        tax_rate=Decimal("13"),
        invoice_amount=Decimal("100.00"),
        tax_amount=Decimal("13.00"),
        total_amount=Decimal("113.00"),
        discount_amount=Decimal("0"),
        payable_id=None,
        payable_code=None,
        status=status_value,
        original_invoice_id=None,
        red_flush_invoice_id=None,
        save=AsyncMock(),
    )
    created_red = SimpleNamespace(id=11)
    with patch(
        "apps.kuaicaiwu.services.tax.purchase_invoice_tax_service.in_transaction",
        return_value=_fake_tx(),
    ), patch.object(
        svc, "_get_invoice", AsyncMock(return_value=orig)
    ), patch.object(
        svc, "_assert_editable", AsyncMock()
    ), patch.object(
        svc._base, "generate_code", AsyncMock(return_value="PI20260515002")
    ), patch(
        "apps.kuaicaiwu.services.tax.purchase_invoice_tax_service.PurchaseInvoice.create",
        AsyncMock(return_value=created_red),
    ):
        red = await svc.create_red_flush(1, 10, "开票有误", created_by=7)

    assert red is created_red
    assert orig.red_flush_invoice_id == 11
    orig.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_red_flush_rejects_unapproved_status():
    svc = PurchaseInvoiceTaxService()
    orig = SimpleNamespace(
        id=10,
        status="未审核",
        original_invoice_id=None,
        red_flush_invoice_id=None,
    )
    with patch(
        "apps.kuaicaiwu.services.tax.purchase_invoice_tax_service.in_transaction",
        return_value=_fake_tx(),
    ), patch.object(svc, "_get_invoice", AsyncMock(return_value=orig)):
        with pytest.raises(ValidationError, match="仅已审核的蓝字发票可红冲"):
            await svc.create_red_flush(1, 10, "开票有误", created_by=7)
