"""控制面请求与响应。响应不含设备鉴权凭据。"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    connection_type: str = Field(..., min_length=1, max_length=30)
    config: Optional[dict] = None
    is_enabled: bool = True
    remark: Optional[str] = None


class ConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    code: str
    name: str
    connection_type: str
    config: Optional[dict] = None
    is_enabled: bool
    health_status: str
    created_at: datetime


class DeviceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: Optional[int] = None
    external_device_id: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    equipment_uuid: Optional[str] = Field(default=None, max_length=36)
    template_code: Optional[str] = Field(default=None, max_length=50)
    remark: Optional[str] = None


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    connection_id: Optional[int] = None
    external_device_id: str
    code: str
    name: str
    equipment_uuid: Optional[str] = None
    group_id: Optional[int] = None
    is_online: bool
    last_seen_at: Optional[datetime] = None
    created_at: datetime


class TagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag_key: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)
    value_type: str = Field(default="number", max_length=20)
    unit: Optional[str] = Field(default=None, max_length=30)
    map_target: str = Field(..., min_length=1, max_length=100)
    fill_target: Optional[str] = Field(default=None, max_length=100)
    is_enabled: bool = True


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    device_id: int
    tag_key: str
    name: str
    value_type: str
    unit: Optional[str] = None
    map_target: str
    fill_target: Optional[str] = None
    is_enabled: bool


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    tag_key: str
    value_text: Optional[str] = None
    value_number: Optional[Decimal] = None
    value_bool: Optional[bool] = None
    quality: str
    sampled_at: datetime
