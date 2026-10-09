"""评审单（L56）校验与会签对象解析。"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

from infra.exceptions.exceptions import BusinessLogicError


def _parse_int_list(raw: Any) -> List[int]:
    if raw is None:
        return []
    if isinstance(raw, list):
        out: List[int] = []
        for item in raw:
            if isinstance(item, dict):
                item = item.get("id")
            try:
                n = int(item)
            except (TypeError, ValueError):
                continue
            if n > 0:
                out.append(n)
        return out
    try:
        n = int(raw)
        return [n] if n > 0 else []
    except (TypeError, ValueError):
        return []


def countersign_department_ids(form_data: Optional[dict[str, Any]]) -> List[int]:
    data = form_data or {}
    return _parse_int_list(data.get("countersign_department_ids"))


def countersign_user_ids(form_data: Optional[dict[str, Any]]) -> List[int]:
    data = form_data or {}
    return _parse_int_list(data.get("countersign_user_ids"))


def review_sheet_has_countersign_targets(form_data: Optional[dict[str, Any]]) -> bool:
    return bool(countersign_department_ids(form_data) or countersign_user_ids(form_data))


def review_sheet_content_ready(form_data: Optional[dict[str, Any]]) -> bool:
    data = form_data or {}
    subject = str(data.get("review_subject") or "").strip()
    content = str(data.get("review_content") or "").strip()
    rtype = str(data.get("review_type") or "").strip()
    return bool(subject and content and rtype)


def validate_review_sheet_on_submit(form_data: dict[str, Any] | None) -> None:
    data = form_data or {}
    if not review_sheet_content_ready(data):
        raise BusinessLogicError("评审单须填写评审类型、主题与内容")
    if not review_sheet_has_countersign_targets(data):
        raise BusinessLogicError("须至少勾选一个参与会签部门或人员")


def user_is_review_sheet_countersign_participant(
    form_data: Optional[dict[str, Any]],
    *,
    user_id: Optional[int],
    department_id: Optional[int],
) -> bool:
    if user_id is None:
        return False
    data = form_data or {}
    if user_id in countersign_user_ids(data):
        return True
    if department_id is not None and department_id in countersign_department_ids(data):
        return True
    return False
