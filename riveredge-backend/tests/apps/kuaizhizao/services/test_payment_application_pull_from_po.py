"""付款申请自采购订单取单：无预付节点时按订单价税合计计可请款。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaizhizao.services.document_action_policy.purchase_order import (
    derive_purchase_order_capabilities,
)
from apps.kuaizhizao.services.payment_application_pull_service import (
    PaymentApplicationPullService,
    _payment_reason_for_purchase_orders,
    _payment_reason_for_purchase_receipts,
    compute_prepayment_application_remaining,
    prepayment_application_base_amount,
)


def test_base_amount_uses_gross_when_no_prepayment():
    order = SimpleNamespace(
        prepayment_amount=Decimal("0"),
        total_amount=Decimal("1000"),
        net_amount=Decimal("1130"),
        tax_rate=Decimal("0.13"),
    )
    assert prepayment_application_base_amount(order) == Decimal("1130.00")


def test_base_amount_uses_prepayment_when_set():
    order = SimpleNamespace(prepayment_amount=Decimal("3000"), total_amount=Decimal("10000"))
    assert prepayment_application_base_amount(order) == Decimal("3000")


def test_base_amount_keeps_prepay_when_equals_excl_header():
    """预付额等于未税合计且小于价税合计时，可请款基数仍是预付额。"""
    order = SimpleNamespace(
        prepayment_amount=Decimal("176.99"),
        total_amount=Decimal("176.99"),
        tax_amount=Decimal("23.01"),
        net_amount=Decimal("0"),
        tax_rate=Decimal("0.13"),
    )
    assert prepayment_application_base_amount(order) == Decimal("176.99")


def test_remaining_subtracts_reserved_from_gross_when_no_prepay():
    order = SimpleNamespace(
        prepayment_amount=None,
        total_amount=Decimal("1000"),
        net_amount=Decimal("1130"),
        tax_rate=Decimal("0.13"),
    )
    assert compute_prepayment_application_remaining(order, Decimal("310")) == Decimal("820.00")


def test_push_payment_application_allowed_without_prepayment_node():
    order = SimpleNamespace(
        status="CONFIRMED",
        review_status="APPROVED",
        supplier_id=1,
        prepayment_amount=Decimal("0"),
        total_amount=Decimal("5000"),
    )
    caps = derive_purchase_order_capabilities(
        order,
        has_items=True,
        prepayment_application_remaining=Decimal("5000"),
    )
    assert caps.push_payment_application.allowed is True


def test_push_prepayment_allowed_without_prepayment_amount():
    order = SimpleNamespace(
        status="CONFIRMED",
        review_status="APPROVED",
        supplier_id=1,
        prepayment_amount=Decimal("0"),
        total_amount=Decimal("1000"),
        net_amount=Decimal("1000"),
    )
    caps = derive_purchase_order_capabilities(
        order,
        has_items=True,
        has_prepayment_payment=False,
        require_payment_application=False,
    )
    assert caps.push_prepayment.allowed is True


def test_payment_reason_for_purchase_orders_single_and_multi():
    assert _payment_reason_for_purchase_orders(["CGDD202611190001"]) == (
        "采购订单 CGDD202611190001 预付请款"
    )
    assert _payment_reason_for_purchase_orders(["A", "B"]) == "采购订单 A、B 预付请款"


def test_payment_reason_for_purchase_receipts_single():
    assert _payment_reason_for_purchase_receipts(["CGSD202611120001"]) == (
        "采购入库单 CGSD202611120001 货款请款"
    )


def test_push_payment_application_denied_when_remaining_zero():
    order = SimpleNamespace(
        status="CONFIRMED",
        review_status="APPROVED",
        supplier_id=1,
        prepayment_amount=Decimal("0"),
        total_amount=Decimal("5000"),
    )
    caps = derive_purchase_order_capabilities(
        order,
        has_items=True,
        prepayment_application_remaining=Decimal("0"),
    )
    assert caps.push_payment_application.allowed is False
    assert caps.push_payment_application.reason == "purchase_order.push_payment_application.no_amount"


@pytest.mark.asyncio
async def test_preview_max_push_without_prepayment_uses_order_gross():
    order = SimpleNamespace(
        id=1,
        order_code="PO001",
        supplier_id=10,
        supplier_name="供应商A",
        prepayment_amount=Decimal("0"),
        total_amount=Decimal("1000"),
        net_amount=Decimal("1130"),
        tax_rate=Decimal("0.13"),
        status="CONFIRMED",
    )
    svc = PaymentApplicationPullService()
    with patch(
        "apps.kuaizhizao.models.purchase_order.PurchaseOrder.get_or_none",
        new=AsyncMock(return_value=order),
    ), patch(
        "apps.kuaizhizao.services.payment_application_pull_service._order_prepayment_linked_by_ids",
        new=AsyncMock(return_value={1: False}),
    ), patch.object(
        svc,
        "_sum_prepayment_application_reserved",
        new=AsyncMock(return_value=Decimal("310")),
    ), patch.object(
        svc,
        "prepayment_payment_occupied_by_order_ids",
        new=AsyncMock(return_value={1: Decimal("0")}),
    ), patch(
        "infra.services.business_config_service.BusinessConfigService.get_finance_require_payment_application",
        new=AsyncMock(return_value=True),
    ):
        preview = await svc.preview_from_purchase_order(1, 1)

    assert preview["has_blocking_issues"] is False
    assert preview["max_push_quantity"] == 820.0
