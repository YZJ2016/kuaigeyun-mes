"""排班管理 Schema"""

from datetime import date, datetime, time
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

from apps.master_data.config.performance_scope_spec import validate_scope_ids
from apps.master_data.schemas.work_calendar_schemas import PerformanceScopeType


def _normalize_optional_clock(v: object) -> object:
    """Tortoise TimeField 可能带 tzinfo；统一为 naive time。"""
    if isinstance(v, time):
        return time(v.hour, v.minute, v.second, v.microsecond)
    return v


def _validate_shift_break_pair(
    *,
    start_time: time,
    end_time: time,
    crosses_midnight: bool,
    break_start: Optional[time],
    break_end: Optional[time],
) -> None:
    has_bs = break_start is not None
    has_be = break_end is not None
    if has_bs != has_be:
        raise ValueError("班内休息须同时配置开始与结束时间")
    if not has_bs:
        return
    assert break_start is not None and break_end is not None
    if break_end <= break_start:
        raise ValueError("班内休息结束须晚于开始")
    if crosses_midnight:
        in_evening = start_time <= break_start < break_end
        in_morning = break_start < break_end <= end_time
        if not (in_evening or in_morning):
            raise ValueError("跨天班次的班内休息须落在开始日晚间或结束日凌晨班段内")
        return
    if end_time <= start_time:
        raise ValueError("非跨天班次结束时间须晚于开始时间")
    if not (start_time <= break_start < break_end <= end_time):
        raise ValueError("班内休息须落在班次时段内")


class ShiftBase(BaseModel):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=200)
    start_time: time = Field(..., alias="startTime")
    end_time: time = Field(..., alias="endTime")
    break_start: Optional[time] = Field(None, alias="breakStart")
    break_end: Optional[time] = Field(None, alias="breakEnd")
    crosses_midnight: bool = Field(False, alias="crossesMidnight")
    standard_hours: Decimal = Field(Decimal("8"), alias="standardHours")
    is_active: bool = Field(True, alias="isActive")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("code", "name")
    @classmethod
    def strip_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("不能为空")
        return v

    @field_validator("start_time", "end_time", "break_start", "break_end", mode="before")
    @classmethod
    def _normalize_clock_time(cls, v: object) -> object:
        return _normalize_optional_clock(v)

    @model_validator(mode="after")
    def validate_break(self) -> "ShiftBase":
        _validate_shift_break_pair(
            start_time=self.start_time,
            end_time=self.end_time,
            crosses_midnight=self.crosses_midnight,
            break_start=self.break_start,
            break_end=self.break_end,
        )
        return self


class ShiftCreate(ShiftBase):
    pass


class ShiftUpdate(BaseModel):
    code: Optional[str] = Field(None, max_length=50)
    name: Optional[str] = Field(None, max_length=200)
    start_time: Optional[time] = Field(None, alias="startTime")
    end_time: Optional[time] = Field(None, alias="endTime")
    break_start: Optional[time] = Field(None, alias="breakStart")
    break_end: Optional[time] = Field(None, alias="breakEnd")
    crosses_midnight: Optional[bool] = Field(None, alias="crossesMidnight")
    standard_hours: Optional[Decimal] = Field(None, alias="standardHours")
    is_active: Optional[bool] = Field(None, alias="isActive")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("start_time", "end_time", "break_start", "break_end", mode="before")
    @classmethod
    def _normalize_clock_time(cls, v: object) -> object:
        return _normalize_optional_clock(v)


class ShiftResponse(ShiftBase):
    id: int
    uuid: str
    tenant_id: int = Field(..., alias="tenantId")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")
    created_by_name: Optional[str] = Field(None, alias="createdByName")
    updated_by_name: Optional[str] = Field(None, alias="updatedByName")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ShiftRosterCreate(BaseModel):
    scope_type: Literal["work_group", "employee", "all_employees"] = Field(
        "work_group", alias="scopeType"
    )
    work_group_id: Optional[int] = Field(None, alias="workGroupId")
    employee_id: Optional[int] = Field(None, alias="employeeId")
    period_start: date = Field(..., alias="periodStart")
    remarks: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_scope(self) -> "ShiftRosterCreate":
        if self.scope_type == "work_group":
            if not self.work_group_id:
                raise ValueError("工作小组排班须指定 workGroupId")
            if self.employee_id:
                raise ValueError("工作小组排班不可指定 employeeId")
        elif self.scope_type == "employee":
            if not self.employee_id:
                raise ValueError("员工排班须指定 employeeId")
            if self.work_group_id:
                raise ValueError("员工排班不可指定 workGroupId")
        elif self.scope_type == "all_employees":
            if self.work_group_id or self.employee_id:
                raise ValueError("全员排班不可指定 workGroupId 或 employeeId")
        return self


