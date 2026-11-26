"""台账双计量（库存主单位 + 辅助副单位）解析与 API 行构造。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from apps.kuaizhizao.utils.inventory_posting_utils import (
    InventoryPostingQuantities,
    normalize_inventory_posting_quantities,
)
from apps.kuaizhizao.utils.material_unit_utils import (
    _parse_material_units_cfg,
    convert_from_base_quantity,
    convert_to_base_quantity,
    resolve_material_inventory_unit,
)
from apps.master_data.constants.material_conversion_type import is_floating_aux_unit_row
from infra.exceptions.exceptions import ValidationError


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _material_label(material: Any) -> str:
    return str(
        getattr(material, "main_code", None) or getattr(material, "code", "") or ""
    ).strip()


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
    """无固定换算辅助单位：批号 aux 由单据手填独立累计，不与主数量镜像。"""
    return (
        resolve_material_display_auxiliary_unit(material) is not None
        and not material_ledger_is_dual_unit(material)
    )


def resolve_ledger_units(material: Any) -> Tuple[str, str]:
    """返回 (primary_unit, secondary_unit)；无辅助时 secondary 与 primary 相同。"""
    if material is None:
        return "", ""
    base_unit = str(getattr(material, "base_unit", None) or "").strip()
    primary = resolve_material_inventory_unit(material) or base_unit
    aux = resolve_ledger_auxiliary_unit(material)
    secondary = aux or primary
    return primary, secondary


def ledger_aux_quantity_from_base(material: Any, base_quantity: Any) -> Decimal:
    """写路径：基本量 → 辅助量（固定辅助单位）。"""
    aux_unit = resolve_ledger_auxiliary_unit(material)
    base_q = _decimal(base_quantity)
    if aux_unit is None:
        return base_q
    return convert_from_base_quantity(material, base_q, to_unit=aux_unit)


def ledger_aux_delta_from_base_delta(material: Any, base_delta: Any) -> Decimal:
    return ledger_aux_quantity_from_base(material, base_delta)


def canonical_material_batch_aux_quantity(
    material: Any,
    *,
    quantity: Any,
    base_quantity: Any = None,
) -> Decimal:
    """批号 aux_quantity 真源：单计量=库存量；双计量=由基本量换算固定辅助量。"""
    qty = _decimal(quantity)
    base_q = _decimal(base_quantity) if base_quantity is not None else qty
    if base_q == 0 and qty != 0:
        base_q = qty
    if material is None or not material_ledger_is_dual_unit(material):
        return qty
    return ledger_aux_quantity_from_base(material, base_q)


def sync_material_batch_ledger_quantities(batch: Any, material: Any) -> None:
    """
    写库前校正 material_batch 的 quantity / base_quantity / aux_quantity。

    单计量：三字段强制与库存量一致，禁止孤立 aux 漂移。
    无固定换算辅助：主/基本量对齐，aux_quantity 保持业务累计值。
    双计量：aux 由 base_quantity 换算。
    """
    qty = _decimal(getattr(batch, "quantity", None))
    if material is None or not material_ledger_is_dual_unit(material):
        batch.quantity = qty
        base_q = _decimal(getattr(batch, "base_quantity", None))
        if base_q == 0 and qty != 0:
            batch.base_quantity = qty
        elif base_q == 0:
            batch.base_quantity = qty
        else:
            batch.base_quantity = base_q
        if material is not None and material_ledger_uses_manual_aux_quantity(material):
            aux = _decimal(getattr(batch, "aux_quantity", None))
            if aux < 0:
                batch.aux_quantity = Decimal("0")
            return
        batch.base_quantity = qty
        batch.aux_quantity = qty
        return

    base = _decimal(getattr(batch, "base_quantity", None))
    if base == 0 and qty != 0:
        inv_unit = resolve_material_inventory_unit(material)
        base = convert_to_base_quantity(material, qty, from_unit=inv_unit)
        batch.base_quantity = base
    inv_q, base_q = normalize_inventory_posting_quantities(
        material, qty, base_quantity=base
    )
    batch.quantity = inv_q
    batch.base_quantity = base_q
    batch.aux_quantity = ledger_aux_quantity_from_base(material, base_q)


@dataclass(frozen=True)
class LedgerSyncQuantities:
    quantity: Decimal
    base_quantity: Decimal
    aux_quantity: Decimal


def resolve_stored_ledger_quantities(
    material: Any,
    *,
    primary_quantity: Any,
    aux_quantity_raw: Any = None,
    base_quantity_raw: Any = None,
) -> Tuple[Decimal, Decimal]:
    """
    从 ORM 存量解析台账主/副数量（读 API 用）。

    单计量：副数量与主数量同口径，忽略孤立的 aux_quantity（历史脏数据）。
    双计量：优先 aux_quantity；缺省时按基本量换算；明显偏离基本量时按基本量重算展示。
    """
    primary = _decimal(primary_quantity)
    if material is not None and material_ledger_uses_manual_aux_quantity(material):
        if aux_quantity_raw is None:
            return primary, Decimal("0")
        aux = _decimal(aux_quantity_raw)
        if aux < 0:
            return primary, Decimal("0")
        return primary, aux
    if not material_ledger_is_dual_unit(material):
        return primary, primary

    base_q = _decimal(base_quantity_raw) if base_quantity_raw is not None else primary
    expected_aux = ledger_aux_quantity_from_base(material, base_q)

    if aux_quantity_raw is None:
        return primary, Decimal("0")

    aux = _decimal(aux_quantity_raw)
    if aux < 0 or abs(aux - expected_aux) > Decimal("0.0001"):
        return primary, expected_aux
    return primary, aux


def _resolve_base_quantity_for_sync(
    material: Any,
    *,
    inventory_quantity: Decimal,
    base_quantity_raw: Any,
) -> Decimal:
    if base_quantity_raw is not None:
        return _decimal(base_quantity_raw)
    inv_unit = resolve_material_inventory_unit(material)
    return convert_to_base_quantity(
        material,
        inventory_quantity,
        from_unit=inv_unit,
    )


def _resolve_aux_quantity_for_sync(
    material: Any,
    *,
    base_quantity: Decimal,
    aux_quantity_raw: Any,
) -> Decimal:
    if material_ledger_uses_manual_aux_quantity(material):
        if aux_quantity_raw is not None:
            return _decimal(aux_quantity_raw)
        return Decimal("0")
    aux_unit = resolve_ledger_auxiliary_unit(material)
    if aux_unit is None:
        return base_quantity
    if aux_quantity_raw is not None:
        return _decimal(aux_quantity_raw)
    if base_quantity <= 0:
        return Decimal("0")
    return ledger_aux_quantity_from_base(material, base_quantity)


def resolve_sync_ledger_quantities(
    material: Any,
    *,
    primary_quantity: Any,
    base_quantity_raw: Any = None,
    aux_quantity_raw: Any = None,
) -> LedgerSyncQuantities:
    """
    金蝶即时库存同步：库存量、基本量、辅助量。

    - avbqty/qty → quantity
    - baseqty → base_quantity（基本）
    - 辅助量：映射字段或写路径由基本量换算（固定辅助）
    """
    if primary_quantity is None:
        raise ValidationError("缺少主数量（库存数量）")
    inv_q = _decimal(primary_quantity)

    base_q = _resolve_base_quantity_for_sync(
        material,
        inventory_quantity=inv_q,
        base_quantity_raw=base_quantity_raw,
    )
    inv_q, base_q = normalize_inventory_posting_quantities(
        material, inv_q, base_quantity=base_q
    )

    aux_q = _resolve_aux_quantity_for_sync(
        material,
        base_quantity=base_q,
        aux_quantity_raw=aux_quantity_raw,
    )

    if material_ledger_is_dual_unit(material) and aux_q <= 0 and inv_q > 0:
        raise ValidationError(
            f"物料 {_material_label(material)} 有固定辅助单位，来源行缺少辅助数量且无法由基本量换算"
        )

    return LedgerSyncQuantities(
        quantity=inv_q,
        base_quantity=base_q,
        aux_quantity=aux_q,
    )


def resolve_sync_ledger_pair(
    material: Any,
    *,
    primary_quantity: Any,
    secondary_quantity_raw: Any = None,
    base_quantity_raw: Any = None,
    aux_quantity_raw: Any = None,
) -> Tuple[Decimal, Decimal]:
    """
    兼容旧调用：返回 (quantity, base_quantity)。

    secondary_quantity_raw 已废弃（曾误传 baseqty）；请传 base_quantity_raw / aux_quantity_raw。
    """
    base_raw = base_quantity_raw if base_quantity_raw is not None else secondary_quantity_raw
    synced = resolve_sync_ledger_quantities(
        material,
        primary_quantity=primary_quantity,
        base_quantity_raw=base_raw,
        aux_quantity_raw=aux_quantity_raw,
    )
    return synced.quantity, synced.base_quantity


def resolve_confirmation_ledger_pair(
    material: Any,
    *,
    primary_quantity: Any,
    secondary_quantity_raw: Any = None,
) -> Tuple[Decimal, Decimal]:
    """确认体：primary=库存量，secondary=辅助量 → 过账 (inventory_quantity, base_quantity)。"""
    if primary_quantity is None:
        raise ValidationError("确认明细缺少主数量")
    inv_q = _decimal(primary_quantity)
    aux_unit = resolve_ledger_auxiliary_unit(material)
    inv_unit = resolve_material_inventory_unit(material)
    base_unit = str(getattr(material, "base_unit", None) or "").strip()

    if aux_unit is None:
        return normalize_inventory_posting_quantities(
            material, inv_q, base_quantity=inv_q
        )

    if secondary_quantity_raw is None:
        raise ValidationError("台账双单位物料确认时必须提供副数量（辅助单位数量）")

    # 库存单位即基本单位：过账基本量以主数量为准；副数量只进台账 aux，不用辅助单位反推基本量
    if not inv_unit or inv_unit == base_unit:
        return normalize_inventory_posting_quantities(
            material, inv_q, base_quantity=inv_q
        )

    aux_q = _decimal(secondary_quantity_raw)
    base_q = convert_to_base_quantity(material, aux_q, from_unit=aux_unit)
    return normalize_inventory_posting_quantities(material, inv_q, base_quantity=base_q)


def ledger_quantities_from_posting(
    posting: InventoryPostingQuantities,
    material: Any,
    *,
    aux_quantity: Any = None,
) -> Dict[str, Any]:
    primary_unit, secondary_unit = resolve_ledger_units(material)
    if aux_quantity is not None:
        aux_q = _decimal(aux_quantity)
    else:
        aux_q = ledger_aux_quantity_from_base(material, posting.base_quantity)
    return {
        "primary_unit": primary_unit or None,
        "secondary_unit": secondary_unit or None,
        "primary_quantity": float(posting.inventory_quantity),
        "secondary_quantity": float(aux_q),
    }


def document_line_ledger_fields(
    material: Any,
    *,
    line_quantity: Any,
    aux_quantity: Any = None,
) -> Dict[str, Any]:
    """
    仓储单据行 → 与即时库存一致的对外主/副字段。

    primary = 库存单位量；secondary = 固定辅助单位量（无则同 primary）。
    不删除行上的 aux_* / material_unit。
    """
    primary_unit, secondary_unit = resolve_ledger_units(material)
    primary_d, secondary_d = resolve_stored_ledger_quantities(
        material,
        primary_quantity=line_quantity,
        aux_quantity_raw=aux_quantity,
    )
    return {
        "primary_unit": primary_unit or None,
        "secondary_unit": secondary_unit or None,
        "primary_quantity": float(primary_d),
        "secondary_quantity": float(secondary_d),
    }


def apply_ledger_fields_to_inventory_row(
    row: Dict[str, Any],
    material: Any,
) -> Dict[str, Any]:
    """
    将库存报表行转为对外台账字段，并移除 legacy 键。
    调用前 row 可含 quantity / aux_quantity / base_quantity（基本量不对外）。
    """
    primary_qty = row.pop("quantity", row.get("primary_quantity", 0))
    aux_raw = row.pop("aux_quantity", row.get("secondary_quantity"))
    base_qty_raw = row.pop("base_quantity", None)
    row.pop("inventory_unit", None)
    row.pop("base_unit", None)
    material_unit = row.pop("material_unit", None)

    mat = material
    if mat is None and material_unit:
        primary_unit = str(material_unit)
    else:
        primary_unit, _ = resolve_ledger_units(mat)

    is_dual = material_ledger_is_dual_unit(mat) if mat is not None else False
    display_aux = resolve_material_display_auxiliary_unit(mat) if mat is not None else None
    row["ledger_is_dual_unit"] = is_dual
    row["ledger_has_auxiliary_unit"] = display_aux is not None

    primary_d, secondary_d = resolve_stored_ledger_quantities(
        mat,
        primary_quantity=primary_qty,
        aux_quantity_raw=aux_raw,
        base_quantity_raw=base_qty_raw,
    )
    row["primary_unit"] = primary_unit or None
    row["primary_quantity"] = float(primary_d)
    if display_aux:
        row["secondary_unit"] = display_aux
        if is_dual:
            row["secondary_quantity"] = float(secondary_d)
        elif mat is not None and material_ledger_uses_manual_aux_quantity(mat):
            if aux_raw is not None:
                aux_f = _decimal(aux_raw)
                row["secondary_quantity"] = (
                    None if aux_f == primary_d else float(aux_f)
                )
            else:
                row["secondary_quantity"] = None
        else:
            row["secondary_quantity"] = None
    else:
        row["secondary_unit"] = None
        row["secondary_quantity"] = None
    return row
