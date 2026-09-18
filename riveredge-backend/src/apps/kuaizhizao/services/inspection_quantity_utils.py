"""检验数量口径：开展检验时合格+不合格须等于检验数量。"""

from decimal import Decimal
from typing import Any, Tuple

from core.utils.quantity_precision import quantize_business_quantity
from infra.exceptions import ValidationError


def to_inspection_quantity(value: Any, decimal_places: int = 2) -> Decimal:
    """按配置数量小数位量化，与 common.quantity_decimal_places 对齐。"""
    return quantize_business_quantity(value, decimal_places)


def assert_inspection_quantities_balanced(
    qualified_quantity: Any,
    unqualified_quantity: Any,
    inspection_quantity: Any,
    *,
    decimal_places: int = 2,
) -> Tuple[Decimal, Decimal]:
    """合格+不合格须等于检验数量；统一 Decimal 量化，避免 float 与 Decimal 直接比较误报。"""
    qualified = to_inspection_quantity(qualified_quantity, decimal_places)
    unqualified = to_inspection_quantity(unqualified_quantity, decimal_places)
    inspection = to_inspection_quantity(inspection_quantity, decimal_places)
    if qualified + unqualified != inspection:
        raise ValidationError("合格数量和不合格数量之和必须等于检验数量")
    return qualified, unqualified
