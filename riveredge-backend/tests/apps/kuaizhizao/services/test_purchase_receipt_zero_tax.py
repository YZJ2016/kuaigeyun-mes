"""采购入库显式 0% 税率回归测试。"""

from decimal import Decimal

from apps.kuaizhizao.services.warehouse_service import (
    _purchase_receipt_persisted_line_tax_rate,
)


def test_purchase_receipt_persists_explicit_zero_tax_rate():
    assert _purchase_receipt_persisted_line_tax_rate(Decimal("0")) == 0.0
    assert _purchase_receipt_persisted_line_tax_rate(Decimal("13")) == 13.0
    assert _purchase_receipt_persisted_line_tax_rate(None) is None
