"""库存过账双计量：库存单位数量 + 基本单位数量。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional, Tuple

from apps.kuaizhizao.utils.material_dual_quantity_utils import (
    convert_document_line_quantity_to_base,
)
from apps.kuaizhizao.utils.material_unit_utils import (
    convert_from_base_quantity,
    resolve_material_inventory_unit,
)
from infra.exceptions.exceptions import ValidationError


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


@dataclass(frozen=True)
class InventoryPostingQuantities:
    inventory_quantity: Decimal
    base_quantity: Decimal
    ledger_aux_quantity: Optional[Decimal] = None


def resolve_material_inventory_unit_field(material: Any) -> str:
    return resolve_material_inventory_unit(material)


def convert_line_to_posting_quantities(
    *,
    material: Any,
    quantity: Any,
    material_unit: Optional[str] = None,
    aux_quantity: Any = None,
    unit_conversion_rate: Any = None,
) -> InventoryPostingQuantities:
    """业务行 → 库存单位数量 + 基本单位数量。"""
    base_qty = convert_document_line_quantity_to_base(
        material=material,
        quantity=quantity,
        material_unit=material_unit,
        aux_quantity=aux_quantity,
        unit_conversion_rate=unit_conversion_rate,
    )
    inv_unit = resolve_material_inventory_unit(material)
    base_unit = str(getattr(material, "base_unit", None) or "").strip()
    if not inv_unit or inv_unit == base_unit:
        inv_qty = base_qty
    else:
        inv_qty = convert_from_base_quantity(material, base_qty, to_unit=inv_unit)
    ledger_aux = None
    from apps.kuaizhizao.utils.ledger_dual_quantity_utils import (
        material_ledger_uses_manual_aux_quantity,
    )

    if material is not None and material_ledger_uses_manual_aux_quantity(material):
        if aux_quantity is not None:
            ledger_aux = _decimal(aux_quantity)
    return InventoryPostingQuantities(
        inventory_quantity=inv_qty,
        base_quantity=base_qty,
        ledger_aux_quantity=ledger_aux,
    )


def normalize_inventory_posting_quantities(
    material: Any,
    quantity: Any,
    *,
    base_quantity: Any = None,
) -> Tuple[Decimal, Decimal]:
    """
    解析过账数量对。

    - base_quantity 为 None：quantity 按基本单位数量（历史调用），换算库存单位数量。
    - base_quantity 有值：quantity 为库存单位数量，base_quantity 为基本单位数量。
    """
    if material is None:
        qty = _decimal(quantity)
        base_q = _decimal(base_quantity) if base_quantity is not None else qty
        return qty, base_q

    inv_unit = resolve_material_inventory_unit(material)
    base_unit = str(getattr(material, "base_unit", None) or "").strip()

    if base_quantity is None:
        base_q = _decimal(quantity)
        if not inv_unit or inv_unit == base_unit:
            return base_q, base_q
        inv_q = convert_from_base_quantity(material, base_q, to_unit=inv_unit)
        return inv_q, base_q

    inv_q = _decimal(quantity)
    base_q = _decimal(base_quantity)
    if not inv_unit or inv_unit == base_unit:
        if abs(inv_q - base_q) > Decimal("0.0001"):
            raise ValidationError("库存单位与基本单位相同时，两种数量须一致")
        return inv_q, base_q
    return inv_q, base_q


def split_base_deduct_for_inventory_deduct(
    total_inventory: Decimal,
    total_base: Decimal,
    deduct_inventory: Decimal,
    *,
    remaining_base: Optional[Decimal] = None,
) -> Decimal:
    """按库存单位扣量比例分摊基本单位扣量；最后一笔用 remaining_base 避免舍入漂移。"""
    deduct_inv = _decimal(deduct_inventory)
    if deduct_inv <= 0:
        return Decimal("0")
    if remaining_base is not None and _decimal(total_inventory) > 0 and deduct_inv >= _decimal(
        total_inventory
    ):
        return _decimal(remaining_base)
    total_inv = _decimal(total_inventory)
    total_b = _decimal(total_base)
    if total_inv <= 0 or total_b <= 0:
        return deduct_inv
    return total_b * deduct_inv / total_inv
