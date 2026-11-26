"""审批组织锚点：制单人在多部门任职时发起选部门，供部门负责人解析。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.models.department import Department
from core.models.user_department_assignment import UserDepartmentAssignment
from core.services.approval.audit_submit_requirements import _iter_flow_nodes
from core.services.user.user_department_assignment_service import UserDepartmentAssignmentService
from infra.exceptions.exceptions import ValidationError


def graph_requires_hierarchy_department(raw_nodes: Any) -> bool:
    """流程是否含须按制单人部门树解析的节点（非指定部门）。"""
    for node in _iter_flow_nodes(raw_nodes):
        if str(node.get("type") or "") != "approval":
            continue
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        approver_type = str(
            data.get("approverType") or data.get("approver_type") or ""
        ).strip()
        if approver_type in ("manager", "multi_level_manager"):
            return True
        if approver_type == "department":
            scope = str(
                data.get("departmentScope") or data.get("department_scope") or "submitter"
            ).strip().lower()
            if scope != "specified":
                return True
    return False


async def _document_department_id(
    tenant_id: int,
    entity_type: str,
    entity_id: int,
) -> Optional[int]:
    from core.services.approval.approval_document_view import DOCUMENT_LOADERS, _to_plain

    loader = DOCUMENT_LOADERS.get((entity_type or "").strip())
    if not loader:
        return None
    try:
        obj = await loader(tenant_id, int(entity_id))
        plain = _to_plain(obj)
    except Exception:
        return None
    if not isinstance(plain, dict):
        return None
    for key in ("department_id", "pick_department_id"):
        raw = plain.get(key)
        try:
            did = int(raw)
        except (TypeError, ValueError):
            continue
        if did > 0:
            return did
    return None


def _dept_option_dict(dept: Department, *, is_primary: bool) -> Dict[str, Any]:
    return {
        "uuid": str(dept.uuid),
        "name": str(dept.name or ""),
        "code": str(dept.code or "") or None,
        "is_primary": is_primary,
    }


async def build_hierarchy_department_submit_hints(
    tenant_id: int,
    entity_type: str,
    entity_id: int,
    *,
    owner_user_id: int,
    process_nodes: Any,
) -> Dict[str, Any]:
    """提交前返回审批部门候选与默认项。"""
    if not graph_requires_hierarchy_department(process_nodes):
        return {
            "hierarchy_department_required": False,
            "hierarchy_department_options": [],
            "default_hierarchy_department_uuid": None,
        }

    memberships = await UserDepartmentAssignmentService.list_membership_departments(
        tenant_id, int(owner_user_id)
    )
    primary_id: Optional[int] = None
    primary_row = await UserDepartmentAssignment.filter(
        tenant_id=tenant_id,
        user_id=int(owner_user_id),
        is_primary=True,
    ).first()
    if primary_row:
        primary_id = int(primary_row.department_id)
    else:
        from infra.models.user import User

        user = await User.filter(id=int(owner_user_id), tenant_id=tenant_id).first()
        if user and user.department_id:
            primary_id = int(user.department_id)

    options: List[Dict[str, Any]] = []
    member_ids = {int(d.id) for d in memberships}
    for dept in memberships:
        options.append(_dept_option_dict(dept, is_primary=(primary_id == int(dept.id))))

    doc_dept_id = await _document_department_id(tenant_id, entity_type, entity_id)
    default_uuid: Optional[str] = None
    if doc_dept_id and doc_dept_id in member_ids:
        match = next((d for d in memberships if int(d.id) == doc_dept_id), None)
        if match:
            default_uuid = str(match.uuid)
    if not default_uuid and primary_id and primary_id in member_ids:
        match = next((d for d in memberships if int(d.id) == primary_id), None)
        if match:
            default_uuid = str(match.uuid)
    if not default_uuid and len(options) == 1:
        default_uuid = str(options[0]["uuid"])

    required = len(options) >= 2
    return {
        "hierarchy_department_required": required,
        "hierarchy_department_options": options,
        "default_hierarchy_department_uuid": default_uuid,
    }


def write_hierarchy_department_snapshot(
    payload: Dict[str, Any],
    *,
    department: Department,
) -> None:
    payload["hierarchy_department_id"] = int(department.id)
    payload["hierarchy_department_uuid"] = str(department.uuid)
    payload["hierarchy_department_name"] = str(department.name or "")


async def resolve_chosen_hierarchy_department(
    tenant_id: int,
    owner_user_id: int,
    *,
    hierarchy_department_uuid: Optional[str],
    allow_auto_single: bool,
) -> Optional[Department]:
    """校验并返回所选任职部门；单部门且 allow_auto_single 时自动取唯一项。"""
    memberships = await UserDepartmentAssignmentService.list_membership_departments(
        tenant_id, int(owner_user_id)
    )
    if not memberships:
        return None
    by_uuid = {str(d.uuid): d for d in memberships}
    if len(memberships) == 1 and allow_auto_single and not hierarchy_department_uuid:
        return memberships[0]
    if len(memberships) >= 2:
        chosen = (hierarchy_department_uuid or "").strip()
        if not chosen:
            raise ValidationError("提交审批须选择审批部门")
        dept = by_uuid.get(chosen)
        if dept is None:
            raise ValidationError("所选审批部门不属于制单人任职范围")
        return dept
    if hierarchy_department_uuid:
        dept = by_uuid.get(hierarchy_department_uuid.strip())
        if dept is None:
            raise ValidationError("所选审批部门不属于制单人任职范围")
        return dept
    return memberships[0]


async def apply_hierarchy_department_on_start(
    tenant_id: int,
    *,
    process_nodes: Any,
    owner_user_id: int,
    payload: Dict[str, Any],
    hierarchy_department_uuid: Optional[str],
) -> None:
    if not graph_requires_hierarchy_department(process_nodes):
        return
    dept = await resolve_chosen_hierarchy_department(
        tenant_id,
        int(owner_user_id),
        hierarchy_department_uuid=hierarchy_department_uuid,
        allow_auto_single=True,
    )
    if dept is not None:
        write_hierarchy_department_snapshot(payload, department=dept)
