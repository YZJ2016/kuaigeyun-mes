"""仓储单据推送苍穹：库存单位数量 + 辅助单位数量（billentry 真源字段）。

辅助数量开放字段为 ``qtyunit2nd``（query 回显同名）。
禁止写即时库存字段 ``qty2nd``——会被忽略并默认成与库存数量相同。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Union

from loguru import logger

from core.services.integration.document_push_codes import (
    DEFAULT_UNIT_NUMBER,
    resolve_push_unit_number,
)
from infra.exceptions.exceptions import BusinessLogicError

QuantityField = Union[str, Callable[[Any], Any]]


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def restate_entry_prices_for_inventory_qty(
    entry: Dict[str, Any],
    *,
    document_qty: float,
    unit_price: float = 0.0,
    amount: Optional[float] = None,
    amount_and_tax: Optional[float] = None,
) -> None:
    """库存数量与单据数量不一致时，用单据金额反推单价。

    金额仍按单据数量计算。只改单价，避免单据单价乘库存数量。
    """
    pushed = _to_float(entry.get("qty"))
    doc = _to_float(document_qty)
    if pushed <= 0 or abs(pushed - doc) <= 1e-6:
        return
    money = _to_float(amount) if amount is not None else 0.0
    if money <= 0 and unit_price and doc > 0:
        money = _to_float(unit_price) * doc
    if money > 0:
        entry["price"] = round(money / pushed, 6)
    if amount_and_tax is not None:
        gross = _to_float(amount_and_tax)
        if gross > 0:
            entry["priceandtax"] = round(gross / pushed, 6)


def _line_quantity(item: Any, quantity_field: QuantityField) -> Any:
    if callable(quantity_field):
        return quantity_field(item)
    return getattr(item, quantity_field, None)


def apply_billentry_dual_qty_fields(
    entry: Dict[str, Any],
    planned: Optional[Dict[str, Any]],
) -> None:
    """把 resolve 结果写入苍穹分录（unit_number/qty/baseqty/unit2nd_number/qtyunit2nd）。"""
    if not planned:
        return
    unit_number = str(planned.get("unit_number") or "").strip()
    if unit_number:
        entry["unit_number"] = unit_number
    if planned.get("qty") is not None:
        entry["qty"] = _to_float(planned.get("qty"))
    if planned.get("baseqty") is not None:
        entry["baseqty"] = _to_float(planned.get("baseqty"))
    unit2nd = str(planned.get("unit2nd_number") or "").strip()
    if unit2nd:
        entry["unit2nd_number"] = unit2nd
    if planned.get("qtyunit2nd") is not None:
        entry["qtyunit2nd"] = _to_float(planned.get("qtyunit2nd"))


def log_billentry_dual_qty(
    *,
    doc_label: str,
    doc_code: Any,
    entries: Iterable[Any],
) -> None:
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        logger.info(
            "{} cosmic entry dual-qty code={} material={} "
            "qty={} unit={} qtyunit2nd={} unit2nd={}",
            doc_label,
            doc_code,
            entry.get("material_number"),
            entry.get("qty"),
            entry.get("unit_number"),
            entry.get("qtyunit2nd"),
            entry.get("unit2nd_number"),
        )


async def resolve_warehouse_bill_line_unit_qty(
    tenant_id: int,
    items: Sequence[Any],
    *,
    quantity_field: QuantityField,
    scene_label: str,
    unit_code_map: Optional[Dict[str, Any]] = None,
    config_unit_number: Optional[str] = None,
) -> Dict[int, Dict[str, Any]]:
    """按行解析推送库存单位/数量与辅助单位/数量。

    Returns:
        item_id -> {unit_number, qty, baseqty?, unit2nd_number?, qtyunit2nd?}
    """
    from apps.kuaizhizao.utils.inventory_posting_utils import convert_line_to_posting_quantities
    from apps.kuaizhizao.utils.ledger_dual_quantity_utils import (
        ledger_aux_quantity_from_base,
        resolve_ledger_auxiliary_unit,
    )
    from apps.kuaizhizao.utils.material_unit_utils import resolve_material_inventory_unit
    from apps.master_data.models.material import Material

    material_ids = sorted(
        {
            int(getattr(it, "material_id", 0) or 0)
            for it in items
            if int(getattr(it, "material_id", 0) or 0) > 0
        }
    )
    materials: Dict[int, Any] = {}
    if material_ids:
        rows = await Material.filter(
            tenant_id=tenant_id,
            id__in=material_ids,
            deleted_at__isnull=True,
        )
        materials = {int(m.id): m for m in rows}

    out: Dict[int, Dict[str, Any]] = {}
    cfg_unit = str(config_unit_number or "").strip()
    for item in items:
        item_id = int(getattr(item, "id", 0) or 0)
        mat = materials.get(int(getattr(item, "material_id", 0) or 0))
        inv_ref = resolve_material_inventory_unit(mat) if mat else ""
        base_ref = str(getattr(mat, "base_unit", None) or "").strip() if mat else ""
        line_ref = str(getattr(item, "material_unit", None) or "").strip()
        unit_number = await resolve_push_unit_number(
            tenant_id,
            unit_refs=[inv_ref, base_ref, line_ref, cfg_unit],
            unit_code_map=unit_code_map,
            allow_builtin_aliases=False,
        )
        if not unit_number:
            unit_number = (
                str(cfg_unit or DEFAULT_UNIT_NUMBER).strip() or DEFAULT_UNIT_NUMBER
            )

        raw_qty = _line_quantity(item, quantity_field)
        qty = _to_float(raw_qty)
        base_qty: Optional[float] = None
        posting = None
        if mat is not None and qty > 0:
            try:
                posting = convert_line_to_posting_quantities(
                    material=mat,
                    quantity=raw_qty,
                    material_unit=getattr(item, "material_unit", None),
                    aux_quantity=getattr(item, "aux_quantity", None),
                    unit_conversion_rate=getattr(item, "unit_conversion_rate", None),
                )
                qty = float(posting.inventory_quantity)
                base_qty = float(posting.base_quantity)
            except Exception as exc:
                logger.warning(
                    "{} push qty convert failed item={} mat={} err={}",
                    scene_label,
                    item_id,
                    getattr(item, "material_code", None),
                    exc,
                )
                raise BusinessLogicError(
                    f"{scene_label}明细 {getattr(item, 'material_code', None) or item_id} "
                    f"无法换算到库存单位「{inv_ref or unit_number}」，"
                    f"请核对物料多单位与行换算率：{exc}"
                ) from exc

        plan: Dict[str, Any] = {"unit_number": unit_number, "qty": qty}
        if base_qty is not None:
            plan["baseqty"] = base_qty

        # 金蝶：物料未启用辅助单位时禁止录入 unit2nd/qtyunit2nd。
        # 行上脏 aux_*（如下推残留默认「件」）不得冒充物料辅助单位。
        from apps.kuaizhizao.utils.ledger_dual_quantity_utils import (
            resolve_material_display_auxiliary_unit,
        )

        mat_aux_ref = ""
        if mat is not None:
            mat_aux_ref = str(resolve_ledger_auxiliary_unit(mat) or "").strip()
            if not mat_aux_ref:
                mat_aux_ref = str(
                    resolve_material_display_auxiliary_unit(mat) or ""
                ).strip()
        if not mat_aux_ref:
            out[item_id] = plan
            continue

        aux_unit_ref = str(getattr(item, "aux_unit", None) or "").strip() or mat_aux_ref
        inv_unit_key = (inv_ref or base_ref or "").casefold()
        if aux_unit_ref and inv_unit_key and aux_unit_ref.casefold() == inv_unit_key:
            out[item_id] = plan
            continue

        aux_qty_raw = getattr(item, "aux_quantity", None)
        aux_qty: Optional[float] = None
        if aux_qty_raw is not None:
            aux_qty = _to_float(aux_qty_raw)
        elif (
            mat is not None
            and aux_unit_ref
            and posting is not None
            and float(posting.base_quantity) > 0
        ):
            try:
                aux_qty = float(
                    ledger_aux_quantity_from_base(mat, posting.base_quantity)
                )
            except Exception as exc:
                logger.warning(
                    "{} push aux qty convert failed item={} mat={} err={}",
                    scene_label,
                    item_id,
                    getattr(item, "material_code", None),
                    exc,
                )
                raise BusinessLogicError(
                    f"{scene_label}明细 {getattr(item, 'material_code', None) or item_id} "
                    f"无法换算到辅助单位「{aux_unit_ref}」：{exc}"
                ) from exc

        if aux_unit_ref and aux_qty is not None:
            unit2nd = await resolve_push_unit_number(
                tenant_id,
                unit_refs=[aux_unit_ref],
                unit_code_map=unit_code_map,
                allow_builtin_aliases=False,
            )
            if unit2nd:
                plan["unit2nd_number"] = unit2nd
                plan["qtyunit2nd"] = aux_qty

        out[item_id] = plan
    return out