class ShiftAssignmentItem(BaseModel):
    employee_id: int = Field(..., alias="employeeId")
    work_date: date = Field(..., alias="workDate")
    shift_id: Optional[int] = Field(None, alias="shiftId")

    model_config = ConfigDict(populate_by_name=True)


class ShiftAssignmentsBulkUpdate(BaseModel):
    assignments: List[ShiftAssignmentItem] = Field(default_factory=list)


class ShiftAssignmentResponse(BaseModel):
    id: int
    employee_id: int = Field(..., alias="employeeId")
    employee_name: Optional[str] = Field(None, alias="employeeName")
    work_date: date = Field(..., alias="workDate")
    shift_id: Optional[int] = Field(None, alias="shiftId")
    shift_code: Optional[str] = Field(None, alias="shiftCode")
    shift_name: Optional[str] = Field(None, alias="shiftName")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ShiftRosterResponse(BaseModel):
    id: int
    uuid: str
    tenant_id: int = Field(..., alias="tenantId")
    scope_type: str = Field("work_group", alias="scopeType")
    work_group_id: Optional[int] = Field(None, alias="workGroupId")
    work_group_code: Optional[str] = Field(None, alias="workGroupCode")
    work_group_name: Optional[str] = Field(None, alias="workGroupName")
    employee_id: Optional[int] = Field(None, alias="employeeId")
    employee_name: Optional[str] = Field(None, alias="employeeName")
    period_start: date = Field(..., alias="periodStart")
    period_end: date = Field(..., alias="periodEnd")
    status: str
    published_at: Optional[datetime] = Field(None, alias="publishedAt")
    remarks: Optional[str] = None
    assignments: List[ShiftAssignmentResponse] = Field(default_factory=list)
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")
    created_by_name: Optional[str] = Field(None, alias="createdByName")
    updated_by_name: Optional[str] = Field(None, alias="updatedByName")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


RosterTimeAdjustmentKind = Literal["temp_overtime", "temp_rest"]


class RosterTimeAdjustmentBase(BaseModel):
    scope_type: PerformanceScopeType = Field("employee", alias="scopeType")
    department_id: Optional[int] = Field(None, alias="departmentId")
    department_name: Optional[str] = Field(None, alias="departmentName")
    employee_id: Optional[int] = Field(None, alias="employeeId")
    work_date: date = Field(..., alias="workDate")
    kind: RosterTimeAdjustmentKind
    start_time: time = Field(..., alias="startTime")
    end_time: time = Field(..., alias="endTime")
    reason: str = Field(..., min_length=1, max_length=500)
    is_active: bool = Field(True, alias="isActive")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def _parse_clock(cls, v: object) -> object:
        return _normalize_optional_clock(v)

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, v: str) -> str:
        text = (v or "").strip()
        if not text:
            raise ValueError("原因不能为空")
        return text

    @model_validator(mode="after")
    def _validate_window(self) -> "RosterTimeAdjustmentBase":
        if self.end_time <= self.start_time:
            raise ValueError("结束时间须晚于开始时间（不跨日）")
        validate_scope_ids(
            self.scope_type,
            department_id=self.department_id,
            employee_id=self.employee_id,
        )
        return self


class RosterTimeAdjustmentCreate(RosterTimeAdjustmentBase):
    employee_name: Optional[str] = Field(None, alias="employeeName")


class RosterTimeAdjustmentUpdate(BaseModel):
    scope_type: Optional[PerformanceScopeType] = Field(None, alias="scopeType")
    department_id: Optional[int] = Field(None, alias="departmentId")
    department_name: Optional[str] = Field(None, alias="departmentName")
    employee_id: Optional[int] = Field(None, alias="employeeId")
    work_date: Optional[date] = Field(None, alias="workDate")
    kind: Optional[RosterTimeAdjustmentKind] = None
    start_time: Optional[time] = Field(None, alias="startTime")
    end_time: Optional[time] = Field(None, alias="endTime")
    reason: Optional[str] = Field(None, min_length=1, max_length=500)
    is_active: Optional[bool] = Field(None, alias="isActive")
    employee_name: Optional[str] = Field(None, alias="employeeName")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def _parse_clock(cls, v: object) -> object:
        return _normalize_optional_clock(v)

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        text = v.strip()
        if not text:
            raise ValueError("原因不能为空")
        return text


class RosterTimeAdjustmentResponse(RosterTimeAdjustmentBase):
    id: int
    uuid: str
    tenant_id: int = Field(..., alias="tenantId")
    employee_name: Optional[str] = Field(None, alias="employeeName")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")
    created_by_name: Optional[str] = Field(None, alias="createdByName")
    updated_by_name: Optional[str] = Field(None, alias="updatedByName")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
