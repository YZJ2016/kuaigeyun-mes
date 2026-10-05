"""厂级工作日历服务：工作时段配置 + 加班计划。"""

from __future__ import annotations

import uuid as uuid_mod
from collections import defaultdict
from datetime import date, time, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.kuaizhizao.utils.work_calendar import load_holiday_dates
from apps.master_data.config.performance_scope_spec import scope_applies_to_row
from apps.master_data.models.shift_scheduling import RosterTimeAdjustment
from apps.master_data.models.work_calendar import (
    OvertimePlan,
    StationUnavailableWindow,
    WorkCalendarConfig,
)
from apps.master_data.services.performance_scope_service import PerformanceScopeService
from apps.master_data.schemas.work_calendar_schemas import (
    EffectiveCalendarResponse,
    OvertimePlanCreate,
    OvertimePlanResponse,
    OvertimePlanUpdate,
    StationUnavailableWindowCreate,
    StationUnavailableWindowResponse,
    StationUnavailableWindowUpdate,
    WorkCalendarConfigResponse,
    WorkCalendarConfigUpdate,
)
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User

DEFAULT_START = time(8, 0)
DEFAULT_END = time(17, 0)


def _config_response(row: WorkCalendarConfig) -> WorkCalendarConfigResponse:
    payload = WorkCalendarConfigResponse.model_validate(row)
    # 可排窗已统一跟班次；对外始终返回 shift，避免前端再走固定时段
    return payload.model_copy(
        update={"window_source": "shift", "break_start": None, "break_end": None}
    )


def _overtime_response(row: OvertimePlan) -> OvertimePlanResponse:
    return OvertimePlanResponse.model_validate(row)


def _strip_tz_clock(t: time) -> time:
    if getattr(t, "tzinfo", None) is not None:
        return t.replace(tzinfo=None, microsecond=0)
    return t.replace(microsecond=0) if getattr(t, "microsecond", 0) else t


async def _merge_scoped_overtime_windows(
    tenant_id: int,
    from_date: date,
    to_date: date,
    *,
    employee_id: Optional[int] = None,
) -> Dict[date, List[Tuple[time, time]]]:
    viewer_department_id: Optional[int] = None
    if employee_id is not None:
        viewer_department_id = await PerformanceScopeService.resolve_viewer_department_id(
            tenant_id, employee_id
        )

    overtime: Dict[date, List[Tuple[time, time]]] = defaultdict(list)

    ot_rows = await OvertimePlan.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        is_active=True,
        overtime_date__gte=from_date,
        overtime_date__lte=to_date,
    ).all()
    for r in ot_rows:
        if not scope_applies_to_row(
            r.scope_type or "plant",
            row_department_id=r.department_id,
            row_employee_id=r.employee_id,
            viewer_employee_id=employee_id,
            viewer_department_id=viewer_department_id,
        ):
            continue
        s = _strip_tz_clock(r.start_time)
        e = _strip_tz_clock(r.end_time)
        if e > s:
            overtime[r.overtime_date].append((s, e))

    temp_rows = await RosterTimeAdjustment.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        is_active=True,
        kind="temp_overtime",
        work_date__gte=from_date,
        work_date__lte=to_date,
    ).all()
    for r in temp_rows:
        if not scope_applies_to_row(
            r.scope_type or "employee",
            row_department_id=r.department_id,
            row_employee_id=r.employee_id,
            viewer_employee_id=employee_id,
            viewer_department_id=viewer_department_id,
        ):
            continue
        s = _strip_tz_clock(r.start_time)
        e = _strip_tz_clock(r.end_time)
        if e > s:
            overtime[r.work_date].append((s, e))

    for d in overtime:
        overtime[d].sort(key=lambda x: x[0])
    return dict(overtime)


