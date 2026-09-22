"""物料超收/超发容差解析单元测试。"""

from decimal import Decimal

from apps.kuaizhizao.utils.over_qty_tolerance import (
    max_allowed,
    max_remaining_after_tolerance,
    _optional_pct,
)


def test_max_allowed_zero_base():
    assert max_allowed(Decimal("0"), Decimal("5")) == Decimal("0")


def test_max_allowed_applies_pct():
    assert max_allowed(Decimal("100"), Decimal("0")) == Decimal("100")
    assert max_allowed(Decimal("100"), Decimal("5")) == Decimal("105")


def test_max_remaining_after_tolerance():
    assert max_remaining_after_tolerance(
        Decimal("100"), Decimal("95"), Decimal("5")
    ) == Decimal("10")
    assert max_remaining_after_tolerance(
        Decimal("100"), Decimal("105"), Decimal("5")
    ) == Decimal("0")


def test_max_remaining_zero_tolerance_matches_strict_outstanding():
    assert max_remaining_after_tolerance(
        Decimal("100"), Decimal("80"), Decimal("0")
    ) == Decimal("20")


def test_optional_pct_clamps_and_null():
    assert _optional_pct(None) is None
    assert _optional_pct(Decimal("-1")) == Decimal("0")
    assert _optional_pct(Decimal("150")) == Decimal("100")
    assert _optional_pct(Decimal("3.5")) == Decimal("3.5")
