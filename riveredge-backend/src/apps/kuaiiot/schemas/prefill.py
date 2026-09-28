"""模板、告警与预填的请求响应。"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TemplateTagOut(BaseModel):
    tag_key: str
    name: str
    value_type: str
    map_target: str
    unit: Optional[str] = None


class TemplateOut(BaseModel):
    code: str
    name: str
    tags: list[TemplateTagOut]


class ApplyTemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=50)


class ApplyTemplateOut(BaseModel):
    code: str
    tag_keys: list[str]


class AlertRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    tag_key: str = Field(..., min_length=1, max_length=100)
    operator: str = Field(..., min_length=1, max_length=10)
    threshold_number: Optional[Decimal] = None
    threshold_text: Optional[str] = Field(default=None, max_length=200)
    device_id: Optional[int] = None
    equipment_uuid: Optional[str] = Field(default=None, max_length=36)
    severity: str = Field(default="warning", max_length=20)
    cooldown_seconds: int = Field(default=300, ge=0)
    notify_enabled: bool = False
    is_enabled: bool = True
    remark: Optional[str] = None


class AlertRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    code: str
    name: str
    tag_key: str
    operator: str
    threshold_number: Optional[Decimal] = None
    threshold_text: Optional[str] = None
    device_id: Optional[int] = None
    equipment_uuid: Optional[str] = None
    severity: str
    cooldown_seconds: int
    notify_enabled: bool
    is_enabled: bool
    rule_type: str


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    rule_id: Optional[int] = None
    device_id: int
    equipment_uuid: Optional[str] = None
    tag_key: str
    severity: str
    message: str
    actual_value: Optional[str] = None
    status: str
    triggered_at: datetime


class FillContextOut(BaseModel):
    equipment_uuid: str
    device_uuid: Optional[str] = None
    values: dict
