"""收付款单过账：余额不足时不得先改确认状态。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.kuaicaiwu.services import finance_voucher_posting_service as module


@pytest.mark.asyncio
async def test_post_payment_keeps_draft_when_bank_balance_insufficient(monkeypatch):
    payment = SimpleNamespace(
        id=36,
        status="Draft",
        payment_method="银行转账",
        bank_account_id=1,
        settlement_type="normal",
        total_amount=Decimal("50000"),
    )

    monkeypatch.setattr(module.Payment, "get_or_none", AsyncMock(return_value=payment))
    bank_svc = MagicMock()
    bank_svc.validate_voucher_account = AsyncMock()
    bank_svc.get_by_id = AsyncMock(
        return_value=SimpleNamespace(account_code="1", current_balance=Decimal("0"))
    )
    bank_svc.sync_from_confirmed_voucher = AsyncMock()
    bank_svc.reverse_from_voucher = AsyncMock(return_value=0)
    monkeypatch.setattr(module, "BankAccountService", lambda: bank_svc)

    update = AsyncMock()
    monkeypatch.setattr(module.Payment, "filter", lambda **kw: MagicMock(update=update))
    settle = AsyncMock()
    monkeypatch.setattr(
        module,
        "PaymentPullService",
        lambda: SimpleNamespace(settle_draft_payment_if_linked=settle),
    )

    with pytest.raises(module.ValidationError, match="余额不足"):
        await module.FinanceVoucherPostingService().post_payment(
            8, 36, operator=SimpleNamespace(id=42)
        )

    settle.assert_not_awaited()
    bank_svc.sync_from_confirmed_voucher.assert_not_awaited()
    update.assert_not_awaited()
