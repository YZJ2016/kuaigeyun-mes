"""月度考勤 schemas。"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class AttendanceSheetCreate(BaseModel):
    year_month: str = Field(..., min_length=7, max_length=7, description="YYYY-MM")
    workshop_name: str = Field(..., max_length=100)
    production_line_name: Optional[str] = Field(None, max_length=100)
    employment_types: Optional[list[str]] = Field(
        None, description="用工类型多选 formal/temp/labor，空表示全部"
    )
    has_night: bool = False
    standard_hours: Decimal = Field(default=Decimal("8"))
    notes: Optional[str] = None


class AttendanceSheetUpdate(BaseModel):
    notes: Optional[str] = None
    has_night: Optional[bool] = None
    employment_types: Optional[list[str]] = None


class AttendanceDayUpdate(BaseModel):
    regular_hours: Optional[Decimal] = None
    ot_hours: Optional[Decimal] = None
    mark: Optional[str] = Field(None, max_length=20)
    is_night: Optional[bool] = None
    leave_deduct_amount: Optional[Decimal] = None
    notes: Optional[str] = None


class AttendanceBatchMark(BaseModel):
    """按日期批量标记休息/夜班。"""

    work_date: str = Field(..., description="YYYY-MM-DD")
    work_date_end: Optional[str] = Field(None, description="结束日期 YYYY-MM-DD，含当日；空则仅 work_date")
    mark: Optional[str] = Field(None, description="rest 或留空")
    is_night: Optional[bool] = None
    employee_ids: Optional[list[int]] = None


class AttendanceDayRegisterCreate(BaseModel):
    """新建休息 / 夜班登记（区间写入月度考勤草稿）。"""

    register_type: str = Field(..., description="rest 或 night")
    date_from: str = Field(..., description="YYYY-MM-DD")
    date_to: str = Field(..., description="YYYY-MM-DD")
    workshop_name: str = Field(..., max_length=100)
    production_line_name: Optional[str] = Field(None, max_length=100)
    employment_types: Optional[list[str]] = Field(
        None, description="用工类型多选 formal/temp/labor，空表示全部"
    )
    employee_ids: Optional[list[int]] = None
