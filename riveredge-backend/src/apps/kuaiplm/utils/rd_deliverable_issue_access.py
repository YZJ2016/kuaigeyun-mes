"""研发交付物下发可见性与能力标记（L53/L57）。"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from apps.kuaiplm.constants.rd_deliverable_issue import (
    MAINTAINER_PERMISSION_CODES,
    RD_DELIVERABLE_ISSUE_TARGET_DEPARTMENT,
    RD_DELIVERABLE_ISSUE_TARGET_ROLE,
    RD_DELIVERABLE_ISSUE_TARGET_USER,
    RD_DELIVERABLE_TYPES_ISSUE_SCOPED,
)
from apps.kuaiplm.constants.rd_project import RdDeliverableStatus
from apps.kuaiplm.models.rd_project import RdProjectDeliverable
from apps.kuaiplm.models.rd_project_deliverable_issue import RdProjectDeliverableIssueGrant
from core.models.user_role import UserRole
from core.services.file.document_version_policy import (
    DOCUMENT_SENIOR_AUTHOR_PERMISSION,
    resolve_audience,
)
from infra.models.user import User


def deliverable_type_requires_issue_scope(deliverable_type: Optional[str]) -> bool:
    return (deliverable_type or "").strip().lower() in RD_DELIVERABLE_TYPES_ISSUE_SCOPED


def user_maintains_deliverables(permission_codes: Optional[Iterable[str]]) -> bool:
    codes = {str(c or "").strip().lower() for c in (permission_codes or []) if str(c or "").strip()}
    return bool(codes.intersection(MAINTAINER_PERMISSION_CODES))


def user_has_global_document_view(permission_codes: Optional[Iterable[str]]) -> bool:
    codes = {str(c or "").strip().lower() for c in (permission_codes or []) if str(c or "").strip()}
    return DOCUMENT_SENIOR_AUTHOR_PERMISSION in codes


def user_matches_issue_grants(
    *,
    user_id: int,
    role_ids: Sequence[int],
    department_id: Optional[int],
    grants: Sequence[RdProjectDeliverableIssueGrant],
) -> bool:
    for grant in grants:
        t = (grant.target_type or "").strip().lower()
        if t == RD_DELIVERABLE_ISSUE_TARGET_USER and grant.target_id == user_id:
            return True
        if t == RD_DELIVERABLE_ISSUE_TARGET_ROLE and grant.target_id in role_ids:
            return True
        if (
            t == RD_DELIVERABLE_ISSUE_TARGET_DEPARTMENT
            and department_id is not None
            and grant.target_id == department_id
        ):
            return True
    return False


async def load_user_role_ids(user_id: int) -> List[int]:
    return list(await UserRole.filter(user_id=user_id).values_list("role_id", flat=True))


async def user_can_view_deliverable_row(
    row: RdProjectDeliverable,
    *,
    user_id: Optional[int],
    permission_codes: Optional[Iterable[str]],
    grants: Sequence[RdProjectDeliverableIssueGrant],
    role_ids: Optional[Sequence[int]] = None,
    department_id: Optional[int] = None,
) -> bool:
    if not deliverable_type_requires_issue_scope(row.deliverable_type):
        return True
    if user_maintains_deliverables(permission_codes):
        return True
    if user_id is not None and row.created_by is not None and int(row.created_by) == int(user_id):
        return True
    if user_has_global_document_view(permission_codes):
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


def compute_deliverable_capabilities(
    row: RdProjectDeliverable,
    *,
    can_view_row: bool,
    permission_codes: Optional[Iterable[str]],
    user_id: Optional[int],
) -> dict[str, bool]:
    uploaded = bool((getattr(row, "file_uuid", None) or "").strip() or (row.file_url or "").strip())
    approved = (row.status or "").strip().upper() == RdDeliverableStatus.APPROVED.value
    issued = getattr(row, "issued_at", None) is not None
    is_author = (
        user_id is not None
        and row.created_by is not None
        and int(row.created_by) == int(user_id)
    )
    audience = resolve_audience(
        permission_codes=permission_codes,
        is_author=is_author,
    )
    can_download = False
    if uploaded and approved:
        if deliverable_type_requires_issue_scope(row.deliverable_type):
            if user_maintains_deliverables(permission_codes) or is_author or user_has_global_document_view(
                permission_codes
            ):
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
    }
