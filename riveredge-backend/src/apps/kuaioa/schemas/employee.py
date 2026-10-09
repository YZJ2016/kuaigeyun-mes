"""员工档案 schemas。"""

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class EmployeeProfileCreate(BaseModel):
    employee_code: Optional[str] = Field(None, max_length=50)
    full_name: str = Field(..., max_length=100)
    phone: Optional[str] = Field(None, max_length=30)
    workshop_name: Optional[str] = Field(None, max_length=100)
    production_line_name: Optional[str] = Field(None, max_length=100)
    employment_type: str = Field(default="formal", max_length=20)
    pay_method: str = Field(default="time", max_length=20)
    hourly_rate: Optional[Decimal] = None
    hire_date: Optional[str] = None
    leave_date: Optional[str] = None
    bank_account: Optional[str] = Field(None, max_length=50)
    bank_name: Optional[str] = Field(None, max_length=100)
    bank_branch: Optional[str] = Field(None, max_length=200)
    living_allowance: Optional[Decimal] = None
    post_wage: Optional[Decimal] = None
    social_insurance: Optional[Decimal] = None
    housing_fund: Optional[Decimal] = None
    rent_utility: Optional[Decimal] = None
    welfare_dragon_boat: Optional[Decimal] = None
    welfare_mid_autumn: Optional[Decimal] = None
    welfare_spring_festival: Optional[Decimal] = None
    user_id: Optional[int] = None
    department_name: Optional[str] = Field(None, max_length=100)
    status: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = None


class EmployeeBulkCreateRequest(BaseModel):
    """批量创建员工档案（导入分片；单次最多 200）"""

    items: List[EmployeeProfileCreate] = Field(
        ...,
        min_length=1,
        max_length=200,
        description="待创建员工列表（单次最多 200）",
    )

    model_config = ConfigDict(populate_by_name=True)


class EmployeeAccountQuickCreateRequest(BaseModel):
    """员工档案旁一键创建登录账号。"""

    full_name: str = Field(..., min_length=1, max_length=100, description="姓名")
    username: Optional[str] = Field(None, min_length=2, max_length=50, description="登录账号，留空自动生成")
    phone: Optional[str] = Field(None, max_length=30, description="手机号")


class EmployeeAccountQuickCreateResponse(BaseModel):
    """一键创建账号结果（initial_password 仅此一次返回）。"""

    user_id: int = Field(..., description="用户ID")
    username: str = Field(..., description="登录账号")
    initial_password: str = Field(..., description="初始密码")


class EmployeeProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=30)
    workshop_name: Optional[str] = Field(None, max_length=100)
    production_line_name: Optional[str] = Field(None, max_length=100)
    employment_type: Optional[str] = Field(None, max_length=20)
    pay_method: Optional[str] = Field(None, max_length=20)
    hourly_rate: Optional[Decimal] = None
    hire_date: Optional[str] = None
    leave_date: Optional[str] = None
    bank_account: Optional[str] = Field(None, max_length=50)
    bank_name: Optional[str] = Field(None, max_length=100)
    bank_branch: Optional[str] = Field(None, max_length=200)
    living_allowance: Optional[Decimal] = None
    post_wage: Optional[Decimal] = None
    social_insurance: Optional[Decimal] = None
    housing_fund: Optional[Decimal] = None
    rent_utility: Optional[Decimal] = None
    welfare_dragon_boat: Optional[Decimal] = None
    welfare_mid_autumn: Optional[Decimal] = None
    welfare_spring_festival: Optional[Decimal] = None
    user_id: Optional[int] = None
    department_name: Optional[str] = Field(None, max_length=100)
    status: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = None
