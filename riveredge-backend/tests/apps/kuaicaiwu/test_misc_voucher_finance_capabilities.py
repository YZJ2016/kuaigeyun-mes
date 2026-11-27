"""其他费用收支 capabilities 与挂账门禁（纯单元）。

状态契约：业务 status 仅 Draft/Confirmed/Cancelled；审核态由 review_status 承载
（已审核=approved）。确认过账要求供应商/客户往来已生成挂账（应付/应收）。
"""

from types import SimpleNamespace

from apps.kuaicaiwu.services.document_action_policy.other_income import (
    derive_other_income_capabilities,
)
from apps.kuaicaiwu.services.document_action_policy.other_expense import (
    derive_other_expense_capabilities,
)


def test_other_income_confirm_requires_receivable_and_bank():
    row = SimpleNamespace(
        status="Draft",
        review_status="已审核",
        counterparty_kind="customer",
        bank_account_id=1,
    )
    caps_no_ar = derive_other_income_capabilities(row, has_receivable=False, has_receipt=False)
    assert caps_no_ar["confirm"].allowed is False
    assert caps_no_ar["confirm"].reason == "other_income.confirm.no_receivable"

    caps_ok = derive_other_income_capabilities(row, has_receivable=True, has_receipt=False)
    assert caps_ok["confirm"].allowed is True
    assert caps_ok["push_receipt"].allowed is True


def test_other_income_confirm_requires_customer_counterparty():
    row = SimpleNamespace(
        status="Draft",
        review_status="已审核",
        counterparty_kind="other",
        bank_account_id=1,
    )
    caps = derive_other_income_capabilities(row, has_receivable=True, has_receipt=False)
    assert caps["confirm"].allowed is False
    assert caps["confirm"].reason == "other_income.confirm.need_customer"


def test_other_income_pending_review_disables_submit_and_edit():
    row = SimpleNamespace(
        status="Draft",
        review_status="待审核",
        counterparty_kind="customer",
        bank_account_id=1,
    )
    caps = derive_other_income_capabilities(row)
    assert caps["submit"].allowed is False
    assert caps["update"].allowed is False
    assert caps["delete"].allowed is False
    assert caps["approve"].allowed is True


def test_other_expense_confirm_requires_supplier_payable():
    row = SimpleNamespace(
        status="Draft",
        review_status="已审核",
        counterparty_kind="supplier",
        bank_account_id=2,
    )
    caps = derive_other_expense_capabilities(row, has_payable=True, has_payment=False)
    assert caps["push_payment"].allowed is True
    assert caps["confirm"].allowed is True


def test_other_expense_confirm_blocked_without_payable():
    row = SimpleNamespace(
        status="Draft",
        review_status="已审核",
        counterparty_kind="supplier",
        bank_account_id=2,
    )
    caps = derive_other_expense_capabilities(row, has_payable=False, has_payment=False)
    assert caps["confirm"].allowed is False
    assert caps["confirm"].reason == "other_expense.confirm.no_payable"

    non_supplier = SimpleNamespace(
        status="Draft",
        review_status="已审核",
        counterparty_kind="other",
        bank_account_id=2,
    )
    caps2 = derive_other_expense_capabilities(non_supplier, has_payable=True, has_payment=False)
    assert caps2["confirm"].allowed is False
    assert caps2["confirm"].reason == "other_expense.confirm.need_supplier"


def test_confirmed_voucher_can_only_unconfirm_or_cancel():
    row = SimpleNamespace(
        status="Confirmed",
        review_status="已审核",
        counterparty_kind="supplier",
        bank_account_id=1,
    )
    caps = derive_other_expense_capabilities(row, has_payable=True, has_payment=True)
    assert caps["unconfirm"].allowed is True
    assert caps["cancel"].allowed is True
    assert caps["update"].allowed is False
    assert caps["confirm"].allowed is False
