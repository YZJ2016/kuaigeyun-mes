"""排班临时加班 / 临时休息。"""

from __future__ import annotations

import uuid as uuid_mod
from datetime import date, time
from typing import Any, Dict, List, Optional

from tortoise.expressions import Q

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.master_data.models.shift_scheduling import RosterTimeAdjustment
from apps.master_data.schemas.shift_scheduling_schemas import (
    RosterTimeAdjustmentCreate,
    RosterTimeAdjustmentResponse,
    RosterTimeAdjustmentUpdate,
)
from apps.master_data.services.performance_scope_service import PerformanceScopeService
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User


def _naive_clock(value: time) -> time:
    if getattr(value, "tzinfo", None) is not None:
        return time(value.hour, value.minute, value.second, value.microsecond)
    return value


class RosterTimeAdjustmentService:
    @staticmethod
    async def list_adjustments(
        tenant_id: int,
        *,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        employee_id: Optional[int] = None,
        employee_ids: Optional[List[int]] = None,
        kind: Optional[str] = None,
        scope_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        q = RosterTimeAdjustment.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if date_from:
            q = q.filter(work_date__gte=date_from)
        if date_to:
            q = q.filter(work_date__lte=date_to)
        if employee_id is not None:
            q = q.filter(scope_type="employee", employee_id=employee_id)
        if employee_ids:
            users = await User.filter(id__in=employee_ids, tenant_id=tenant_id).all()
            dept_ids = [int(u.department_id) for u in users if u.department_id is not None]
            q = q.filter(
                Q(scope_type="plant")
                | Q(scope_type="department", department_id__in=dept_ids)
                | Q(scope_type="employee", employee_id__in=employee_ids)
            )
        if kind:
            q = q.filter(kind=kind)
        if scope_type:
            q = q.filter(scope_type=scope_type)
        if is_active is not None:
            q = q.filter(is_active=is_active)
        total = await q.count()
        rows = await q.order_by("-work_date", "scope_type", "employee_id", "start_time").offset(skip).limit(limit)
        items = [RosterTimeAdjustmentResponse.model_validate(r) for r in rows]
        return {"items": items, "total": total, "skip": skip, "limit": limit}

    @staticmethod
    async def create(
        tenant_id: int,
        data: RosterTimeAdjustmentCreate,
        operator: Optional[User] = None,
    ) -> RosterTimeAdjustmentResponse:
        scope_fields = await PerformanceScopeService.build_scope_write_fields(
            tenant_id,
            scope_type=data.scope_type,
            department_id=data.department_id,
            department_name=data.department_name,
            employee_id=data.employee_id,
            employee_name=data.employee_name,
        )
        payload: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "uuid": str(uuid_mod.uuid4()),
            "work_date": data.work_date,
            "kind": data.kind,
            "start_time": _naive_clock(data.start_time),
            "end_time": _naive_clock(data.end_time),
            "reason": data.reason,
            "is_active": data.is_active,
            **scope_fields,
        }
        apply_create_audit(payload, operator)
        row = await RosterTimeAdjustment.create(**payload)
        return RosterTimeAdjustmentResponse.model_validate(row)

    @staticmethod
    async def get(tenant_id: int, uuid: str) -> RosterTimeAdjustmentResponse:
        row = await RosterTimeAdjustment.filter(
            tenant_id=tenant_id, uuid=uuid, deleted_at__isnull=True
        ).first()
        if not row:
            raise NotFoundError(f"临时调整 {uuid} 不存在")
        return RosterTimeAdjustmentResponse.model_validate(row)

    @staticmethod
    async def update(
        tenant_id: int,
        uuid: str,
        data: RosterTimeAdjustmentUpdate,
        operator: Optional[User] = None,
    ) -> RosterTimeAdjustmentResponse:
        row = await RosterTimeAdjustment.filter(
            tenant_id=tenant_id, uuid=uuid, deleted_at__isnull=True
        ).first()
        if not row:
            raise NotFoundError(f"临时调整 {uuid} 不存在")
        updates = data.model_dump(exclude_unset=True, by_alias=False)
        scope_keys = {"scope_type", "department_id", "department_name", "employee_id", "employee_name"}
        if scope_keys.intersection(updates.keys()):
            merged_scope = {
                "scope_type": updates.get("scope_type", row.scope_type or "employee"),
                "department_id": updates.get("department_id", row.department_id),
                "department_name": updates.get("department_name", row.department_name),
                "employee_id": updates.get("employee_id", row.employee_id),
                "employee_name": updates.get("employee_name", row.employee_name),
            }
            scope_fields = await PerformanceScopeService.build_scope_write_fields(
                tenant_id, **merged_scope
            )
            updates.update(scope_fields)
        for key in ("start_time", "end_time"):
            if key in updates and updates[key] is not None:
                updates[key] = _naive_clock(updates[key])
        start = updates.get("start_time", row.start_time)
        end = updates.get("end_time", row.end_time)
        if end <= start:
            raise ValidationError("结束时间须晚于开始时间（不跨日）")
        for k, v in updates.items():
            setattr(row, k, v)
        apply_update_audit(row, operator)
        await row.save()
        return RosterTimeAdjustmentResponse.model_validate(row)

    @staticmethod
    async def delete(tenant_id: int, uuid: str) -> None:
        from tortoise.timezone import now as tz_now

        row = await RosterTimeAdjustment.filter(
            tenant_id=tenant_id, uuid=uuid, deleted_at__isnull=True
        ).first()
        if not row:
            raise NotFoundError(f"临时调整 {uuid} 不存在")
        row.deleted_at = tz_now()
        await row.save(update_fields=["deleted_at", "updated_at"])

    @staticmethod
    async def load_temp_overtime_windows(
        tenant_id: int,
        from_date: date,
        to_date: date,
    ) -> Dict[date, List[tuple[time, time]]]:
        """厂级合并（仅整厂范围）；按人排产请走 get_effective_calendar(employee_id=...)。"""
        from apps.master_data.services.work_calendar_service import _merge_scoped_overtime_windows

        return await _merge_scoped_overtime_windows(
            tenant_id, from_date, to_date, employee_id=None
        )
