from decimal import Decimal

from apps.kuaizhizao.utils.document_amount_write import (
    allocate_amount_by_weights,
    line_total_qty_unit_price,
    resolve_simple_line_total,
)


def test_line_total_qty_unit_price_basic():
    assert line_total_qty_unit_price(3, "0.195") == Decimal("0.59")


def test_resolve_simple_line_total_prefers_computed_when_given_zero():
    assert resolve_simple_line_total(2, 10, 0) == Decimal("20.00")


def test_allocate_amount_by_weights_tail_absorbs_rounding():
    parts = allocate_amount_by_weights("100", [1, 1, 1])
    assert sum(parts) == Decimal("100.00")
    assert len(parts) == 3


def test_allocate_amount_by_weights_proportional():
    parts = allocate_amount_by_weights("10", [30, 70])
    assert sum(parts) == Decimal("10.00")
    assert parts[0] == Decimal("3.00")
    assert parts[1] == Decimal("7.00")
