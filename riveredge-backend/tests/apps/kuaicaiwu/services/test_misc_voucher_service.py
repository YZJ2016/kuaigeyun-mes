"""其他费用收入/支出服务：状态机、能力矩阵与过账边界。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.kuaicaiwu.services import misc_voucher_posting_service as posting_module
from apps.kuaicaiwu.services import misc_voucher_service as module
from apps.kuaicaiwu.services.misc_voucher_service import (
    EXPENSE_SPEC,
    INCOME_SPEC,
    MiscVoucherService,
)
from infra.exceptions.exceptions import BusinessLogicError, ValidationError


def _svc():
    return MiscVoucherService(INCOME_SPEC)


@pytest.mark.parametrize(
    "status,expected",
    [
        ("Draft", {"update": True, "submit": True, "approve": False, "confirm": True, "unconfirm": False, "cancel": True, "delete": True}),
        ("PendingReview", {"update": False, "submit": False, "approve": True, "reject": True, "confirm": False, "cancel": False}),
        ("Approved", {"update": False, "submit": False, "confirm": True, "unconfirm": False, "cancel": True, "delete": False}),
        ("Rejected", {"update": True, "submit": True, "confirm": False, "delete": True, "cancel": True}),
        ("Confirmed", {"update": False, "submit": False, "confirm": False, "unconfirm": True, "cancel": True, "delete": False}),
        ("Cancelled", {"update": False, "confirm": False, "unconfirm": False, "cancel": False, "delete": True}),
    ],
)
def test_capabilities_by_status(status, expected):
    doc = SimpleNamespace(status=status)
    caps = _svc().capabilities(doc, audit_required=False)
    for action, allowed in expected.items():
        assert caps[action]["allowed"] is allowed, (status, action, caps)


def test_capabilities_confirm_blocked_for_draft_when_audit_required():
    doc = SimpleNamespace(status="Draft")
    caps = _svc().capabilities(doc, audit_required=True)
    assert caps["confirm"]["allowed"] is False
    assert caps["submit"]["allowed"] is True


@pytest.mark.parametrize(
    "kind,cid,cname,ok",
    [
        ("none", None, None, True),
        ("customer", 5, "客户A", True),
        ("customer", None, None, False),
        ("supplier", None, None, False),
        ("employee", None, None, False),
        ("other", None, "某单位", True),
        ("other", None, None, False),
        ("weird", None, None, False),
    ],
)
def test_counterparty_validation(kind, cid, cname, ok):
    data = {
        "counterparty_kind": kind,
        "counterparty_id": cid,
        "counterparty_name": cname,
    }
    if ok:
        MiscVoucherService._assert_counterparty_dict(data)
    else:
        with pytest.raises(ValidationError):
            MiscVoucherService._assert_counterparty_dict(data)


def test_specs_bind_correct_models():
    from apps.kuaicaiwu.models.other_voucher import (
        OtherExpense,
        OtherExpenseLine,
        OtherIncome,
        OtherIncomeLine,
    )
    from apps.kuaicaiwu.models.finance_misc_category import (
        MiscExpenseCategory,
        MiscIncomeCategory,
    )

    assert INCOME_SPEC.model is OtherIncome
    assert INCOME_SPEC.line_model is OtherIncomeLine
    assert INCOME_SPEC.category_model is MiscIncomeCategory
    assert INCOME_SPEC.code_field == "income_code"
    assert EXPENSE_SPEC.model is OtherExpense
    assert EXPENSE_SPEC.line_model is OtherExpenseLine
    assert EXPENSE_SPEC.category_model is MiscExpenseCategory
    assert EXPENSE_SPEC.code_field == "expense_code"


@pytest.mark.asyncio
async def test_post_expense_blocks_when_bank_balance_insufficient(monkeypatch):
    expense = SimpleNamespace(
        id=7,
        status="Approved",
        payment_method="银行转账",
        bank_account_id=1,
        total_amount=Decimal("9000"),
    )
    monkeypatch.setattr(
        posting_module.OtherExpense, "get_or_none", AsyncMock(return_value=expense)
    )
    bank_svc = MagicMock()
    bank_svc.validate_voucher_account = AsyncMock()
    bank_svc.get_by_id = AsyncMock(
        return_value=SimpleNamespace(account_code="1002", current_balance=Decimal("0"))
    )
    bank_svc.sync_from_confirmed_voucher = AsyncMock()
    bank_svc.reverse_from_voucher = AsyncMock(return_value=0)
    monkeypatch.setattr(posting_module, "BankAccountService", lambda: bank_svc)
    update = AsyncMock()
    monkeypatch.setattr(
        posting_module.OtherExpense,
        "filter",
        lambda **kw: MagicMock(update=update),
    )

    with pytest.raises(ValidationError, match="余额不足"):
        await posting_module.MiscVoucherPostingService().post(
            8, voucher_type="other_expense", voucher_id=7, operator=SimpleNamespace(id=1)
        )

    bank_svc.sync_from_confirmed_voucher.assert_not_awaited()
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_income_writes_bank_flow_and_confirms(monkeypatch):
    income = SimpleNamespace(
        id=3,
        status="Approved",
        payment_method="现金",
        bank_account_id=2,
        total_amount=Decimal("100"),
    )
    confirmed = SimpleNamespace(**{**income.__dict__, "status": "Confirmed"})
    monkeypatch.setattr(
        posting_module.OtherIncome,
        "get_or_none",
        AsyncMock(side_effect=[income, confirmed]),
    )
    bank_svc = MagicMock()
    bank_svc.validate_voucher_account = AsyncMock()
    bank_svc.sync_from_confirmed_voucher = AsyncMock()
    monkeypatch.setattr(posting_module, "BankAccountService", lambda: bank_svc)
    update = AsyncMock()
    monkeypatch.setattr(
        posting_module.OtherIncome, "filter", lambda **kw: MagicMock(update=update)
    )

    result = await posting_module.MiscVoucherPostingService().post(
        8, voucher_type="other_income", voucher_id=3, operator=SimpleNamespace(id=1)
    )

    bank_svc.sync_from_confirmed_voucher.assert_awaited_once()
    assert bank_svc.sync_from_confirmed_voucher.await_args.kwargs["voucher_type"] == "other_income"
    update.assert_awaited_once()
    assert result is confirmed


@pytest.mark.asyncio
async def test_post_rejects_unapproved_status(monkeypatch):
    doc = SimpleNamespace(id=1, status="Draft", bank_account_id=None)
    monkeypatch.setattr(
        posting_module.OtherIncome, "get_or_none", AsyncMock(return_value=doc)
    )
    with pytest.raises(ValidationError, match="已审核"):
        await posting_module.MiscVoucherPostingService().post(
            8, voucher_type="other_income", voucher_id=1, operator=SimpleNamespace(id=1)
        )


@pytest.mark.asyncio
async def test_unpost_reverses_bank_flow_back_to_approved(monkeypatch):
    doc = SimpleNamespace(id=4, status="Confirmed")
    reverted = SimpleNamespace(id=4, status="Approved")
    monkeypatch.setattr(
        posting_module.OtherExpense,
        "get_or_none",
        AsyncMock(side_effect=[doc, reverted]),
    )
    bank_svc = MagicMock()
    bank_svc.reverse_from_voucher = AsyncMock(return_value=1)
    monkeypatch.setattr(posting_module, "BankAccountService", lambda: bank_svc)
    update = AsyncMock()
    monkeypatch.setattr(
        posting_module.OtherExpense, "filter", lambda **kw: MagicMock(update=update)
    )

    result = await posting_module.MiscVoucherPostingService().unpost(
        8, voucher_type="other_expense", voucher_id=4, operator=SimpleNamespace(id=1)
    )

    bank_svc.reverse_from_voucher.assert_awaited_once()
    update.assert_awaited_once()
    assert update.await_args.kwargs["status"] == "Approved"
    assert result is reverted


@pytest.mark.asyncio
async def test_cancel_blocks_pending_review(monkeypatch):
    svc = _svc()
    doc = SimpleNamespace(id=9, status="PendingReview")
    monkeypatch.setattr(svc, "get_or_404", AsyncMock(return_value=doc))
    with pytest.raises(BusinessLogicError, match="待审核"):
        await svc.cancel(8, 9, SimpleNamespace(id=1))


@pytest.mark.asyncio
async def test_delete_blocks_confirmed(monkeypatch):
    svc = _svc()
    doc = SimpleNamespace(id=9, status="Confirmed")
    monkeypatch.setattr(svc, "get_or_404", AsyncMock(return_value=doc))
    with pytest.raises(BusinessLogicError, match="可删除"):
        await svc.delete(8, 9)


@pytest.mark.asyncio
async def test_resolve_lines_unknown_category_raises(monkeypatch):
    svc = _svc()
    qs = MagicMock()
    qs.all = AsyncMock(return_value=[])
    monkeypatch.setattr(
        INCOME_SPEC.category_model, "filter", lambda **kw: qs
    )
    line = SimpleNamespace(category_code="NOPE", amount=Decimal("5"))
    with pytest.raises(ValidationError, match="收支类别不存在"):
        await svc._resolve_lines(8, [line])
