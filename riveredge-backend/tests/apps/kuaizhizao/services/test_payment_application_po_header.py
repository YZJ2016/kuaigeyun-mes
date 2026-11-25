"""采购订单 → 付款申请表头带入。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaizhizao.services.payment_application_po_header import (
    payment_method_label_from_purchase_order,
    payment_application_header_from_purchase_order,
    resolve_invoice_status_from_purchase_order,
)


def test_payment_method_label_from_po_bank_transfer():
    order = SimpleNamespace(
        payment_method_code="bank_transfer",
        payment_wire_percent=None,
        payment_acceptance_percent=None,
    )
    assert payment_method_label_from_purchase_order(order) == "银行转账"


@pytest.mark.asyncio
async def test_header_from_tax_inclusive_po_prepayment():
    order = SimpleNamespace(
        id=1,
        tax_rate=Decimal("0.13"),
        price_type="tax_inclusive",
        payment_method_code="bank_transfer",
        payment_wire_percent=None,
        payment_acceptance_percent=None,
    )
    with patch(
        "apps.kuaizhizao.services.payment_application_po_header.resolve_tax_rate_percent_from_purchase_order",
        new=AsyncMock(return_value=Decimal("13.00")),
    ), patch(
        "apps.kuaizhizao.services.payment_application_po_header._purchase_order_has_approved_invoice",
        new=AsyncMock(return_value=False),
    ):
        header = await payment_application_header_from_purchase_order(
            1, order, application_kind="prepayment"
        )
    assert header["invoice_status"] == "发票后补"
    assert "tax_rate" not in header
    assert header["payment_method"] == "银行转账"


@pytest.mark.asyncio
async def test_invoice_status_no_invoice_when_tax_exclusive():
    order = SimpleNamespace(
        id=2,
        tax_rate=Decimal("0.13"),
        price_type="tax_exclusive",
    )
    with patch(
        "apps.kuaizhizao.services.payment_application_po_header._purchase_order_has_approved_invoice",
        new=AsyncMock(return_value=False),
    ):
        status = await resolve_invoice_status_from_purchase_order(1, order)
    assert status == "无发票"