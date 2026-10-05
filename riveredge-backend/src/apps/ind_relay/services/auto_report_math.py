"""继电器自动报工：产量增量与数量分摊（无 IO，便于单测）。"""

from __future__ import annotations

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
