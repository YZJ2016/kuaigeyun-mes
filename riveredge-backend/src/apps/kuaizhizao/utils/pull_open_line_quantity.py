"""
开口行取单数量契约：主/副 suggested、pushed、remaining。

可勾选仍只认主数量 remaining_quantity > 0；副数量并行汇总占用，禁止从主剩余比例反推副剩余。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from pydantic import Field

from core.schemas.base import BaseSchema


def _f(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _d(val: Any) -> Decimal:
    try:
        return Decimal(str(val if val is not None else 0))
    except Exception:
        return Decimal("0")


def _optional_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    d = _d(val)
    if d <= 0:
        return None
    return float(d)


def remaining_qty(suggested: Any, pushed: Any) -> float:
    return max(0.0, _f(suggested) - _f(pushed))


def requisition_material_group_key(
    requisition_id: Any,
    material_id: Any,
    *,
    fallback_item_id: Optional[int] = None,
) -> Tuple[int, int]:
    """同一采购申请下同物料拆分行共用副数量占用汇总（fallback_item_id 隔离无物料 id 的行）。"""
    rid = int(requisition_id or 0)
    mid = int(material_id or 0)
    if mid > 0:
        return rid, mid
    if fallback_item_id is not None and int(fallback_item_id) > 0:
        return rid, -int(fallback_item_id)
    return rid, 0


def sum_suggested_aux_for_requisition_material_items(
    items: List[Any],
) -> Tuple[Optional[float], Optional[str]]:
    """同申请同物料多行（含部分转单拆行）副建议量相加，单位取首行有效副单位。"""
    total = 0.0
    aux_unit: Optional[str] = None
    has_aux = False
    for item in items:
        aux_sug, unit = read_line_aux_pair(item)
        if not unit:
            continue
        has_aux = True
        if aux_unit is None:
            aux_unit = unit
        if aux_sug is not None:
            total += _f(aux_sug)
    if not has_aux or not aux_unit:
        return None, None
    return total, aux_unit


def resolve_requisition_material_aux_triplet(
    *,
    group_items: List[Any],
    occupied_aux_by_item_id: Dict[int, Any],
    line_fully_pushed: bool = False,
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[str]]:
    """
    拆行后开口取单展示：副建议量按同物料各行相加，已转副量按各行 source 占用相加。
    与主数量同组汇总口径一致（申请量不因拆行变小）。
    例：主2副10 拆为 5+5，PO 占副6 → 建议10 / 已转6 / 可取4。
    """
    suggested, aux_unit = sum_suggested_aux_for_requisition_material_items(group_items)
    if aux_unit is None or suggested is None:
        return None, None, None, None
    occupied = Decimal("0")
    for item in group_items:
        iid = int(getattr(item, "id", 0) or 0)
        if iid <= 0:
            continue
        occupied += _d(occupied_aux_by_item_id.get(iid, 0))
    triplet = build_partial_push_aux_triplet(
        suggested,
        float(occupied),
        line_fully_pushed=line_fully_pushed,
    )
    return triplet[0], triplet[1], triplet[2], aux_unit


def read_line_aux_pair(source: Any) -> Tuple[Optional[float], Optional[str]]:
    """源行副数量与副单位；无副单位则不输出副三元组。有副单位但未填副数量按 0 计（取单展示用）。"""
    aux_unit_raw = getattr(source, "aux_unit", None)
    aux_unit = str(aux_unit_raw).strip() if aux_unit_raw is not None else ""
    if not aux_unit:
        return None, None
    raw = getattr(source, "aux_quantity", None)
    if raw is None:
        return 0.0, aux_unit
    return max(0.0, _f(raw)), aux_unit


def build_pull_open_qty_source(line_item: Any, material: Any = None) -> Any:
    """取单 enrich：行 aux 快照优先；副单位名可回落物料台账展示辅助单位（不算占用、不按主数量反推副量）。"""
    from types import SimpleNamespace

    aux_unit = str(getattr(line_item, "aux_unit", None) or "").strip()
    if not aux_unit and material is not None:
        from apps.kuaizhizao.utils.ledger_dual_quantity_utils import (
            resolve_material_display_auxiliary_unit,
        )

        aux_unit = str(resolve_material_display_auxiliary_unit(material) or "").strip()
    return SimpleNamespace(
        aux_unit=aux_unit or None,
        aux_quantity=getattr(line_item, "aux_quantity", None),
    )


def build_partial_push_qty_triplet(
    suggested: Any,
    occupied_pushed: Any,
    *,
    line_fully_pushed: bool = False,
) -> Tuple[float, float, float]:
    """分批占用：pushed = min(suggested, occupied)；remaining = suggested - pushed。"""
    sug = _f(suggested)
    if line_fully_pushed:
        return sug, sug, 0.0
    occ = _f(occupied_pushed)
    pushed = min(sug, occ)
    rem = max(0.0, sug - pushed)
    return sug, pushed, rem


def dual_quantity_for_open_requisition_push(
    source_item: Any,
    *,
    group_items: List[Any],
    occupied_aux_by_item_id: Dict[int, Any],
    push_primary_qty: Any,
    line_remaining_primary: Any,
) -> Dict[str, Any]:
    """
    采购申请开口行 → 采购订单 create 载荷的副数量。

    取单列表的副可取按同申请同物料组汇总（含拆行）；禁止仅用当前拆行 aux×(本次主/行主) 比例缩放，
    否则第二次转单会出现 30 而非 110−88=22。
    """
    from apps.kuaizhizao.utils.material_dual_quantity_utils import (
        document_line_dual_quantity_for_push,
    )

    rate = getattr(source_item, "unit_conversion_rate", None)
    _, _, group_aux_rem, aux_unit_triplet = resolve_requisition_material_aux_triplet(
        group_items=group_items,
        occupied_aux_by_item_id=occupied_aux_by_item_id,
    )
    aux_unit_raw = getattr(source_item, "aux_unit", None) or aux_unit_triplet
    aux_unit = str(aux_unit_raw).strip() if aux_unit_raw is not None else ""
    if group_aux_rem is None:
        return document_line_dual_quantity_for_push(
            source_item,
            source_primary_qty=line_remaining_primary,
            push_primary_qty=push_primary_qty,
        )
    push = _d(push_primary_qty)
    rem = _d(line_remaining_primary)
    if push <= 0:
        aux = Decimal("0")
    elif rem > 0:
        aux = _d(group_aux_rem) * push / rem
    else:
        aux = _d(group_aux_rem)
    return {
        "aux_quantity": aux,
        "aux_unit": aux_unit or None,
        "unit_conversion_rate": rate,
    }


def build_partial_push_aux_triplet(
    suggested_aux: Optional[float],
    occupied_aux_pushed: Any,
    *,
    line_fully_pushed: bool = False,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if suggested_aux is None:
        return None, None, None
    sug = _f(suggested_aux)
    if line_fully_pushed:
        return sug, sug, 0.0
    occ = _f(occupied_aux_pushed)
    pushed = min(sug, occ)
    rem = max(0.0, sug - pushed)
    return sug, pushed, rem


def compose_pushed_aux_qty(
    *,
    confirmed_receipt_aux: Any,
    pending_receipt_aux: Any,
    confirmed_returned_aux: Any = 0,
) -> float:
    """已转副数量：已入库副数量 + 待入库占用副数量 − 已确认退货副数量。

    口径与已转主数量（已确认入库 − 已确认退货 + 待入库占用）一一对应。
    分批入库第二次取单时，已入库那批的副数量必须计入，否则副已转退回 0、
    副可取退回全量，第二次转入的副数量就错了。
    """
    total = _f(confirmed_receipt_aux) + _f(pending_receipt_aux) - _f(confirmed_returned_aux)
    return max(0.0, total)


def build_whole_line_gate_primary_triplet(
    suggested: Any,
    *,
    already_pushed: bool,
    push_allowed: bool,
) -> Tuple[float, float, float]:
    """整行门禁（报价→订单等）：已转则全占满；允许则全剩余；否则全 0。"""
    qty = _f(suggested)
    if already_pushed:
        return qty, qty, 0.0
    if push_allowed:
        return qty, 0.0, qty
    return qty, 0.0, 0.0


def build_whole_line_gate_aux_triplet(
    suggested_aux: Optional[float],
    *,
    already_pushed: bool,
    push_allowed: bool,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if suggested_aux is None:
        return None, None, None
    aux = _f(suggested_aux)
    if already_pushed:
        return aux, aux, 0.0
    if push_allowed:
        return aux, 0.0, aux
    return aux, 0.0, 0.0


def merge_pull_open_line_qty_fields(
    target: Dict[str, Any],
    *,
    suggested_primary: float,
    pushed_primary: float,
    remaining_primary: float,
    suggested_aux: Optional[float] = None,
    pushed_aux: Optional[float] = None,
    remaining_aux: Optional[float] = None,
    aux_unit: Optional[str] = None,
) -> Dict[str, Any]:
    target["suggested_quantity"] = suggested_primary
    target["pushed_quantity"] = pushed_primary
    target["remaining_quantity"] = remaining_primary
    if aux_unit:
        target["aux_unit"] = aux_unit
        if suggested_aux is not None:
            target["suggested_aux_quantity"] = suggested_aux
        if pushed_aux is not None:
            target["pushed_aux_quantity"] = pushed_aux
        if remaining_aux is not None:
            target["remaining_aux_quantity"] = remaining_aux
    return target


def apply_pull_open_aux_from_pushable_map(
    line: Dict[str, Any],
    source_item: Any,
    *,
    suggested_primary: float,
    pushed_primary: float,
    remaining_primary: float,
    pushable_aux: Optional[float] = None,
) -> Dict[str, Any]:
    """主三元组已由 pushable 算好；副三元组由 pushable_aux 镜像（销售出库等）。"""
    merge_pull_open_line_qty_fields(
        line,
        suggested_primary=suggested_primary,
        pushed_primary=pushed_primary,
        remaining_primary=remaining_primary,
    )
    aux_sug, aux_unit = read_line_aux_pair(source_item)
    if not aux_unit or aux_sug is None:
        return line
    if pushable_aux is None:
        pushable_aux = aux_sug
    sug = float(aux_sug)
    rem = max(0.0, float(pushable_aux))
    pushed = max(0.0, sug - rem)
    return merge_pull_open_line_qty_fields(
        line,
        suggested_primary=suggested_primary,
        pushed_primary=pushed_primary,
        remaining_primary=remaining_primary,
        suggested_aux=sug,
        pushed_aux=pushed,
        remaining_aux=rem,
        aux_unit=aux_unit,
    )


def enrich_pull_line_from_source_item(
    target: Dict[str, Any],
    source_item: Any,
    *,
    pushed_primary: float,
    remaining_primary: float,
    suggested_primary: float,
    occupied_aux_pushed: Any = 0,
    line_fully_pushed: bool = False,
    already_pushed: Optional[bool] = None,
    push_allowed: Optional[bool] = None,
    suggested_aux_override: Optional[float] = None,
    aux_unit_override: Optional[str] = None,
) -> Dict[str, Any]:
    """在已有主三元组或整行门禁参数下写入副三元组。"""
    aux_sug, aux_unit = read_line_aux_pair(source_item)
    if suggested_aux_override is not None:
        aux_sug = suggested_aux_override
    if aux_unit_override:
        aux_unit = aux_unit_override
    if already_pushed is not None and push_allowed is not None:
        aux_triplet = build_whole_line_gate_aux_triplet(
            aux_sug,
            already_pushed=bool(already_pushed),
            push_allowed=bool(push_allowed),
        )
    else:
        aux_triplet = build_partial_push_aux_triplet(
            aux_sug,
            occupied_aux_pushed,
            line_fully_pushed=line_fully_pushed,
        )
    return merge_pull_open_line_qty_fields(
        target,
        suggested_primary=suggested_primary,
        pushed_primary=pushed_primary,
        remaining_primary=remaining_primary,
        suggested_aux=aux_triplet[0],
        pushed_aux=aux_triplet[1],
        remaining_aux=aux_triplet[2],
        aux_unit=aux_unit,
    )


class PullOpenLineQuantitySchemaMixin(BaseSchema):
    """开口行数量块（主 + 可选副）。"""

    suggested_quantity: float = Field(0, description="源单数量（主）")
    pushed_quantity: float = Field(0, description="已转数量（主）")
    remaining_quantity: float = Field(0, description="可取数量（主）")
    suggested_aux_quantity: Optional[float] = Field(None, description="源单副数量")
    pushed_aux_quantity: Optional[float] = Field(None, description="已转副数量")
    remaining_aux_quantity: Optional[float] = Field(None, description="可取副数量")
    aux_unit: Optional[str] = Field(None, max_length=20, description="副单位")


def sum_aux_by_source_id(
    rows: List[Any],
    source_id_attr: str,
    aux_qty_attr: str = "aux_quantity",
    *,
    filter_fn: Optional[Any] = None,
) -> Dict[int, Decimal]:
    out: Dict[int, Decimal] = {}
    for row in rows:
        if filter_fn is not None and not filter_fn(row):
            continue
        sid = int(getattr(row, source_id_attr, 0) or 0)
        if sid <= 0:
            continue
        aux = getattr(row, aux_qty_attr, None)
        if aux is None:
            continue
        out[sid] = out.get(sid, Decimal("0")) + _d(aux)
    return out