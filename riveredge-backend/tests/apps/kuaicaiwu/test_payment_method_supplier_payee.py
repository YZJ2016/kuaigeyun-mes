"""供应商收款账户校验：未选付款方式时不拦截草稿/取单建单。"""

import pytest

from apps.kuaicaiwu.constants.payment_method import (
    BANK_TRANSFER_PAYMENT_METHOD,
    assert_supplier_payee_account,
    requires_supplier_payee_account,
)
from infra.exceptions.exceptions import ValidationError


def test_requires_supplier_payee_account_false_when_method_empty():
    assert requires_supplier_payee_account(None) is False
    assert requires_supplier_payee_account("") is False


def test_requires_supplier_payee_account_true_for_bank_transfer():
    assert requires_supplier_payee_account(BANK_TRANSFER_PAYMENT_METHOD) is True


def test_assert_supplier_payee_account_skips_when_method_empty():
    assert_supplier_payee_account(
        payment_method=None,
        account_name=None,
        bank_name=None,
        bank_account=None,
    ) is None


def test_assert_supplier_payee_account_raises_when_transfer_incomplete():
    with pytest.raises(ValidationError):
        assert_supplier_payee_account(
            payment_method=BANK_TRANSFER_PAYMENT_METHOD,
            account_name="甲",
            bank_name=None,
            bank_account=None,
        )