"""单据行主/副数量与基础单位过账换算。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from apps.master_data.constants.material_conversion_type import is_floating_aux_unit_row
from apps.kuaizhizao.utils.material_unit_utils import (
    _parse_material_units_cfg,
    convert_to_base_quantity,
    resolve_unit_to_base_factor,
)
from infra.exceptions.exceptions import ValidationError


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _aux_row_for_unit(material: Any, unit_name: str) -> Optional[dict]:
    units_cfg = _parse_material_units_cfg(getattr(material, "units", None))
    if not units_cfg:
        return None
    target = str(unit_name or "").strip()
    for row in units_cfg.get("units") or []:
        if isinstance(row, dict) and str(row.get("unit") or "").strip() == target:
            return row
    return None


def is_floating_line_unit(material: Any, material_unit: Optional[str]) -> bool:
    row = _aux_row_for_unit(material, str(material_unit or "").strip())
    return bool(row and is_floating_aux_unit_row(row))


def compute_line_unit_conversion_rate(
    *,
    primary_quantity: Any,
    aux_quantity: Any,
) -> Optional[Decimal]:
    """1 副单位 = rate 主单位（与物料分子/分母语义一致）。"""
    primary = _decimal(primary_quantity)
    aux = _decimal(aux_quantity)
    if primary <= 0 or aux <= 0:
        return None
    return primary / aux


def convert_document_line_quantity_to_base(
    *,
    material: Any,
    quantity: Any,
    material_unit: Optional[str],
    aux_quantity: Any = None,
    unit_conversion_rate: Any = None,
) -> Decimal:
    """
    业务行数量 → 主单位（库存）数量。

    - material_unit 为主单位：quantity 即主数量
    - 有行换算率：quantity 按副单位计，主数量 = quantity × rate（或双数量时用 aux×rate 校验）
    - 固定换算：quantity 按 material_unit 用主数据 n/d 折算
    - 浮动且无行率：报错
    """
    qty = _decimal(quantity)
    if qty <= 0 or not material:
        return qty

    base_unit = str(getattr(material, "base_unit", None) or "").strip()
    unit = str(material_unit or "").strip() or base_unit

    if not base_unit or unit == base_unit:
        return qty

    line_rate = _decimal(unit_conversion_rate) if unit_conversion_rate is not None else None
    if line_rate is not None and line_rate > 0:
        return qty * line_rate

    aux_qty = _decimal(aux_quantity) if aux_quantity is not None else Decimal("0")
    if aux_qty > 0:
        derived = compute_line_unit_conversion_rate(primary_quantity=qty, aux_quantity=aux_qty)
        if derived and derived > 0:
            return aux_qty * derived

    if is_floating_line_unit(material, unit):
        raise ValidationError(
            f"物料 {getattr(material, 'main_code', '') or getattr(material, 'id', '')} "
            f"副单位「{unit}」为无固定换算，须填写主数量、副数量或行换算率"
        )

    factor = resolve_unit_to_base_factor(material, unit)
    if factor is None or factor <= 0:
        raise ValidationError(f"无法解析物料副单位「{unit}」的固定换算关系")
    return qty * factor


def validate_floating_line_dual_quantities(
    *,
    material: Any,
    material_unit: Optional[str],
    quantity: Any,
    aux_quantity: Any = None,
    aux_unit: Optional[str] = None,
    unit_conversion_rate: Any = None,
) -> None:
    """保存前校验：浮动副单位须双录或提供行换算率。"""
    unit = str(material_unit or "").strip()
    if not material or not unit or not is_floating_line_unit(material, unit):
        return
    qty = _decimal(quantity)
    aux_qty = _decimal(aux_quantity)
    rate = _decimal(unit_conversion_rate) if unit_conversion_rate is not None else Decimal("0")
    if rate > 0 and qty > 0:
        return
    if qty > 0 and aux_qty > 0 and str(aux_unit or "").strip():
        return
    raise ValidationError(
        "无固定换算的副单位须同时填写主数量与副数量，或填写行换算率"
    )
