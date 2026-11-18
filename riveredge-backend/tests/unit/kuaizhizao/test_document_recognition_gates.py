"""单据头立账策略门控（以单据字段为准）。"""

from types import SimpleNamespace

import pytest

from apps.kuaizhizao.services.document_recognition import (
    coerce_payable_recognition,
    coerce_revenue_recognition,
    describe_sales_delivery_receivable_auto_skip,
    resolve_payable_for_downstream,
    resolve_revenue_for_downstream,
    should_auto_payable_on_purchase_receipt,
    should_auto_receivable_on_sales_delivery,
    should_auto_receivable_on_sales_invoice,
    should_auto_receivable_on_misc_voucher_approve,
)


def test_coerce_revenue_whitelist():
    assert coerce_revenue_recognition("on_partner_statement") == "on_partner_statement"
    assert coerce_revenue_recognition("invalid") == "on_shipment"


def test_delivery_gate_uses_doc_strategy_not_partner():
    assert should_auto_receivable_on_sales_delivery("on_shipment") is True
    assert should_auto_receivable_on_sales_delivery("on_partner_statement") is False
    assert should_auto_receivable_on_sales_delivery("manual") is False
    assert should_auto_receivable_on_sales_delivery("on_invoice") is False


def test_sales_invoice_gate_on_invoice_only():
    assert should_auto_receivable_on_sales_invoice("on_invoice") is True
    assert should_auto_receivable_on_sales_invoice("on_shipment") is False
    assert should_auto_receivable_on_sales_invoice("on_partner_statement") is False


def test_describe_sales_delivery_skip_for_non_shipment_strategies():
    assert "销售发票" in (describe_sales_delivery_receivable_auto_skip("on_invoice") or "")
    assert describe_sales_delivery_receivable_auto_skip("on_shipment") is None


def test_purchase_receipt_gate_on_receipt_only():
    assert should_auto_payable_on_purchase_receipt("on_receipt") is True
    assert should_auto_payable_on_purchase_receipt("on_partner_statement") is False


def test_misc_voucher_skips_manual_and_statement():
    assert should_auto_receivable_on_misc_voucher_approve("on_shipment") is True
    assert should_auto_receivable_on_misc_voucher_approve("manual") is False
    assert should_auto_receivable_on_misc_voucher_approve("on_partner_statement") is False


@pytest.mark.asyncio
async def test_downstream_copies_upstream_manual_value():
    upstream = SimpleNamespace(revenue_recognition="on_partner_statement")
    resolved = await resolve_revenue_for_downstream(
        1,
        99,
        upstream=upstream,
        provided=None,
    )
    assert resolved == "on_partner_statement"


@pytest.mark.asyncio
async def test_downstream_provided_overrides_upstream():
    upstream = SimpleNamespace(payable_recognition="on_receipt")
    resolved = await resolve_payable_for_downstream(
        1,
        88,
        upstream=upstream,
        provided="manual",
    )
    assert resolved == "manual"
