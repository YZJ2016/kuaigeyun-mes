"""固定资产折旧方法计算。"""

from decimal import Decimal

from apps.kuaicaiwu.services.fa_core import compute_period_depreciation
from apps.kuaicaiwu.services.fa_depreciation_methods import (
    DEPRECIATION_LABEL_TO_CODE,
    normalize_depreciation_method,
)


def test_normalize_depreciation_method_labels():
    assert normalize_depreciation_method("双倍余额递减法") == "double_declining"
    assert normalize_depreciation_method("不折旧") == "none"
    assert DEPRECIATION_LABEL_TO_CODE["年数总和法"] == "sum_of_years"


def test_straight_line_period_depreciation():
    dep = compute_period_depreciation(
        depreciation_method="straight_line",
        original_value=Decimal("600000"),
        residual_rate=Decimal("0.05"),
        useful_life_months=60,
        depreciated_periods=0,
        accumulated_depreciation=Decimal("0"),
    )
    assert dep == Decimal("9500.0000")


def test_none_method_returns_zero():
    dep = compute_period_depreciation(
        depreciation_method="none",
        original_value=Decimal("100000"),
        residual_rate=Decimal("0.05"),
        useful_life_months=60,
    )
    assert dep == Decimal("0")


def test_double_declining_higher_than_straight_early_periods():
    dep = compute_period_depreciation(
        depreciation_method="double_declining",
        original_value=Decimal("120000"),
        residual_rate=Decimal("0.05"),
        useful_life_months=60,
        depreciated_periods=0,
        accumulated_depreciation=Decimal("0"),
    )
    straight = compute_period_depreciation(
        depreciation_method="straight_line",
        original_value=Decimal("120000"),
        residual_rate=Decimal("0.05"),
        useful_life_months=60,
        depreciated_periods=0,
        accumulated_depreciation=Decimal("0"),
    )
    assert dep > straight


def test_units_of_production_requires_workload():
    dep = compute_period_depreciation(
        depreciation_method="units_of_production",
        original_value=Decimal("100000"),
        residual_rate=Decimal("0.05"),
        useful_life_months=60,
        total_workload=Decimal("60000"),
        depreciated_periods=0,
        accumulated_depreciation=Decimal("0"),
    )
    assert dep == Decimal("1583.3333")


def test_straight_line_recalculates_after_impairment():
    """减值后月折旧按（账面价值 - 净残值）/ 剩余期间。"""
    without_impairment = compute_period_depreciation(
        depreciation_method="straight_line",
        original_value=Decimal("500000"),
        residual_rate=Decimal("0.10"),
        useful_life_months=60,
        depreciated_periods=11,
        accumulated_depreciation=Decimal("37600"),
        impairment_value=Decimal("0"),
    )
    assert without_impairment == Decimal("7500.0000")

    with_impairment = compute_period_depreciation(
        depreciation_method="straight_line",
        original_value=Decimal("500000"),
        residual_rate=Decimal("0.10"),
        useful_life_months=60,
        depreciated_periods=11,
        accumulated_depreciation=Decimal("37600"),
        impairment_value=Decimal("100"),
    )
    # (500000 - 37600 - 100 - 50000) / 49
    assert with_impairment == Decimal("8414.2857")
