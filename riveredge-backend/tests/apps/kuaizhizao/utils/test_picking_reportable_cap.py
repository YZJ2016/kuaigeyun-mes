"""正式领料可支撑报工量：纯函数口径。"""

from decimal import Decimal

from apps.kuaizhizao.utils.picking_posting import max_reportable_units_from_picked


def test_max_reportable_bottleneck_by_scarce_material():
    # 计划 100：A 需 200（2/件），B 需 100（1/件）；已领 A=100 → 支撑 50，B=80 → 支撑 80 → 取 50
    result = max_reportable_units_from_picked(
        Decimal("100"),
        [(1, Decimal("200")), (2, Decimal("100"))],
        {1: Decimal("100"), 2: Decimal("80")},
    )
    assert result == Decimal("50")


def test_max_reportable_none_when_no_pick_requirements():
    assert max_reportable_units_from_picked(Decimal("100"), [], {}) is None


def test_max_reportable_zero_when_nothing_picked():
    result = max_reportable_units_from_picked(
        Decimal("10"),
        [(9, Decimal("10"))],
        {},
    )
    assert result == Decimal("0")


def test_max_reportable_allows_full_plan_when_fully_picked():
    result = max_reportable_units_from_picked(
        Decimal("10"),
        [(1, Decimal("20"))],
        {1: Decimal("20")},
    )
    assert result == Decimal("10")
