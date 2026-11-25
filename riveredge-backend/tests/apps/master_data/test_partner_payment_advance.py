import pytest

from apps.master_data.config.partner_payment_advance import normalize_partner_payment_advance_payee


def test_employee_advance_requires_payee():
    with pytest.raises(ValueError, match="领款人"):
        normalize_partner_payment_advance_payee("employee_advance", None, None)


def test_non_advance_clears_payee():
    pid, pname = normalize_partner_payment_advance_payee("bank_transfer", None, None)
    assert pid is None and pname is None

    with pytest.raises(ValueError, match="非员工垫付"):
        normalize_partner_payment_advance_payee("bank_transfer", 1, "张三")