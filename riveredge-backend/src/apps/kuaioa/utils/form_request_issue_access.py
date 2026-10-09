"""会签申请下发可见性与能力标记（L54）。"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, Sequence

from apps.kuaioa.constants.form_request_issue import (
    FORM_REQUEST_BUSINESS_TYPES_ISSUE_SCOPED,
    FORM_REQUEST_ISSUE_ATTACHMENT_FIELD_BY_BUSINESS,
    FORM_REQUEST_ISSUE_TARGET_DEPARTMENT,
    FORM_REQUEST_ISSUE_TARGET_ROLE,
    FORM_REQUEST_ISSUE_TARGET_USER,
    MAINTAINER_PERMISSION_CODES,
)
from apps.kuaioa.models.form_request import KuaioaFormRequest
from apps.kuaioa.models.form_request_issue import KuaioaFormRequestIssueGrant
from apps.kuaioa.utils.form_request_confirmation import (
    CONFIRMATION_KIND_COMPLETE_MACHINE,
    CONFIRMATION_KIND_MATERIAL,
    confirmation_has_sales_reply,
    confirmation_kind_from_form_data,
    confirmation_uploaded_flag,
)
from apps.kuaioa.utils.form_request_material_issue import (
    material_issue_content_ready,
    material_issue_has_countersign_targets,
    user_is_material_issue_countersign_participant,
)
from apps.kuaioa.utils.form_request_review_sheet import (
    review_sheet_content_ready,
    review_sheet_has_countersign_targets,
    user_is_review_sheet_countersign_participant,
)
from core.models.user_role import UserRole
from infra.models.user import User


def business_type_requires_issue_scope(business_type: Optional[str]) -> bool:
    return (business_type or "").strip().lower() in FORM_REQUEST_BUSINESS_TYPES_ISSUE_SCOPED


def resolve_attachment_field(business_type: Optional[str]) -> Optional[str]:
    code = (business_type or "").strip().lower()
    return FORM_REQUEST_ISSUE_ATTACHMENT_FIELD_BY_BUSINESS.get(code)


def form_data_has_attachment(row: KuaioaFormRequest) -> bool:
    bt = (row.business_type or "").strip().lower()
    fd = row.form_data if isinstance(row.form_data, dict) else {}
    if bt == "confirmation":
        return confirmation_uploaded_flag(fd, business_type=row.business_type)
    if bt == "review_sheet":
        field_name = resolve_attachment_field(row.business_type)
        if field_name:
            raw = fd.get(field_name)
            if isinstance(raw, str) and raw.strip():
                return True
            if isinstance(raw, dict):
                uuid_val = raw.get("uuid") or raw.get("file_uuid")
                if isinstance(uuid_val, str) and uuid_val.strip():
                    return True
        return review_sheet_content_ready(fd)
    if bt == "material_issue":
        field_name = resolve_attachment_field(row.business_type)
        if field_name:
            raw = fd.get(field_name)
            if isinstance(raw, str) and raw.strip():
                return True
            if isinstance(raw, dict):
                uuid_val = raw.get("uuid") or raw.get("file_uuid")
                if isinstance(uuid_val, str) and uuid_val.strip():
                    return True
        return material_issue_content_ready(fd)
    field_name = resolve_attachment_field(row.business_type)
    if not field_name:
        return False
    form_data = row.form_data if isinstance(row.form_data, dict) else {}
    raw = form_data.get(field_name)
    if isinstance(raw, str) and raw.strip():
        return True
    if isinstance(raw, dict):
        uuid_val = raw.get("uuid") or raw.get("file_uuid")
        if isinstance(uuid_val, str) and uuid_val.strip():
            return True
    return False


def user_maintains_form_requests(permission_codes: Optional[Iterable[str]]) -> bool:
    codes = {str(c or "").strip().lower() for c in (permission_codes or []) if str(c or "").strip()}
    return bool(codes.intersection(MAINTAINER_PERMISSION_CODES))


def user_matches_issue_grants(
    *,
    user_id: int,
    role_ids: Sequence[int],
    department_id: Optional[int],
    grants: Sequence[KuaioaFormRequestIssueGrant],
) -> bool:
    for grant in grants:
        t = (grant.target_type or "").strip().lower()
        if t == FORM_REQUEST_ISSUE_TARGET_USER and grant.target_id == user_id:
            return True
        if t == FORM_REQUEST_ISSUE_TARGET_ROLE and grant.target_id in role_ids:
            return True
        if (
            t == FORM_REQUEST_ISSUE_TARGET_DEPARTMENT
            and department_id is not None
            and grant.target_id == department_id
        ):
            return True
    return False


async def load_user_role_ids(user_id: int) -> List[int]:
    return list(await UserRole.filter(user_id=user_id).values_list("role_id", flat=True))


async def user_can_view_form_request_row(
    row: KuaioaFormRequest,
    *,
    user_id: Optional[int],
    permission_codes: Optional[Iterable[str]],
    grants: Sequence[KuaioaFormRequestIssueGrant],
    role_ids: Optional[Sequence[int]] = None,
    department_id: Optional[int] = None,
) -> bool:
    if not business_type_requires_issue_scope(row.business_type):
        return True
    if user_maintains_form_requests(permission_codes):
        return True
    if user_id is not None and row.applicant_id is not None and int(row.applicant_id) == int(user_id):
        return True
    if (row.business_type or "").strip().lower() == "review_sheet" and user_id is not None:
        dept_id = department_id
        if dept_id is None:
            user = await User.get_or_none(id=user_id)
            dept_id = getattr(user, "department_id", None) if user else None
        fd = row.form_data if isinstance(row.form_data, dict) else {}
        if user_is_review_sheet_countersign_participant(
            fd, user_id=user_id, department_id=dept_id
        ):
            return True
    if (row.business_type or "").strip().lower() == "material_issue" and user_id is not None:
        fd = row.form_data if isinstance(row.form_data, dict) else {}
        if user_is_material_issue_countersign_participant(fd, user_id=user_id):
            return True
    if not getattr(row, "issued_at", None):
        return False
    if user_id is None:
        return False
    roles = list(role_ids) if role_ids is not None else await load_user_role_ids(user_id)
    dept_id = department_id
    if dept_id is None:
        user = await User.get_or_none(id=user_id)
        dept_id = getattr(user, "department_id", None) if user else None
    return user_matches_issue_grants(
        user_id=user_id,
        role_ids=roles,
        department_id=dept_id,
        grants=grants,
    )


def compute_form_request_capabilities(
    row: KuaioaFormRequest,
    *,
    can_view_row: bool,
    permission_codes: Optional[Iterable[str]],
    user_id: Optional[int],
) -> dict[str, bool]:
    uploaded = form_data_has_attachment(row)
    approved = (row.status or "").strip().lower() == "approved"
    issued = getattr(row, "issued_at", None) is not None
    is_applicant = (
        user_id is not None
        and row.applicant_id is not None
        and int(row.applicant_id) == int(user_id)
    )
    form_data = row.form_data if isinstance(row.form_data, dict) else {}
    bt = (row.business_type or "").strip().lower()
    countersign_selected = False
    if bt == "review_sheet":
        countersign_selected = review_sheet_has_countersign_targets(form_data)
    elif bt == "material_issue":
        countersign_selected = material_issue_has_countersign_targets(form_data)
    responded = False
    if bt == "confirmation":
        kind = confirmation_kind_from_form_data(form_data)
        if kind == CONFIRMATION_KIND_COMPLETE_MACHINE:
            responded = confirmation_has_sales_reply(form_data)
        elif kind == CONFIRMATION_KIND_MATERIAL:
            responded = approved

    can_download = False
    download_ready = uploaded
    if (row.business_type or "").strip().lower() == "confirmation":
        kind = confirmation_kind_from_form_data(form_data)
        if kind == CONFIRMATION_KIND_COMPLETE_MACHINE and approved and responded:
            download_ready = True
        elif kind == CONFIRMATION_KIND_MATERIAL:
            download_ready = uploaded

    if download_ready and approved:
        if business_type_requires_issue_scope(row.business_type):
            if user_maintains_form_requests(permission_codes) or is_applicant:
                can_download = True
            else:
                can_download = issued and can_view_row
        elif can_view_row:
            can_download = True
    return {
        "uploaded": uploaded,
        "approved": approved,
        "issued": issued,
        "can_download": can_download,
        "responded": responded,
        "countersign_selected": countersign_selected,
    }
