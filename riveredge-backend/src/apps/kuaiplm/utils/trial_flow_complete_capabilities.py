"""整机试流/试生产报告（L61）列表进度勾选。"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence


def _ext(payload: Any, key: str) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get(key) or "").strip()


def complete_trial_content_ready(
    *,
    title: Optional[str],
    extension_payload: Any,
    material_line_count: int,
) -> bool:
    if not (title or "").strip():
        return False
    if material_line_count < 1:
        return False
    if not _ext(extension_payload, "trial_reason"):
        return False
    if not _ext(extension_payload, "sample_management"):
        return False
    return True


def validate_complete_trial_on_submit(
    *,
    title: Optional[str],
    extension_payload: Any,
    material_line_count: int,
) -> None:
    from infra.exceptions.exceptions import ValidationError

    if not (title or "").strip():
        raise ValidationError("试验名称不能为空")
    if material_line_count < 1:
        raise ValidationError("提交前须至少一行试流物料")
    if not _ext(extension_payload, "trial_reason"):
        raise ValidationError("整机试流须填写提出原因")
    if not _ext(extension_payload, "sample_management"):
        raise ValidationError("整机试流须填写样品管理")


def _steps_done(steps: Sequence[Any]) -> bool:
    if not steps:
        return False
    return all((getattr(s, "status", None) or "").strip().lower() == "done" for s in steps)


def compute_trial_flow_complete_capabilities(
    row: Any,
    *,
    steps: Iterable[Any],
    material_line_count: int = 0,
) -> dict[str, bool]:
    """L61 列表勾选：填报、审过、工序结果、部门结论、存档。"""
    bt = (getattr(row, "business_type", None) or "").strip().lower()
    if bt != "complete":
        return {}
    status = (getattr(row, "status", None) or "").strip().lower()
    filled = complete_trial_content_ready(
        title=getattr(row, "title", None),
        extension_payload=getattr(row, "extension_payload", None),
        material_line_count=material_line_count,
    )
    dept_approved = status not in {"draft", "pending"} and bool(
        getattr(row, "submitted_at", None)
    )
    step_list = list(steps)
    process_steps = [s for s in step_list if not str(getattr(s, "step_key", "")).startswith("conclusion_")]
    conclusion_steps = [s for s in step_list if str(getattr(s, "step_key", "")).startswith("conclusion_")]
    results_done = _steps_done(process_steps)
    if conclusion_steps:
        conclusions_done = _steps_done(conclusion_steps)
    else:
        conclusions_done = status in {"concluded", "closed"}
    archived = status == "closed" or getattr(row, "closed_at", None) is not None
    return {
        "filled": filled,
        "dept_approved": dept_approved and filled,
        "results_done": results_done,
        "conclusions_done": conclusions_done,
        "archived": archived,
    }
