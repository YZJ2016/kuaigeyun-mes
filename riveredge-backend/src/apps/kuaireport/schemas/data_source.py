"""星报表数据源请求与响应。请求体禁止夹带 tenant_id。"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class DataSourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(default="static", max_length=20)
    config: dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None
    is_default: bool = False


class DataSourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    type: Optional[str] = Field(default=None, max_length=20)
    config: Optional[dict[str, Any]] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None


class DataSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    name: str
    type: str
    config: Optional[dict[str, Any]] = None
    description: Optional[str] = None
    is_default: bool
    is_system: bool
    created_at: datetime
    updated_at: datetime
