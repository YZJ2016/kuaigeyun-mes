"""其他收支确认过账守卫：审核态门禁、银行余额、过账/反过账联动。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.kuaicaiwu.services import misc_voucher_posting_service as posting_module
from apps.kuaicaiwu.services.misc_voucher_posting_service import (
    MiscVoucherPostingService,
)
from infra.exceptions.exceptions import ValidationError


@pytest.mark.asyncio
async def test_post_income_rejects_unapproved_status(monkeypatch):
    head = SimpleNamespace(
        id=1,
        status="Draft",
        review_status="待审核",
        bank_account_id=None,
    )
    monkeypatch.setattr(
        posting_module.OtherIncome, "get_or_none", AsyncMock(return_value=head)
    )
    monkeypatch.setattr(
        posting_module, "assert_other_income_capability", lambda *a, **k: None
    )
    with pytest.raises(ValidationError, match="仅已审核"):
        await MiscVoucherPostingService().post_other_income(
            8, 1, operator=SimpleNamespace(id=1)
        )


@pytest.mark.asyncio
async def test_post_expense_blocks_when_bank_balance_insufficient(monkeypatch):
    head = SimpleNamespace(
        id=7,
        status="Draft",
        review_status="已审核",
        payment_method="银行转账",
        bank_account_id=1,
        total_amount=Decimal("9000"),
    )
    monkeypatch.setattr(
        posting_module.OtherExpense, "get_or_none", AsyncMock(return_value=head)
    )
    monkeypatch.setattr(
        posting_module, "assert_other_expense_capability", lambda *a, **k: None
    )
    bank_svc = MagicMock()
    bank_svc.validate_voucher_account = AsyncMock()
    bank_svc.assert_out_funds = AsyncMock(
        side_effect=ValidationError("账户 1002 余额不足，当前 0，本次出款 9000")
    )
    monkeypatch.setattr(posting_module, "BankAccountService", lambda: bank_svc)
    update = AsyncMock()
    monkeypatch.setattr(
        posting_module.OtherExpense, "filter", lambda **kw: MagicMock(update=update)
    )

    with pytest.raises(ValidationError, match="余额不足"):
        await MiscVoucherPostingService().post_other_expense(
            8, 7, operator=SimpleNamespace(id=1)
        )

    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_income_creates_receipt_and_confirms(monkeypatch):
    head = SimpleNamespace(
        id=3,
        status="Draft",
        review_status="已审核",
        payment_method="现金",
        bank_account_id=2,
        bank_account=None,
        total_amount=Decimal("100"),
        income_code="OI-1",
        business_date=None,
    )
    confirmed = SimpleNamespace(**{**head.__dict__, "status": "Confirmed"})
    monkeypatch.setattr(
        posting_module.OtherIncome,
        "get_or_none",
        AsyncMock(side_effect=[head, confirmed]),
    )
    monkeypatch.setattr(
        posting_module, "assert_other_income_capability", lambda *a, **k: None
    )
    bank_svc = MagicMock()
    bank_svc.validate_voucher_account = AsyncMock()
    monkeypatch.setattr(posting_module, "BankAccountService", lambda: bank_svc)
    bridge = MagicMock()
    bridge.get_receivable_for_income = AsyncMock(return_value=SimpleNamespace(id=5))
    bridge.finance_links_for_income = AsyncMock(return_value={})
    bridge.link_income_receipt = AsyncMock()
    monkeypatch.setattr(posting_module, "MiscVoucherFinanceBridge", lambda: bridge)
    create_receipt = AsyncMock(return_value=9)
    monkeypatch.setattr(
        posting_module, "create_concurrent_receipt_for_receivable", create_receipt
    )
    monkeypatch.setattr(
        posting_module.Receipt,
        "get",
        AsyncMock(return_value=SimpleNamespace(receipt_code="SK-1")),
    )
    update = AsyncMock()
    monkeypatch.setattr(
        posting_module.OtherIncome, "filter", lambda **kw: MagicMock(update=update)
    )

    result = await MiscVoucherPostingService().post_other_income(
        8, 3, operator=SimpleNamespace(id=1)
    )

    create_receipt.assert_awaited_once()
    bridge.link_income_receipt.assert_awaited_once()
    update.assert_awaited_once()
    assert result is confirmed


@pytest.mark.asyncio
async def test_unpost_expense_reverts_payment_back_to_draft(monkeypatch):
    head = SimpleNamespace(
        id=4,
        status="Confirmed",
        review_status="已审核",
        expense_code="OE-1",
    )
    reverted = SimpleNamespace(**{**head.__dict__, "status": "Draft"})
    monkeypatch.setattr(
        posting_module.OtherExpense,
        "get_or_none",
        AsyncMock(side_effect=[head, reverted]),
    )
    bridge = MagicMock()
    bridge.finance_links_for_expense = AsyncMock(return_value={"payment_id": 3})
    monkeypatch.setattr(posting_module, "MiscVoucherFinanceBridge", lambda: bridge)
    monkeypatch.setattr(
        posting_module.Payment,
        "get_or_none",
        AsyncMock(return_value=SimpleNamespace(id=3, status="Confirmed")),
    )
    monkeypatch.setattr(
        posting_module, "assert_voucher_correction_allowed", lambda *a, **k: None
    )
    unpost = AsyncMock()
    monkeypatch.setattr(posting_module, "apply_confirmed_voucher_unpost", unpost)
    user = SimpleNamespace(id=1)
    monkeypatch.setattr(
        posting_module.User,
        "filter",
        lambda **kw: MagicMock(first=AsyncMock(return_value=user)),
    )
    payment_update = AsyncMock()
    monkeypatch.setattr(
        posting_module.Payment,
        "filter",
        lambda **kw: MagicMock(update=payment_update),
    )
    expense_update = AsyncMock()
    monkeypatch.setattr(
        posting_module.OtherExpense,
        "filter",
        lambda **kw: MagicMock(update=expense_update),
    )

    result = await MiscVoucherPostingService().unpost_other_expense(
        8, 4, operator_id=1
    )

    unpost.assert_awaited_once()
    payment_update.assert_awaited_once()
    expense_update.assert_awaited_once()
    assert result is reverted
