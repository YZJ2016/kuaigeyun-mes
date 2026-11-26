"""用户主部门与兼职部门任职维护。"""

from __future__ import annotations

from typing import Iterable, List, Optional, Set

from core.models.department import Department
from core.models.user_department_assignment import UserDepartmentAssignment
from infra.exceptions.exceptions import ValidationError
from infra.models.user import User


class UserDepartmentAssignmentService:
    @staticmethod
    async def replace_assignments(
        tenant_id: int,
        user_id: int,
        primary_department_id: Optional[int],
        secondary_department_ids: Optional[Iterable[int]] = None,
    ) -> None:
        secondary_ids = [
            int(d)
            for d in (secondary_department_ids or [])
            if d is not None and int(d) > 0
        ]
        if primary_department_id and primary_department_id in secondary_ids:
            raise ValidationError("兼职部门不得与主部门重复")

        await UserDepartmentAssignment.filter(tenant_id=tenant_id, user_id=user_id).delete()

        if primary_department_id:
            await UserDepartmentAssignment.create(
                tenant_id=tenant_id,
                user_id=user_id,
                department_id=int(primary_department_id),
                is_primary=True,
            )
        for dept_id in secondary_ids:
            await UserDepartmentAssignment.create(
                tenant_id=tenant_id,
                user_id=user_id,
                department_id=int(dept_id),
                is_primary=False,
            )

    @staticmethod
    async def list_secondary_departments(tenant_id: int, user_id: int) -> List[Department]:
        rows = await UserDepartmentAssignment.filter(
            tenant_id=tenant_id,
            user_id=user_id,
            is_primary=False,
        ).all()
        if not rows:
            return []
        dept_ids = [r.department_id for r in rows]
        return await Department.filter(
            tenant_id=tenant_id,
            id__in=dept_ids,
            deleted_at__isnull=True,
        ).all()

    @staticmethod
    async def list_membership_department_ids(tenant_id: int, user_id: int) -> List[int]:
        """主部门 + 兼职，去重；无任职行时回退 User.department_id。"""
        rows = await UserDepartmentAssignment.filter(
            tenant_id=tenant_id,
            user_id=user_id,
        ).all()
        ordered: List[int] = []
        if rows:
            primary = [int(r.department_id) for r in rows if r.is_primary]
            secondary = [int(r.department_id) for r in rows if not r.is_primary]
            for did in primary + secondary:
                if did > 0 and did not in ordered:
                    ordered.append(did)
            return ordered
        user = await User.filter(
            id=user_id,
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).first()
        if user and user.department_id:
            return [int(user.department_id)]
        return []

    @staticmethod
    async def list_membership_departments(tenant_id: int, user_id: int) -> List[Department]:
        ids = await UserDepartmentAssignmentService.list_membership_department_ids(
            tenant_id, user_id
        )
        if not ids:
            return []
        rows = await Department.filter(
            tenant_id=tenant_id,
            id__in=ids,
            deleted_at__isnull=True,
        ).all()
        by_id = {int(d.id): d for d in rows}
        return [by_id[i] for i in ids if i in by_id]

    @staticmethod
    async def list_users_in_departments(tenant_id: int, department_ids: List[int]) -> List[int]:
        """任职表或主 FK 归属上述任一部门的有效用户 id（未删除且启用）。"""
        dept_ids = [int(d) for d in department_ids if d is not None and int(d) > 0]
        if not dept_ids:
            return []
        assigned = await UserDepartmentAssignment.filter(
            tenant_id=tenant_id,
            department_id__in=dept_ids,
        ).values_list("user_id", flat=True)
        assigned_ids = [
            int(uid) for uid in assigned if uid is not None and int(uid) > 0
        ]
        live_assigned: List[int] = []
        if assigned_ids:
            live_assigned = [
                int(uid)
                for uid in await User.filter(
                    tenant_id=tenant_id,
                    id__in=assigned_ids,
                    deleted_at__isnull=True,
                    is_active=True,
                ).values_list("id", flat=True)
            ]
        primary = await User.filter(
            tenant_id=tenant_id,
            department_id__in=dept_ids,
            deleted_at__isnull=True,
            is_active=True,
        ).values_list("id", flat=True)
        seen: Set[int] = set()
        out: List[int] = []
        for raw in list(live_assigned) + list(primary):
            if raw is None:
                continue
            uid = int(raw)
            if uid <= 0 or uid in seen:
                continue
            seen.add(uid)
            out.append(uid)
        return out

    @staticmethod
    async def count_users_for_department(tenant_id: int, department_id: int) -> int:
        ids = await UserDepartmentAssignmentService.list_users_in_departments(
            tenant_id, [int(department_id)]
        )
        return len(ids)

    @staticmethod
    async def user_has_department_membership(
        tenant_id: int,
        user_id: int,
        department_id: int,
    ) -> bool:
        target = int(department_id)
        if target <= 0:
            return False
        member_ids = await UserDepartmentAssignmentService.list_membership_department_ids(
            tenant_id, user_id
        )
        return target in member_ids
