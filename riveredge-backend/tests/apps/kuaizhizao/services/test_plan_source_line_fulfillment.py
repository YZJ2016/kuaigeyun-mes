"""计划/销售开口行占用分摊（单元级，无库）。"""

from decimal import Decimal

from apps.kuaizhizao.services.plan_source_line_fulfillment import (
    _allocate_material_pool_across_lines,
    _dec,
)


class _Line:
    def __init__(self, line_id: int, material_id: int, qty):
        self.id = line_id
        self.material_id = material_id
        self.order_quantity = qty
        self.required_quantity = qty


def test_dec_parses_numeric_strings():
    assert _dec("10.5") == Decimal("10.5")
    assert _dec(None) == Decimal("0")


def test_allocate_material_pool_respects_line_order():
    lines = [
        _Line(1, 100, 30),
        _Line(2, 100, 20),
    ]
    pool = {100: Decimal("35")}
    alloc = _allocate_material_pool_across_lines(lines, pool, "order_quantity")
    assert alloc[1] == Decimal("30")
    assert alloc[2] == Decimal("5")


def test_allocate_material_pool_zero_when_pool_empty():
    lines = [_Line(1, 200, 10)]
    alloc = _allocate_material_pool_across_lines(lines, {}, "order_quantity")
    assert alloc.get(1, Decimal("0")) == Decimal("0")