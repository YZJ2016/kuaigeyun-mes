"""固定资产通用辅助。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional, Type

from tortoise.models import Model

from apps.kuaicaiwu.services.fa_depreciation_methods import normalize_depreciation_method
from core.utils.timezone_utils import resolve_business_datetime, today_site_str
from infra.models.user import User


def model_to_dict(row: Model, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for field in row._meta.fields_map:
        if field == "deleted_at":
            continue
        value = getattr(row, field, None)
        if isinstance(value, datetime):
            data[field] = value.isoformat()
        elif isinstance(value, date):
            data[field] = value.isoformat()
        elif isinstance(value, Decimal):
            data[field] = float(value)
        else:
            data[field] = value
    if extra:
        data.update(extra)
    return data


async def generate_daily_code(
    model: Type[Model],
    tenant_id: int,
    prefix: str,
    code_field: str,
) -> str:
    today = today_site_str().replace("-", "")
    base = f"{prefix}{today}"
    count = await model.filter(tenant_id=tenant_id, **{f"{code_field}__startswith": base}).count()
    return f"{base}{count + 1:04d}"


def quantize_money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def compute_residual_value(
    original_value: Decimal,
    residual_rate: Decimal,
) -> Decimal:
    return quantize_money(original_value * residual_rate)


def compute_monthly_depreciation(
    original_value: Decimal,
    residual_rate: Decimal,
    useful_life_months: int,
    *,
    depreciation_method: str = "straight_line",
    depreciated_periods: int = 0,
    accumulated_depreciation: Decimal | float | int | str = 0,
    impairment_value: Decimal | float | int | str = 0,
    total_workload: Decimal | float | int | str | None = None,
    period_workload: Decimal | float | int | str | None = None,
) -> Decimal:
    """下一期应计提折旧额（卡片展示与计提预览共用）。

    工作量法：未传 period_workload 时返回单位折旧额（原值减残值 / 预计总工作量）；
    传入当期工作量时返回 单位折旧 × 当期工作量。
    """
    return compute_period_depreciation(
        depreciation_method=depreciation_method,
        original_value=original_value,
        residual_rate=residual_rate,
        useful_life_months=useful_life_months,
        depreciated_periods=depreciated_periods,
        accumulated_depreciation=accumulated_depreciation,
        impairment_value=impairment_value,
        total_workload=total_workload,
        period_workload=period_workload,
    )


def _life_years_from_months(useful_life_months: int) -> int:
    """年数总和法按年计算：使用月数向上折算为整年（至少 1 年）。"""
    life = int(useful_life_months or 0)
    if life <= 0:
        return 0
    return max(1, (life + 11) // 12)


def compute_period_depreciation(
    *,
    depreciation_method: str,
    original_value: Decimal | float | int | str,
    residual_rate: Decimal | float | int | str,
    useful_life_months: int,
    depreciated_periods: int = 0,
    accumulated_depreciation: Decimal | float | int | str = 0,
    impairment_value: Decimal | float | int | str = 0,
    total_workload: Decimal | float | int | str | None = None,
    period_workload: Decimal | float | int | str | None = None,
) -> Decimal:
    method = normalize_depreciation_method(depreciation_method)
    if method == "none":
        return Decimal("0")

    original = quantize_money(original_value)
    residual = compute_residual_value(original, quantize_money(residual_rate))
    depreciable = quantize_money(original - residual)
    if depreciable <= 0:
        return Decimal("0")

    life = int(useful_life_months or 0)
    used = max(0, int(depreciated_periods or 0))

    accumulated = quantize_money(accumulated_depreciation)
    impairment = quantize_money(impairment_value)
    book_value = quantize_money(original - accumulated - impairment)
    if book_value <= residual:
        return Decimal("0")

    remaining_depreciable = quantize_money(book_value - residual)

    # 工作量法不依赖预计使用期间数；其余方法须有有效期间
    if method != "units_of_production":
        if life <= 0 or used >= life:
            return Decimal("0")

    remaining_periods = max(1, life - used) if life > 0 else 1

    if method == "straight_line":
        if impairment > 0:
            dep = quantize_money(remaining_depreciable / Decimal(remaining_periods))
        else:
            dep = quantize_money(depreciable / Decimal(life))
    elif method == "double_declining":
        ddb = quantize_money(book_value * Decimal("2") / Decimal(life))
        sl = quantize_money(remaining_depreciable / Decimal(remaining_periods))
        # 最后 24 个计提月（或剩余期间不足 24 月时）改按直线法，避免尾差
        dep = sl if remaining_periods <= 24 else ddb
        if dep < sl:
            dep = sl
    elif method == "sum_of_years":
        # 年数总和法按「年」加权，再除以 12 得到月折旧（不用月数直接作年数）
        life_years = _life_years_from_months(life)
        if life_years <= 0:
            return Decimal("0")
        year_index = min(used // 12, life_years - 1)
        remaining_years = life_years - year_index
        if remaining_years <= 0:
            return Decimal("0")
        if impairment > 0:
            sum_remaining = Decimal(remaining_years * (remaining_years + 1)) / Decimal("2")
            annual = quantize_money(remaining_depreciable * Decimal(remaining_years) / sum_remaining)
        else:
            sum_digits = Decimal(life_years * (life_years + 1)) / Decimal("2")
            weight = Decimal(remaining_years)
            annual = quantize_money(depreciable * weight / sum_digits)
        dep = quantize_money(annual / Decimal("12"))
    elif method == "units_of_production":
        # 单位折旧 = 应计折旧额 / 预计总工作量；当期折旧 = 单位折旧 × 当期工作量
        workload = quantize_money(total_workload)
        if workload <= 0:
            return Decimal("0")
        base = remaining_depreciable if impairment > 0 else depreciable
        unit_rate = quantize_money(base / workload)
        if period_workload is None:
            dep = unit_rate
        else:
            pw = quantize_money(period_workload)
            if pw <= 0:
                return Decimal("0")
            dep = quantize_money(unit_rate * pw)
    else:
        if impairment > 0:
            dep = quantize_money(remaining_depreciable / Decimal(remaining_periods))
        else:
            dep = quantize_money(depreciable / Decimal(life))

    max_dep = quantize_money(book_value - residual)
    if dep > max_dep:
        dep = max_dep
    return dep if dep > 0 else Decimal("0")


def compute_net_value(
    original_value: Decimal,
    accumulated_depreciation: Decimal,
    impairment_value: Decimal,
) -> Decimal:
    return quantize_money(original_value - accumulated_depreciation - impairment_value)


async def touch_updated(row: Model, user: Optional[User | int] = None) -> None:
    row.updated_at = resolve_business_datetime()
    if user is None:
        return
    if isinstance(user, User):
        row.updated_by = user.id
        row.updated_by_name = getattr(user, "name", None) or getattr(user, "username", None)
        return
    resolved = await User.get_or_none(id=int(user))
    if resolved:
        row.updated_by = resolved.id
        row.updated_by_name = getattr(resolved, "name", None) or getattr(resolved, "username", None)
