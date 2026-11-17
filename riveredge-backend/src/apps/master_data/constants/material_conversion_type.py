"""物料副单位换算类型。"""

from typing import Any, Literal, Optional

MaterialConversionType = Literal["fixed", "floating"]

CONVERSION_TYPE_FIXED = "fixed"
CONVERSION_TYPE_FLOATING = "floating"


def normalize_material_conversion_type(value: Optional[str]) -> MaterialConversionType:
    raw = str(value or "").strip().lower()
    if raw in ("floating", "float", "none", "no_fixed", "nofixed"):
        return CONVERSION_TYPE_FLOATING
    return CONVERSION_TYPE_FIXED


def aux_unit_conversion_type(row: Any) -> MaterialConversionType:
    if not isinstance(row, dict):
        return CONVERSION_TYPE_FIXED
    return normalize_material_conversion_type(row.get("conversionType") or row.get("conversion_type"))


def is_floating_aux_unit_row(row: Any) -> bool:
    return aux_unit_conversion_type(row) == CONVERSION_TYPE_FLOATING
