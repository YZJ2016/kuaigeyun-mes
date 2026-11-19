"""开口行取单：同申请同物料的建议、已转、可取数量。"""

from typing import Any, Optional, Tuple


def requisition_material_group_key(
    requisition_id: Any,
    material_id: Any,
    *,
    fallback_item_id: Optional[int] = None,
) -> Tuple[int, int]:
    """无物料 ID 的行单独分组，避免不同物料的数量合并。"""
    rid = int(requisition_id or 0)
    mid = int(material_id or 0)
    if mid > 0:
        return rid, mid
    if fallback_item_id is not None and int(fallback_item_id) > 0:
        return rid, -int(fallback_item_id)
    return rid, 0


def build_partial_push_qty_triplet(
    suggested: Any,
    occupied_pushed: Any,
    *,
    line_fully_pushed: bool = False,
) -> Tuple[float, float, float]:
    """分批占用按实际下游数量计算，不以挂链代替占用。"""
    sug = float(suggested or 0)
    if line_fully_pushed:
        return sug, sug, 0.0
    pushed = min(sug, float(occupied_pushed or 0))
    return sug, pushed, max(0.0, sug - pushed)
