"""确认书（L55）表单校验与能力辅助。"""

from __future__ import annotations

from typing import Any, Optional

from infra.exceptions.exceptions import BusinessLogicError

CONFIRMATION_KIND_COMPLETE_MACHINE = "complete_machine"
CONFIRMATION_KIND_MATERIAL = "material"


def confirmation_kind_from_form_data(form_data: Optional[dict[str, Any]]) -> str:
    data = form_data or {}
    return str(data.get("confirmation_kind") or "").strip().lower()


def confirmation_has_attachment(form_data: Optional[dict[str, Any]]) -> bool:
    data = form_data or {}
    raw = data.get("confirmation_attachment")
    if isinstance(raw, str) and raw.strip():
        return True
    if isinstance(raw, dict):
        uuid_val = raw.get("uuid") or raw.get("file_uuid")
        if isinstance(uuid_val, str) and uuid_val.strip():
            return True
    return False


def confirmation_content_ready(form_data: Optional[dict[str, Any]]) -> bool:
    data = form_data or {}
    subject = str(data.get("confirmation_subject") or "").strip()
    content = str(data.get("confirmation_content") or "").strip()
    return bool(subject and content)


def confirmation_has_sales_reply(form_data: Optional[dict[str, Any]]) -> bool:
    data = form_data or {}
    return bool(str(data.get("confirmation_result") or "").strip())


def validate_confirmation_on_submit(form_data: dict[str, Any] | None) -> None:
    data = form_data or {}
    kind = confirmation_kind_from_form_data(data)
    if kind == CONFIRMATION_KIND_MATERIAL:
        if not confirmation_has_attachment(data):
            raise BusinessLogicError("材料确认须上传确认书附件")
        if not confirmation_has_sales_reply(data):
            raise BusinessLogicError("材料确认须填写确认结论")
    elif kind == CONFIRMATION_KIND_COMPLETE_MACHINE:
        if not confirmation_content_ready(data):
            raise BusinessLogicError("整机确认须填写确认主题与确认内容")
    else:
        raise BusinessLogicError("须选择确认书类型")


def confirmation_uploaded_flag(form_data: Optional[dict[str, Any]], *, business_type: Optional[str]) -> bool:
    if (business_type or "").strip().lower() != "confirmation":
        return False
    kind = confirmation_kind_from_form_data(form_data)
    if kind == CONFIRMATION_KIND_MATERIAL:
        return confirmation_has_attachment(form_data)
    if kind == CONFIRMATION_KIND_COMPLETE_MACHINE:
        return confirmation_content_ready(form_data)
    return False
