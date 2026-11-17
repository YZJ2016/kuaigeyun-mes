"""付款申请发票情况校验"""

import pytest

from apps.kuaizhizao.services.payment_application_service import PaymentApplicationService
from infra.exceptions.exceptions import ValidationError


def test_coerce_invoice_status_default() -> None:
    assert PaymentApplicationService._coerce_invoice_status(None, allow_default=True) == "无发票"


def test_coerce_invoice_status_required() -> None:
    with pytest.raises(ValidationError):
        PaymentApplicationService._coerce_invoice_status("", allow_default=False)


def test_coerce_invoice_status_valid() -> None:
    assert PaymentApplicationService._coerce_invoice_status("有发票", allow_default=False) == "有发票"
