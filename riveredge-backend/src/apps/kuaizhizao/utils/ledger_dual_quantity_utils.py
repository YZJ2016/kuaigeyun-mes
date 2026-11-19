"""台账双计量：单据推送要用的辅助单位解析。

未摘上游同文件里的批号回写、确认过账和库存行落库（sync_material_batch_ledger_quantities、
resolve_sync_ledger_quantities、resolve_confirmation_ledger_pair、apply_ledger_fields_to_inventory_row
等）。那些函数会改库存写路径，本链只服务金蝶分录数量。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from apps.kuaizhizao.utils.material_unit_utils import (
    _parse_material_units_cfg,
    convert_from_base_quantity,
    resolve_material_inventory_unit,
)
from apps.master_data.constants.material_conversion_type import is_floating_aux_unit_row


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def resolve_material_display_auxiliary_unit(material: Any) -> Optional[str]:
    """即时库存等展示：物料配置的第一个辅助单位（含无固定换算）。"""
    if material is None:
        return None
    units_cfg = _parse_material_units_cfg(getattr(material, "units", None))
    if not units_cfg:
        return None
    rows = units_cfg.get("units") or []
    if not isinstance(rows, list):
        return None
    base_unit = str(getattr(material, "base_unit", None) or "").strip()
    primary = resolve_material_inventory_unit(material) or base_unit
    primary_key = primary.casefold()
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("unit") or "").strip()
        if not name:
            continue
        if primary_key and name.casefold() == primary_key:
            continue
        return name
    return None


def resolve_ledger_auxiliary_unit(material: Any) -> Optional[str]:
    """台账副单位：物料 units 列表中第一个固定换算辅助单位。"""
    if material is None:
        return None
    units_cfg = _parse_material_units_cfg(getattr(material, "units", None))
    if not units_cfg:
        return None
    rows = units_cfg.get("units") or []
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if is_floating_aux_unit_row(row):
            continue
        name = str(row.get("unit") or "").strip()
        if name:
            return name
    return None


def material_ledger_is_dual_unit(material: Any) -> bool:
    """台账双单位：存在固定辅助单位。"""
    return resolve_ledger_auxiliary_unit(material) is not None


def material_ledger_uses_manual_aux_quantity(material: Any) -> bool:
    """无固定换算辅助单位：批号 aux 由单据手填，不与主数量镜像。"""
    return (
        resolve_material_display_auxiliary_unit(material) is not None
        and not material_ledger_is_dual_unit(material)
    )


def ledger_aux_quantity_from_base(material: Any, base_quantity: Any) -> Decimal:
    """基本数量 → 固定辅助单位数量。无固定辅助单位时返回基本数量。"""
    aux_unit = resolve_ledger_auxiliary_unit(material)
    base_q = _decimal(base_quantity)
    if aux_unit is None:
        return base_q
    return convert_from_base_quantity(material, base_q, to_unit=aux_unit)
