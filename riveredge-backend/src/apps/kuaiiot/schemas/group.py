"""设备分组请求与响应。"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class GroupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    parent_id: Optional[int] = None
    sort_order: int = 0
    remark: Optional[str] = None


class GroupUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None
    remark: Optional[str] = None


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    code: str
    name: str
    parent_id: Optional[int] = None
    sort_order: int
    remark: Optional[str] = None


class DeviceGroupAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: Optional[int] = None
