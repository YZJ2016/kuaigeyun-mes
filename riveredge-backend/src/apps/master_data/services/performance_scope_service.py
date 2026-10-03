"""解析部门/人员快照，供加班与临时调整写路径使用。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from apps.master_data.config.performance_scope_spec import validate_scope_ids
from core.models.department import Department
from infra.exceptions.exceptions import NotFoundError
from infra.models.user import User


class PerformanceScopeService:
    @staticmethod
    async def resolve_department_name(tenant_id: int, department_id: int) -> str:
        row = await Department.filter(
            id=department_id, tenant_id=tenant_id, deleted_at__isnull=True
        ).first()
        if not row:
            raise NotFoundError(f"部门 {department_id} 不存在")
        return (row.name or str(department_id)).strip()

    @staticmethod
    async def resolve_employee_name(tenant_id: int, employee_id: int) -> str:
        user = await User.filter(
            id=employee_id, tenant_id=tenant_id, deleted_at__isnull=True
        ).first()
        if not user:
            raise NotFoundError(f"员工 {employee_id} 不存在")
        return (user.full_name or user.username or str(employee_id)).strip()

    @staticmethod
    async def resolve_viewer_department_id(tenant_id: int, employee_id: int) -> Optional[int]:
        user = await User.filter(
            id=employee_id, tenant_id=tenant_id, deleted_at__isnull=True
        ).first()
        if not user or user.department_id is None:
            return None
        return int(user.department_id)

    @staticmethod
    async def build_scope_write_fields(
        tenant_id: int,
        *,
        scope_type: str,
        department_id: Optional[int] = None,
        department_name: Optional[str] = None,
        employee_id: Optional[int] = None,
        employee_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        st = (scope_type or "plant").strip().lower()
        validate_scope_ids(st, department_id=department_id, employee_id=employee_id)
        fields: Dict[str, Any] = {
            "scope_type": st,
            "department_id": None,
            "department_name": None,
            "employee_id": None,
            "employee_name": None,
        }
        if st == "department":
            fields["department_id"] = int(department_id)  # type: ignore[arg-type]
            fields["department_name"] = department_name or await PerformanceScopeService.resolve_department_name(
                tenant_id, int(department_id)
            )
        elif st == "employee":
            fields["employee_id"] = int(employee_id)  # type: ignore[arg-type]
            fields["employee_name"] = employee_name or await PerformanceScopeService.resolve_employee_name(
                tenant_id, int(employee_id)
            )
        return fields
