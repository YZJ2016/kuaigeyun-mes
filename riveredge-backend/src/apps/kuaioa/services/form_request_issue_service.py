"""会签申请下发（L54 与 L53 交付物下发同策略）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from tortoise.transactions import in_transaction

from apps.kuaioa.constants.form_request_issue import FORM_REQUEST_ISSUE_TARGET_TYPES
from apps.kuaioa.models.form_request import KuaioaFormRequest
from apps.kuaioa.models.form_request_issue import KuaioaFormRequestIssueGrant
from apps.kuaioa.schemas.forms import (
    FormRequestIssueGrantInput,
    FormRequestIssueRequest,
)
from apps.kuaioa.utils.form_request_issue_access import (
    business_type_requires_issue_scope,
    compute_form_request_capabilities,
    load_user_role_ids,
    user_can_view_form_request_row,
    user_maintains_form_requests,
)
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.models.user import User


async def grants_by_request_ids(
    tenant_id: int, request_ids: Sequence[int]
) -> Dict[int, List[KuaioaFormRequestIssueGrant]]:
    if not request_ids:
        return {}
    rows = await KuaioaFormRequestIssueGrant.filter(
        tenant_id=tenant_id,
        request_id__in=list(request_ids),
        deleted_at__isnull=True,
    ).all()
    out: Dict[int, List[KuaioaFormRequestIssueGrant]] = {}
    for row in rows:
        out.setdefault(int(row.request_id), []).append(row)
    return out


def issue_grant_dicts(grants: Sequence[KuaioaFormRequestIssueGrant]) -> List[dict[str, Any]]:
    return [
        {
            "target_type": g.target_type,
            "target_id": g.target_id,
            "target_label": g.target_label,
        }
        for g in grants
    ]


async def enrich_form_request_item(
    item: dict[str, Any],
    row: KuaioaFormRequest,
    *,
    grants: Sequence[KuaioaFormRequestIssueGrant],
    current_user_id: Optional[int],
    permission_codes: Optional[Sequence[str]],
    role_ids: Optional[Sequence[int]] = None,
    department_id: Optional[int] = None,
    include_grants: bool = False,
) -> dict[str, Any]:
    can_view = await user_can_view_form_request_row(
        row,
        user_id=current_user_id,
        permission_codes=permission_codes,
        grants=grants,
        role_ids=role_ids,
        department_id=department_id,
    )
    caps = compute_form_request_capabilities(
        row,
        can_view_row=can_view,
        permission_codes=permission_codes,
        user_id=current_user_id,
    )
    item["capabilities"] = caps
    if include_grants:
        item["issue_grants"] = issue_grant_dicts(grants)
    return item


async def filter_visible_form_requests(
    rows: Sequence[KuaioaFormRequest],
    *,
    tenant_id: int,
    current_user_id: Optional[int],
    permission_codes: Optional[Sequence[str]],
) -> List[KuaioaFormRequest]:
    if current_user_id is None or user_maintains_form_requests(permission_codes):
        return list(rows)
    role_ids = await load_user_role_ids(current_user_id)
    user_row = await User.get_or_none(id=current_user_id)
    department_id = getattr(user_row, "department_id", None) if user_row else None
    grant_map = await grants_by_request_ids(
        tenant_id, [int(r.id) for r in rows if r.id is not None]
    )
    visible: List[KuaioaFormRequest] = []
    for row in rows:
        grants = grant_map.get(int(row.id), [])
        if await user_can_view_form_request_row(
            row,
            user_id=current_user_id,
            permission_codes=permission_codes,
            grants=grants,
            role_ids=role_ids,
            department_id=department_id,
        ):
            visible.append(row)
    return visible


async def clear_form_request_issue(tenant_id: int, request_id: int) -> None:
    now = resolve_business_datetime()
    await KuaioaFormRequestIssueGrant.filter(
        tenant_id=tenant_id,
        request_id=request_id,
        deleted_at__isnull=True,
    ).update(deleted_at=now)
    row = await KuaioaFormRequest.get_or_none(id=request_id, tenant_id=tenant_id)
    if row:
        row.issued_at = None
        row.issued_by = None
        row.issued_by_name = None
        await row.save()


async def issue_form_request(
    tenant_id: int,
    request_id: int,
    data: FormRequestIssueRequest,
    current_user: User,
    *,
    permission_codes: Sequence[str],
) -> dict[str, Any]:
    row = await KuaioaFormRequest.get_or_none(
        id=request_id, tenant_id=tenant_id, deleted_at__isnull=True
    )
    if not row:
        raise NotFoundError("申请单不存在")
    if (row.status or "").strip().lower() != "approved":
        raise BusinessLogicError("仅已批准申请单可下发")
    if not business_type_requires_issue_scope(row.business_type):
        raise BusinessLogicError("该业务类型无需单独下发")

    grant_inputs = data.normalized_grants()
    from core.models.role import Role

    for role_uuid in data.role_uuids:
        ru = (role_uuid or "").strip()
        if not ru:
            continue
        role = await Role.get_or_none(tenant_id=tenant_id, uuid=ru)
        if not role:
            raise ValidationError(f"角色不存在: {role_uuid}")
        grant_inputs.append(
            FormRequestIssueGrantInput(
                target_type="role",
                target_id=int(role.id),
                target_label=role.name,
            )
        )
    if not grant_inputs:
        raise ValidationError("须至少选择一个下发对象")

    now = resolve_business_datetime()
    actor_name = getattr(current_user, "name", None) or getattr(current_user, "username", None)
    async with in_transaction():
        await clear_form_request_issue(tenant_id, request_id)
        row = await KuaioaFormRequest.get_or_none(
            id=request_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("申请单不存在")
        for item in grant_inputs:
            t = (item.target_type or "").strip().lower()
            if t not in FORM_REQUEST_ISSUE_TARGET_TYPES:
                raise ValidationError(f"非法下发对象类型: {item.target_type}")
            label = (item.target_label or "").strip() or None
            if t == "user" and not label:
                user = await User.get_or_none(id=int(item.target_id))
                label = getattr(user, "name", None) or getattr(user, "username", None)
            await KuaioaFormRequestIssueGrant.create(
                tenant_id=tenant_id,
                request_id=request_id,
                target_type=t,
                target_id=int(item.target_id),
                target_label=label,
            )
        row.issued_at = now
        row.issued_by = current_user.id
        row.issued_by_name = actor_name
        await row.save()

    grants = await KuaioaFormRequestIssueGrant.filter(
        tenant_id=tenant_id,
        request_id=request_id,
        deleted_at__isnull=True,
    ).all()
    from apps.kuaioa.services.kuaioa_list_core import model_to_dict

    item = model_to_dict(row)
    return await enrich_form_request_item(
        item,
        row,
        grants=grants,
        current_user_id=current_user.id,
        permission_codes=permission_codes,
        include_grants=True,
    )