class WorkCalendarService:
    @staticmethod
    async def get_or_create_config(
        tenant_id: int,
        operator: Optional[User] = None,
    ) -> WorkCalendarConfigResponse:
        row = await WorkCalendarConfig.filter(
            tenant_id=tenant_id, deleted_at__isnull=True
        ).first()
        if row:
            return _config_response(row)
        payload: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "uuid": str(uuid_mod.uuid4()),
            "work_day_start": DEFAULT_START,
            "work_day_end": DEFAULT_END,
            "break_start": None,
            "break_end": None,
            "window_source": "shift",
        }
        apply_create_audit(payload, operator)
        row = await WorkCalendarConfig.create(**payload)
        return _config_response(row)

    @staticmethod
    async def update_config(
        tenant_id: int,
        data: WorkCalendarConfigUpdate,
        operator: Optional[User] = None,
    ) -> WorkCalendarConfigResponse:
        row = await WorkCalendarConfig.filter(
            tenant_id=tenant_id, deleted_at__isnull=True
        ).first()
        if not row:
            created = await WorkCalendarService.get_or_create_config(tenant_id, operator)
            row = await WorkCalendarConfig.get(id=created.id)
        # 可排工作窗已改跟班次；配置行仅保留兼容字段，窗口来源固定为 shift
        row.work_day_start = data.work_day_start
        row.work_day_end = data.work_day_end
        row.break_start = None
        row.break_end = None
        row.window_source = "shift"
        apply_update_audit(row, operator)
        await row.save()
        return _config_response(row)

    @staticmethod
    async def list_overtimes(
        tenant_id: int,
        *,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        q = OvertimePlan.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if date_from:
            q = q.filter(overtime_date__gte=date_from)
        if date_to:
            q = q.filter(overtime_date__lte=date_to)
        if is_active is not None:
            q = q.filter(is_active=is_active)
        total = await q.count()
        rows = await q.order_by("overtime_date", "start_time").offset(skip).limit(limit)
        return {
            "items": [_overtime_response(r) for r in rows],
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    @staticmethod
    async def create_overtime(
        tenant_id: int,
        data: OvertimePlanCreate,
        operator: Optional[User] = None,
    ) -> OvertimePlanResponse:
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
            "overtime_date": data.overtime_date,
            "start_time": data.start_time,
            "end_time": data.end_time,
            "name": data.name,
            "reason": data.reason,
            "is_active": data.is_active,
            **scope_fields,
        }
        apply_create_audit(payload, operator)
        row = await OvertimePlan.create(**payload)
        return _overtime_response(row)

    @staticmethod
    async def get_overtime(tenant_id: int, overtime_uuid: str) -> OvertimePlanResponse:
        row = await OvertimePlan.filter(
            tenant_id=tenant_id, uuid=overtime_uuid, deleted_at__isnull=True
        ).first()
        if not row:
            raise NotFoundError(f"加班计划 {overtime_uuid} 不存在")
        return _overtime_response(row)

    @staticmethod
    async def update_overtime(
        tenant_id: int,
        overtime_uuid: str,
        data: OvertimePlanUpdate,
        operator: Optional[User] = None,
    ) -> OvertimePlanResponse:
        row = await OvertimePlan.filter(
            tenant_id=tenant_id, uuid=overtime_uuid, deleted_at__isnull=True
        ).first()
        if not row:
            raise NotFoundError(f"加班计划 {overtime_uuid} 不存在")
        updates = data.model_dump(exclude_unset=True, by_alias=False)
        if "start_time" in updates or "end_time" in updates:
            start = updates.get("start_time", row.start_time)
            end = updates.get("end_time", row.end_time)
            if end <= start:
                raise ValidationError("endTime 必须晚于 startTime（加班窗口不跨日）")
        if "name" in updates and updates["name"] is not None:
            updates["name"] = str(updates["name"]).strip() or None
        if "reason" in updates and updates["reason"] is not None:
            updates["reason"] = str(updates["reason"]).strip() or None
        scope_keys = {"scope_type", "department_id", "department_name", "employee_id", "employee_name"}
        if scope_keys.intersection(updates.keys()):
            merged_scope = {
                "scope_type": updates.get("scope_type", row.scope_type or "plant"),
                "department_id": updates.get("department_id", row.department_id),
                "department_name": updates.get("department_name", row.department_name),
                "employee_id": updates.get("employee_id", row.employee_id),
                "employee_name": updates.get("employee_name", row.employee_name),
            }
            scope_fields = await PerformanceScopeService.build_scope_write_fields(
                tenant_id, **merged_scope
            )
            updates.update(scope_fields)
        for k, v in updates.items():
            setattr(row, k, v)
        apply_update_audit(row, operator)
        await row.save()
        return _overtime_response(row)

    @staticmethod
    async def delete_overtime(tenant_id: int, overtime_uuid: str) -> None:
        from tortoise.timezone import now as tz_now

        row = await OvertimePlan.filter(
            tenant_id=tenant_id, uuid=overtime_uuid, deleted_at__isnull=True
        ).first()
        if not row:
            raise NotFoundError(f"加班计划 {overtime_uuid} 不存在")
        row.deleted_at = tz_now()
        await row.save(update_fields=["deleted_at", "updated_at"])

    @staticmethod
    async def get_effective_calendar(
        tenant_id: int,
        from_date: date,
        to_date: date,
        *,
        employee_id: Optional[int] = None,
    ) -> Tuple[WorkCalendarConfig, Set[date], Dict[date, List[Tuple[time, time]]]]:
        """返回 (config_row, holidays, overtime_by_date)。"""
        cfg_resp = await WorkCalendarService.get_or_create_config(tenant_id)
        cfg = await WorkCalendarConfig.get(id=cfg_resp.id)
        if to_date < from_date:
            from_date, to_date = to_date, from_date
        holidays = await load_holiday_dates(tenant_id, from_date, to_date)
        overtime = await _merge_scoped_overtime_windows(
            tenant_id, from_date, to_date, employee_id=employee_id
        )
        return cfg, holidays, overtime

    @staticmethod
    async def get_effective_calendar_response(
        tenant_id: int,
        from_date: date,
        to_date: date,
    ) -> EffectiveCalendarResponse:
        cfg, holidays, overtime = await WorkCalendarService.get_effective_calendar(
            tenant_id, from_date, to_date
        )
        ot_payload: Dict[str, List[Dict[str, str]]] = {}
        for d, windows in overtime.items():
            ot_payload[d.isoformat()] = [
                {
                    "startTime": s.strftime("%H:%M"),
                    "endTime": e.strftime("%H:%M"),
                }
                for s, e in windows
            ]
        day_payload: Dict[str, List[Dict[str, str]]] = {}
        from apps.kuaizhizao.utils.working_time import _load_shift_day_windows

        day_windows = await _load_shift_day_windows(tenant_id, from_date, to_date)
        for d, windows in day_windows.items():
            day_payload[d.isoformat()] = [
                {
                    "startTime": s.strftime("%H:%M"),
                    "endTime": e.strftime("%H:%M"),
                }
                for s, e in windows
            ]
        return EffectiveCalendarResponse(
            config=_config_response(cfg),
            holiday_dates=sorted(holidays),
            overtime_by_date=ot_payload,
            day_windows_by_date=day_payload,
        )

    @staticmethod
    async def list_station_unavailable(
        tenant_id: int,
        *,
        station_id: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        q = StationUnavailableWindow.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if station_id:
            q = q.filter(station_id=station_id)
        if date_from:
            q = q.filter(end_at__gte=date_from)
        if date_to:
            q = q.filter(start_at__lte=date_to + timedelta(days=1))
        total = await q.count()
        rows = await q.order_by("-start_at").offset(skip).limit(limit)
        return {
            "items": [StationUnavailableWindowResponse.model_validate(r) for r in rows],
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    @staticmethod
    async def create_station_unavailable(
        tenant_id: int,
        data: StationUnavailableWindowCreate,
        operator: Optional[User] = None,
    ) -> StationUnavailableWindowResponse:
        if data.end_at <= data.start_at:
            raise ValidationError("endAt 必须晚于 startAt")
        payload: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "uuid": str(uuid_mod.uuid4()),
            "station_id": data.station_id,
            "start_at": data.start_at,
            "end_at": data.end_at,
            "reason": data.reason,
            "is_active": data.is_active,
        }
        apply_create_audit(payload, operator)
        row = await StationUnavailableWindow.create(**payload)
        return StationUnavailableWindowResponse.model_validate(row)

    @staticmethod
    async def update_station_unavailable(
        tenant_id: int,
        window_uuid: str,
        data: StationUnavailableWindowUpdate,
        operator: Optional[User] = None,
    ) -> StationUnavailableWindowResponse:
        row = await StationUnavailableWindow.filter(
            tenant_id=tenant_id, uuid=window_uuid, deleted_at__isnull=True
        ).first()
        if not row:
            raise NotFoundError(f"停机窗 {window_uuid} 不存在")
        updates = data.model_dump(exclude_unset=True, by_alias=False)
        start = updates.get("start_at", row.start_at)
        end = updates.get("end_at", row.end_at)
        if end <= start:
            raise ValidationError("endAt 必须晚于 startAt")
        if "reason" in updates and updates["reason"] is not None:
            updates["reason"] = str(updates["reason"]).strip() or None
        for k, v in updates.items():
            setattr(row, k, v)
        apply_update_audit(row, operator)
        await row.save()
        return StationUnavailableWindowResponse.model_validate(row)

    @staticmethod
    async def delete_station_unavailable(tenant_id: int, window_uuid: str) -> None:
        from tortoise.timezone import now as tz_now

        row = await StationUnavailableWindow.filter(
            tenant_id=tenant_id, uuid=window_uuid, deleted_at__isnull=True
        ).first()
        if not row:
            raise NotFoundError(f"停机窗 {window_uuid} 不存在")
        row.deleted_at = tz_now()
        await row.save(update_fields=["deleted_at", "updated_at"])
