"""每日考勤登记服务。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from apps.kuaioa.models.daily_attendance import KuaioaDailyAttendanceRecord
from apps.kuaioa.models.employee import KuaioaEmployeeProfile
from apps.kuaioa.schemas.daily_attendance import DailyAttendanceCreate, DailyAttendanceUpdate
from apps.kuaioa.services.kuaioa_list_core import (
    apply_create_audit_by_user_id,
    build_keyword_q,
    model_to_dict,
    parse_optional_date,
    touch_updated,
)
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

_CLOCK_FIELDS = (
    "clock_in_1",
    "clock_out_1",
    "clock_in_2",
    "clock_out_2",
    "clock_in_3",
    "clock_out_3",
)
_HOUR_FIELDS = ("expected_hours", "paid_hours", "actual_hours", "ot_hours")
_MINUTE_FIELDS = ("late_minutes", "early_leave_minutes")


def _norm_clock(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # 兼容 ISO / dayjs 序列化：取末尾 HH:mm[:ss] 并规范为 HH:mm
    if "T" in text:
        text = text.split("T", 1)[1]
    text = text.replace("Z", "").split("+", 1)[0].split(".", 1)[0].strip()
    if " " in text:
        text = text.rsplit(" ", 1)[-1]
    parts = text.split(":")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        hour = int(parts[0])
        minute = int(parts[1])
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    return text[:16]


def _norm_hours(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    d = Decimal(str(value))
    if d < 0:
        raise BusinessLogicError("时长不能为负数")
    return d


def _norm_minutes(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    n = int(value)
    if n < 0:
        raise BusinessLogicError("分钟不能为负数")
    return n


class DailyAttendanceService:
    async def list_rows(
        self,
        tenant_id: int,
        *,
        keyword: Optional[str] = None,
        work_date_from: Optional[str] = None,
        work_date_to: Optional[str] = None,
        department_name: Optional[str] = None,
        employee_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        q = KuaioaDailyAttendanceRecord.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if keyword:
            q = q.filter(build_keyword_q(keyword, "employee_name", "employee_code", "department_name"))
        if department_name:
            q = q.filter(department_name=department_name.strip())
        if employee_id:
            q = q.filter(employee_id=int(employee_id))
        d_from = parse_optional_date(work_date_from) if work_date_from else None
        d_to = parse_optional_date(work_date_to) if work_date_to else None
        if d_from:
            q = q.filter(work_date__gte=d_from)
        if d_to:
            q = q.filter(work_date__lte=d_to)
        rows = await q.order_by("-work_date", "employee_name", "-id")
        return [model_to_dict(r) for r in rows]

    async def get_row(self, tenant_id: int, row_id: int) -> dict[str, Any]:
        row = await KuaioaDailyAttendanceRecord.get_or_none(
            id=row_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("考勤登记记录不存在")
        return model_to_dict(row)

    async def _resolve_employee(
        self,
        tenant_id: int,
        *,
        employee_id: Optional[int],
        employee_code: Optional[str],
        employee_name: Optional[str],
        department_name: Optional[str],
    ) -> dict[str, Any]:
        emp = None
        if employee_id:
            emp = await KuaioaEmployeeProfile.get_or_none(
                id=int(employee_id), tenant_id=tenant_id, deleted_at__isnull=True
            )
        if not emp and employee_code:
            emp = await KuaioaEmployeeProfile.get_or_none(
                tenant_id=tenant_id,
                employee_code=employee_code.strip(),
                deleted_at__isnull=True,
            )
        if emp:
            return {
                "employee_id": int(emp.id),
                "employee_code": emp.employee_code,
                "employee_name": emp.full_name,
                "department_name": department_name or emp.department_name,
            }
        name = (employee_name or "").strip()
        if not name:
            raise BusinessLogicError("请选择员工或填写姓名")
        return {
            "employee_id": int(employee_id) if employee_id else None,
            "employee_code": (employee_code or "").strip() or None,
            "employee_name": name,
            "department_name": (department_name or "").strip() or None,
        }

    async def _assert_unique(
        self,
        tenant_id: int,
        *,
        work_date,
        employee_id: Optional[int],
        employee_code: Optional[str],
        exclude_id: Optional[int] = None,
    ) -> None:
        q = KuaioaDailyAttendanceRecord.filter(
            tenant_id=tenant_id, work_date=work_date, deleted_at__isnull=True
        )
        if exclude_id:
            q = q.exclude(id=exclude_id)
        if employee_id:
            exists = await q.filter(employee_id=int(employee_id)).exists()
        elif employee_code:
            exists = await q.filter(employee_code=employee_code).exists()
        else:
            return
        if exists:
            raise BusinessLogicError("该员工当日考勤登记已存在")

    def _clock_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in _CLOCK_FIELDS:
            if key in data:
                out[key] = _norm_clock(data.get(key))
        for key in _HOUR_FIELDS:
            if key in data:
                out[key] = _norm_hours(data.get(key))
        for key in _MINUTE_FIELDS:
            if key in data:
                out[key] = _norm_minutes(data.get(key))
        if "result" in data:
            result = data.get("result")
            out["result"] = str(result).strip()[:50] if result else None
        if "notes" in data:
            out["notes"] = data.get("notes")
        return out

    async def create_row(
        self, tenant_id: int, data: DailyAttendanceCreate, user_id: int
    ) -> dict[str, Any]:
        work_date = parse_optional_date(data.work_date)
        if not work_date:
            raise BusinessLogicError("日期无效")
        emp = await self._resolve_employee(
            tenant_id,
            employee_id=data.employee_id,
            employee_code=data.employee_code,
            employee_name=data.employee_name,
            department_name=data.department_name,
        )
        await self._assert_unique(
            tenant_id,
            work_date=work_date,
            employee_id=emp.get("employee_id"),
            employee_code=emp.get("employee_code"),
        )
        payload: dict[str, Any] = {
            "tenant_id": tenant_id,
            "work_date": work_date,
            **emp,
            **self._clock_payload(data.model_dump()),
        }
        await apply_create_audit_by_user_id(payload, user_id)
        row = await KuaioaDailyAttendanceRecord.create(**payload)
        return model_to_dict(row)

    async def update_row(
        self, tenant_id: int, row_id: int, data: DailyAttendanceUpdate, user_id: int
    ) -> dict[str, Any]:
        row = await KuaioaDailyAttendanceRecord.get_or_none(
            id=row_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("考勤登记记录不存在")
        raw = data.model_dump(exclude_unset=True)
        work_date = row.work_date
        if "work_date" in raw:
            parsed = parse_optional_date(raw.pop("work_date"))
            if not parsed:
                raise BusinessLogicError("日期无效")
            work_date = parsed
            row.work_date = work_date

        need_emp = any(
            k in raw for k in ("employee_id", "employee_code", "employee_name", "department_name")
        )
        if need_emp:
            emp = await self._resolve_employee(
                tenant_id,
                employee_id=raw.get("employee_id", row.employee_id),
                employee_code=raw.get("employee_code", row.employee_code),
                employee_name=raw.get("employee_name", row.employee_name),
                department_name=raw.get("department_name", row.department_name),
            )
            for k, v in emp.items():
                setattr(row, k, v)
            await self._assert_unique(
                tenant_id,
                work_date=work_date,
                employee_id=emp.get("employee_id"),
                employee_code=emp.get("employee_code"),
                exclude_id=int(row.id),
            )
        else:
            await self._assert_unique(
                tenant_id,
                work_date=work_date,
                employee_id=row.employee_id,
                employee_code=row.employee_code,
                exclude_id=int(row.id),
            )

        for k, v in self._clock_payload(raw).items():
            setattr(row, k, v)
        await touch_updated(row, user_id)
        await row.save()
        return model_to_dict(row)

    async def delete_row(self, tenant_id: int, row_id: int, user_id: int) -> None:
        row = await KuaioaDailyAttendanceRecord.get_or_none(
            id=row_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("考勤登记记录不存在")
        row.deleted_at = resolve_business_datetime()
        await touch_updated(row, user_id)
        await row.save()
