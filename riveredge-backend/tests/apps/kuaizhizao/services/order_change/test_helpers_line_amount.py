from decimal import Decimal

from apps.kuaizhizao.services.order_change.helpers import line_amount


def test_line_amount_uses_business_precision():
    assert line_amount("3", "0.195") == Decimal("0.59")
