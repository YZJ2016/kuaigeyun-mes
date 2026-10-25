"""维保/保养单据完修时写明细执行结果（工装、模具共用）。"""

from __future__ import annotations

from typing import Any, List, Sequence

from infra.exceptions.exceptions import ValidationError


async def apply_maintenance_line_execution_on_complete(
    existing_lines: Sequence[Any],
    inputs: Sequence[Any],
    *,
    detail_noun: str = "保养",
) -> None:
    if not existing_lines:
        return
    if not inputs:
        raise ValidationError(f"完修须提交{detail_noun}明细执行结果")
    by_line_no = {int(getattr(row, "line_no", 0) or 0): row for row in existing_lines}
    seen: set[int] = set()
    for inp in inputs:
        line_no = int(getattr(inp, "line_no", 0) or 0)
        if line_no <= 0 or line_no not in by_line_no:
            raise ValidationError(f"{detail_noun}明细行 {line_no} 不存在")
        seen.add(line_no)
        row = by_line_no[line_no]
        row.is_done = bool(getattr(inp, "is_done", False))
        remark = getattr(inp, "remark", None)
        if remark is not None:
            row.remark = remark
        await row.save()
    missing = set(by_line_no.keys()) - seen
    if missing:
        raise ValidationError(f"完修须提交全部{detail_noun}明细行")
    for row in existing_lines:
        if not bool(getattr(row, "is_done", False)):
            raise ValidationError(f"尚有{detail_noun}项未执行，请全部勾选后再完修")
