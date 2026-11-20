"""物料库存单位校验（禁止浮动副单位作库存单位）。"""

from __future__ import annotations

from typing import Any, Optional

from apps.master_data.constants.material_conversion_type import is_floating_aux_unit_row
from apps.kuaizhizao.utils.material_unit_utils import _parse_material_units_cfg
from infra.exceptions.exceptions import ValidationError


def validate_material_inventory_unit(
    *,
    base_unit: str,
    inventory_unit: Optional[str],
    units_cfg: Any = None,
) -> str:
    base = str(base_unit or "").strip()
    inv = str(inventory_unit or "").strip() or base
    if not base:
        raise ValidationError("基础单位不能为空")
    if inv == base:
        return inv

    parsed = _parse_material_units_cfg(units_cfg)
    if not parsed:
        raise ValidationError("库存单位须为基础单位或未配置辅助单位时不可另选")
    allowed_fixed: set[str] = {base}
    for row in parsed.get("units") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("unit") or "").strip()
        if not name:
            continue
        if is_floating_aux_unit_row(row):
            if name == inv:
                raise ValidationError(f"无固定换算的副单位「{inv}」不可作为库存单位")
            continue
        allowed_fixed.add(name)
    if inv not in allowed_fixed:
        raise ValidationError(f"库存单位「{inv}」须为基础单位或已配置的固定换算副单位")
    return inv


def sync_inventory_unit_to_units_json(
    *,
    base_unit: str,
    inventory_unit: str,
    units_cfg: Any,
) -> Any:
    """写物料时同步 units.scenarios.inventory。"""
    parsed = _parse_material_units_cfg(units_cfg)
    if not parsed:
        if inventory_unit == base_unit:
            return units_cfg
        return {"units": [], "scenarios": {"inventory": inventory_unit}}
    scenarios = dict(parsed.get("scenarios") or {})
    scenarios["inventory"] = inventory_unit
    parsed["scenarios"] = scenarios
    return parsed
