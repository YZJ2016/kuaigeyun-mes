"""继电器自动报工：产量增量与数量分摊（无 IO，便于单测）。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, Sequence

ZERO = Decimal("0")


def compute_zscl_increment(
    current: Optional[Decimal],
    last: Optional[Decimal],
) -> tuple[str, Decimal]:
    """
    根据累计产量算出本次增量。

    返回 (reason, qty)：
    - missing: 无当前值
    - baseline: 尚无上次基线（调用方应对齐、不报工）
    - zero: 无增量
    - reset: 当前 < 上次（清零重启），把当前值当增量
    - increment: 正常差额
    """
    if current is None:
        return "missing", ZERO
    if last is None:
        return "baseline", ZERO
    if current < last:
        return "reset", current
    delta = current - last
    if delta <= ZERO:
        return "zero", ZERO
    return "increment", delta


def allocate_increment(
    increment: Decimal,
    remainings: Sequence[Decimal],
    *,
    last_takes_overflow: bool = True,
) -> list[Decimal]:
    """
    按任务顺序分摊增量：前面填到 remaining，末张可吃尾量（允许超计划）。
    返回与 remainings 等长的本次分配量。
    """
    qty = increment if increment > ZERO else ZERO
    n = len(remainings)
    allocated = [ZERO] * n
    if n == 0 or qty <= ZERO:
        return allocated
    leftover = qty
    for i, remaining in enumerate(remainings):
        is_last = i == n - 1
        cap = remaining if remaining > ZERO else ZERO
        if is_last and last_takes_overflow:
            take = leftover
        else:
            take = leftover if leftover <= cap else cap
        if take < ZERO:
            take = ZERO
        allocated[i] = take
        leftover -= take
        if leftover <= ZERO:
            break
    return allocated


def planned_start_ts(value: Optional[datetime]) -> float:
    if value is None:
        return 0.0
    try:
        return float(value.timestamp())
    except (OSError, OverflowError, TypeError, ValueError):
        return 0.0


def equipment_in_default_ids(raw: object, equipment_id: int) -> bool:
    """工序主数据 default_equipment_ids 是否包含该 MES 设备。"""
    if raw is None or not isinstance(raw, (list, tuple)):
        return False
    for item in raw:
        try:
            if int(item) == int(equipment_id):
                return True
        except (TypeError, ValueError):
            continue
    return False


def candidate_bind_sort_key(
    status_rank: int,
    planned_start: Optional[datetime],
    wo_id: int,
) -> tuple:
    """生产中优先；同状态计划开始越新越优先；再 id 越大越优先。"""
    return (int(status_rank), -planned_start_ts(planned_start), -int(wo_id or 0))


def candidate_fill_sort_key(
    planned_start: Optional[datetime],
    wo_id: int,
) -> tuple:
    """同产品连做：先填计划开始更早的工单。"""
    ts = planned_start_ts(planned_start)
    return (0 if ts else 1, ts, int(wo_id or 0))


def should_changeover(
    *,
    has_bound: bool,
    bound_still_candidate: bool,
    bound_in_progress: bool,
    bound_product_id: Optional[int],
    best_in_progress: bool,
    best_wo_id: int,
    best_product_id: Optional[int],
    bound_wo_id: int,
) -> bool:
    """产品变了、旧任务已不在候选、或旧单不再生产中而新单已生产中 → 切单。"""
    if not has_bound:
        return False
    if not bound_still_candidate:
        return True
    if bound_product_id != best_product_id:
        return True
    if (
        (not bound_in_progress)
        and best_in_progress
        and int(best_wo_id) != int(bound_wo_id)
    ):
        return True
    return False
