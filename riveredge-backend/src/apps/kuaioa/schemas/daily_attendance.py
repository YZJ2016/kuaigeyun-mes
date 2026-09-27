"""每日考勤登记 schemas。"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class DailyAttendanceCreate(BaseModel):
    employee_id: Optional[int] = None
    employee_code: Optional[str] = Field(None, max_length=50)
    employee_name: Optional[str] = Field(None, max_length=100)
    department_name: Optional[str] = Field(None, max_length=100)
    work_date: str = Field(..., description="YYYY-MM-DD")
    clock_in_1: Optional[str] = Field(None, max_length=16)
    clock_out_1: Optional[str] = Field(None, max_length=16)
    clock_in_2: Optional[str] = Field(None, max_length=16)
    clock_out_2: Optional[str] = Field(None, max_length=16)
    clock_in_3: Optional[str] = Field(None, max_length=16)
    clock_out_3: Optional[str] = Field(None, max_length=16)
    result: Optional[str] = Field(None, max_length=50)
    expected_hours: Optional[Decimal] = None
    paid_hours: Optional[Decimal] = None
    actual_hours: Optional[Decimal] = None
    late_minutes: Optional[int] = None
    early_leave_minutes: Optional[int] = None
    ot_hours: Optional[Decimal] = None
    notes: Optional[str] = None


class DailyAttendanceUpdate(BaseModel):
    employee_id: Optional[int] = None
    employee_code: Optional[str] = Field(None, max_length=50)
    employee_name: Optional[str] = Field(None, max_length=100)
    department_name: Optional[str] = Field(None, max_length=100)
    work_date: Optional[str] = None
    clock_in_1: Optional[str] = Field(None, max_length=16)
    clock_out_1: Optional[str] = Field(None, max_length=16)
    clock_in_2: Optional[str] = Field(None, max_length=16)
    clock_out_2: Optional[str] = Field(None, max_length=16)
    clock_in_3: Optional[str] = Field(None, max_length=16)
    clock_out_3: Optional[str] = Field(None, max_length=16)
    result: Optional[str] = Field(None, max_length=50)
    expected_hours: Optional[Decimal] = None
    paid_hours: Optional[Decimal] = None
    actual_hours: Optional[Decimal] = None
    late_minutes: Optional[int] = None
    early_leave_minutes: Optional[int] = None
    ot_hours: Optional[Decimal] = None
    notes: Optional[str] = None
