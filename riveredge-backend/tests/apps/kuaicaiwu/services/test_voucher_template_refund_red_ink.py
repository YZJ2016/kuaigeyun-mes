"""收/付款退款凭证模板：红字冲销（同向负金额），禁止相反分录。"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from apps.kuaicaiwu.services.voucher_template_service import VoucherTemplateService


def test_refund_templates_match_forward_sides():
    svc = VoucherTemplateService()
    receipt = svc.DEFAULT_TEMPLATES["receipt_confirmed"]
    receipt_refund = svc.DEFAULT_TEMPLATES["receipt_refund"]
    assert [(r["side"], r["account_code"]) for r in receipt] == [
        (r["side"], r["account_code"]) for r in receipt_refund
    ]

    payment = svc.DEFAULT_TEMPLATES["payment_confirmed"]
    payment_refund = svc.DEFAULT_TEMPLATES["payment_refund"]
    assert [(r["side"], r["account_code"]) for r in payment] == [
        (r["side"], r["account_code"]) for r in payment_refund
    ]
    assert "payment_refund" in svc.RED_INK_TEMPLATE_KEYS
    assert "receipt_refund" in svc.RED_INK_TEMPLATE_KEYS


def test_build_draft_lines_payment_refund_red_ink():
    svc = VoucherTemplateService()
    event = MagicMock()
    event.event_type = "PAYMENT_REFUND_CONFIRMED"
    event.business_type = "payment_refund"
    event.notes = "付款退款 TP202609120002 确认"
    event.amount = Decimal("78.38")
    event.payload = {"supplier_id": 5, "supplier_name": "东风5c"}

    bank = MagicMock(id=1, account_code="1002", account_name="银行存款")
    ap = MagicMock(id=2, account_code="2202", account_name="应付账款")
    for account in (bank, ap):
        account.aux_customer = False
        account.aux_supplier = account.account_code == "2202"
        account.aux_department = False
        account.is_cash_journal = False
        account.is_bank_journal = account.account_code == "1002"

    async def resolve_side_effect(_tenant_id, code):
        if code == "1002":
            return bank
        if code == "2202":
            return ap
        return None

    svc._resolve_account = AsyncMock(side_effect=resolve_side_effect)
    svc._resolve_partner_from_event = AsyncMock(
        return_value={"supplier_id": 5, "supplier_name": "东风5c"}
    )

    with patch(
        "apps.kuaicaiwu.services.gl.cash_flow_classify.resolve_cash_flow_item_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        lines = asyncio.run(svc.build_draft_lines_from_event(1, event))
    assert len(lines) == 2
    assert lines[0]["account_code"] == "2202"
    assert lines[0]["debit_amount"] == Decimal("-78.38")
    assert lines[0]["credit_amount"] == Decimal("0")
    assert lines[1]["account_code"] == "1002"
    assert lines[1]["credit_amount"] == Decimal("-78.38")
    assert lines[1]["debit_amount"] == Decimal("0")


def test_build_draft_lines_receipt_refund_red_ink():
    svc = VoucherTemplateService()
    event = MagicMock()
    event.event_type = "RECEIPT_REFUND_CONFIRMED"
    event.business_type = "receipt_refund"
    event.notes = "收款退款确认"
    event.amount = Decimal("100")
    event.payload = {"customer_id": 9, "customer_name": "客户A"}

    bank = MagicMock(id=1, account_code="1002", account_name="银行存款")
    ar = MagicMock(id=2, account_code="1122", account_name="应收账款")
    for account in (bank, ar):
        account.aux_customer = account.account_code == "1122"
        account.aux_supplier = False
        account.aux_department = False
        account.is_cash_journal = False
        account.is_bank_journal = account.account_code == "1002"

    async def resolve_side_effect(_tenant_id, code):
        if code == "1002":
            return bank
        if code == "1122":
            return ar
        return None

    svc._resolve_account = AsyncMock(side_effect=resolve_side_effect)
    svc._resolve_partner_from_event = AsyncMock(
        return_value={"customer_id": 9, "customer_name": "客户A"}
    )

    with patch(
        "apps.kuaicaiwu.services.gl.cash_flow_classify.resolve_cash_flow_item_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        lines = asyncio.run(svc.build_draft_lines_from_event(1, event))
    assert len(lines) == 2
    assert lines[0]["account_code"] == "1002"
    assert lines[0]["debit_amount"] == Decimal("-100")
    assert lines[1]["account_code"] == "1122"
    assert lines[1]["credit_amount"] == Decimal("-100")
