"""客户联系方式必填规则：无联系人时不强制手机/邮箱。"""

import pytest

from apps.master_data.services.supply_chain_service import _assert_customer_phone_or_email
from infra.exceptions.exceptions import ValidationError


def test_assert_skips_when_no_contact_identity():
    _assert_customer_phone_or_email({"code": "001", "name": "客户甲"})


def test_assert_passes_with_phone_only():
    _assert_customer_phone_or_email({"phone": "13800138000"})


def test_assert_requires_channel_when_contact_person_set():
    with pytest.raises(ValidationError, match="手机号与邮箱"):
        _assert_customer_phone_or_email({"contact_person": "张三"})


def test_assert_passes_when_contact_has_email():
    _assert_customer_phone_or_email(
        {"contacts": [{"contact_person": "李四", "email": "a@b.com"}]}
    )
