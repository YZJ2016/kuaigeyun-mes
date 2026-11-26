"""采购入库显式 0% 税率回归测试。"""

from decimal import Decimal
from types import SimpleNamespace

from apps.kuaicaiwu.services.purchase_settlement import (
    _rollup_receipt_header_tax_percent,
    resolve_purchase_line_tax_rate_percent,
    resolve_receipt_line_tax_rate_percent,
)
from apps.kuaizhizao.services.warehouse_service import (
    _purchase_receipt_persisted_line_tax_rate,
)


def test_purchase_receipt_persists_explicit_zero_tax_rate():
    assert _purchase_receipt_persisted_line_tax_rate(Decimal("0")) == 0.0
    assert _purchase_receipt_persisted_line_tax_rate(Decimal("13")) == 13.0
    assert _purchase_receipt_persisted_line_tax_rate(None) is None


def test_resolve_purchase_line_tax_rate_keeps_explicit_zero():
    assert resolve_purchase_line_tax_rate_percent(line_tax_rate=0, header_tax_rate=13) == Decimal("0")
    assert resolve_purchase_line_tax_rate_percent(line_tax_rate=None, header_tax_rate=13) == Decimal("13")


def test_resolve_receipt_line_tax_rate_keeps_explicit_zero_on_line():
    receipt = SimpleNamespace(tax_rate=Decimal("13"))
    line = SimpleNamespace(tax_rate=Decimal("0"), purchase_order_item_id=None)
    assert resolve_receipt_line_tax_rate_percent(receipt=receipt, purchase_order_item_id=None, poi_by_id={}, receipt_line=line) == Decimal("0")


def test_rollup_receipt_header_tax_all_zero():
    lines = [
        SimpleNamespace(tax_rate=Decimal("0")),
        SimpleNamespace(tax_rate=Decimal("0")),
    ]
    assert _rollup_receipt_header_tax_percent(lines) == Decimal("0")
