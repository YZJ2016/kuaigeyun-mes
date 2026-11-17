"""无价税字段单据行金额写入（跟 amount_places，禁止散落 hardcode 0.01）。"""

from __future__ import annotations

from decimal import Decimal

from core.utils.amount_precision import quantize_business_amount


def line_total_qty_unit_price(
    qty: Decimal | int | float | str,
    unit_price: Decimal | int | float | str,
    *,
    amount_places: int = 2,
) -> Decimal:
    q = Decimal(str(qty or 0))
    p = Decimal(str(unit_price or 0))
    return quantize_business_amount(q * p, amount_places)


def resolve_simple_line_total(
    qty: Decimal | int | float | str,
    unit_price: Decimal | int | float | str,
    total_amount: Decimal | int | float | str | None = None,
    *,
    amount_places: int = 2,
) -> Decimal:
    """无价税行：数量×单价；显式 total 仅在非零或与单价为 0 时保留。"""
    computed = line_total_qty_unit_price(qty, unit_price, amount_places=amount_places)
    if total_amount is None:
        return computed
    given = quantize_business_amount(Decimal(str(total_amount or 0)), amount_places)
    if given == 0 and computed != 0:
        return computed
    return given


def allocate_amount_by_weights(
    total: Decimal | int | float | str,
    weights: list[Decimal | int | float | str],
    *,
    amount_places: int = 2,
) -> list[Decimal]:
    """按权重分摊金额；末行吃尾差，保证合计等于 total（与前端 allocateAmountByWeights 一致）。"""
    if not weights:
        return []
    total_dec = quantize_business_amount(Decimal(str(total or 0)), amount_places)
    safe_weights = [
        max(Decimal("0"), Decimal(str(w or 0))) for w in weights
    ]
    weight_sum = sum(safe_weights)
    if weight_sum <= 0:
        n = len(safe_weights)
        if n == 1:
            return [total_dec]
        each = quantize_business_amount(total_dec / n, amount_places)
        parts = [each] * (n - 1)
        parts.append(total_dec - sum(parts))
        return parts
    parts: list[Decimal] = []
    allocated = Decimal("0")
    for i, w in enumerate(safe_weights):
        if i == len(safe_weights) - 1:
            parts.append(total_dec - allocated)
        else:
            part = quantize_business_amount(total_dec * w / weight_sum, amount_places)
            parts.append(part)
            allocated += part
    return parts
