"""控制面请求与响应。响应不含设备鉴权凭据。"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

_SECRET_CONFIG_KEYS = frozenset({"password", "passwd", "broker_password", "mqtt_password"})


def redact_connection_config(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).strip().lower() in _SECRET_CONFIG_KEYS:
                continue
            cleaned[str(key)] = redact_connection_config(item)
        return cleaned
    if isinstance(value, list):
        return [redact_connection_config(item) for item in value]
    return value


class ConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    connection_type: str = Field(..., min_length=1, max_length=30)
    integration_uuid: Optional[UUID] = None
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
    integration_id: Optional[int] = None
    config: Optional[dict] = None
    is_enabled: bool
    health_status: str
    created_at: datetime

    @field_serializer("config")
    def _serialize_config(self, config: Optional[dict]) -> Optional[dict]:
        if config is None:
            return None
        redacted = redact_connection_config(config)
        return redacted if isinstance(redacted, dict) else None


class ConnectionUpdate(BaseModel):
    """连接资料更新。code、connection_type 与公共连接绑定不可改。"""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    config: Optional[dict] = None
    is_enabled: Optional[bool] = None
    remark: Optional[str] = None


class DeviceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: Optional[int] = None
    external_device_id: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    equipment_uuid: Optional[str] = Field(default=None, max_length=36)
    product_id: Optional[int] = Field(default=None, gt=0)
    group_id: Optional[int] = Field(default=None, gt=0)
    template_code: Optional[str] = Field(default=None, max_length=50)
    remark: Optional[str] = None


class DeviceUpdate(BaseModel):
    """设备改绑与资料更新。equipment_uuid 需配合 clear_equipment 表达解绑。"""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    connection_id: Optional[int] = None
    equipment_uuid: Optional[str] = Field(default=None, max_length=36)
    clear_equipment: bool = False
    group_id: Optional[int] = None
    product_id: Optional[int] = None
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
    product_id: Optional[int] = None
    remark: Optional[str] = None
    is_online: bool
    last_seen_at: Optional[datetime] = None
    created_at: datetime


class DeviceTokenOut(DeviceOut):
    """仅建机/轮换凭据当次返回；列表与详情仍走 DeviceOut。"""

    device_token: str


class TagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag_key: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)
    value_type: str = Field(default="number", max_length=20)
    unit: Optional[str] = Field(default=None, max_length=30)
    map_target: str = Field(..., min_length=1, max_length=100)
    fill_target: Optional[str] = Field(default=None, max_length=100)
    is_enabled: bool = True


class TagUpdate(BaseModel):
    """点位资料更新。tag_key 与所属设备不可改。"""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    value_type: Optional[str] = Field(default=None, max_length=20)
    unit: Optional[str] = Field(default=None, max_length=30)
    map_target: Optional[str] = Field(default=None, min_length=1, max_length=100)
    fill_target: Optional[str] = Field(default=None, max_length=100)
    is_enabled: Optional[bool] = None


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
