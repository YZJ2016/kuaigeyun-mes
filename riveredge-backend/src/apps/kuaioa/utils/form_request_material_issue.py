"""领料单（L60）校验与会签对象解析。"""

from __future__ import annotations

from typing import Any, Optional

from apps.kuaioa.utils.form_request_review_sheet import countersign_user_ids
from infra.exceptions.exceptions import BusinessLogicError


def material_issue_content_ready(form_data: Optional[dict[str, Any]]) -> bool:
    data = form_data or {}
    purpose = str(data.get("issue_purpose") or "").strip()
    lines = str(data.get("issue_lines") or "").strip()
    return bool(purpose and lines)


def material_issue_has_countersign_targets(form_data: Optional[dict[str, Any]]) -> bool:
    return bool(countersign_user_ids(form_data))


def validate_material_issue_on_submit(form_data: dict[str, Any] | None) -> None:
    data = form_data or {}
    if not material_issue_content_ready(data):
        raise BusinessLogicError("领料单须填写领料说明与领料明细")
    if not material_issue_has_countersign_targets(data):
        raise BusinessLogicError("须至少勾选一个会签人员（采购/销售/计划）")


def user_is_material_issue_countersign_participant(
    form_data: Optional[dict[str, Any]],
    *,
    user_id: Optional[int],
) -> bool:
    if user_id is None:
        return False
    return user_id in countersign_user_ids(form_data)
