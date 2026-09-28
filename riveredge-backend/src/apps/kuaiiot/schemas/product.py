"""产品、批量建设备与趋势的请求响应。批量创建响应含当次凭据。"""

from datetime import datetime
from typing import Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ProductTagIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag_key: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)
    value_type: str = Field(default="number", max_length=20)
    unit: Optional[str] = Field(default=None, max_length=30)
    map_target: str = Field(..., min_length=1, max_length=100)
    fill_target: Optional[str] = Field(default=None, max_length=100)
    is_enabled: bool = True


class ProductEventIn(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    event_key: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)
    severity: str = Field(
        default="info",
        max_length=20,
        validation_alias=AliasChoices("severity", "level"),
    )
    message: Optional[str] = None


class ProductFunctionParamIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str = Field(..., min_length=1, max_length=100)
    name: str = ""
    value_type: str = "number"
    required: bool = False


class ProductEdgeActionIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str = "modbus_write"
    param_key: str = "value"
    address: Optional[int] = None
    data_type: str = "uint16"
    scale: float = 1.0


class ProductFunctionIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    function_key: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)
    timeout_seconds: Optional[int] = Field(default=None, ge=1)
    params: list[ProductFunctionParamIn] = Field(default_factory=list)
    edge_action: Optional[ProductEdgeActionIn] = None


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    tags: list[ProductTagIn] = Field(default_factory=list)
    events: list[ProductEventIn] = Field(default_factory=list)
    functions: list[ProductFunctionIn] = Field(default_factory=list)
    remark: Optional[str] = None


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    tags: Optional[list[ProductTagIn]] = None
    events: Optional[list[ProductEventIn]] = None
    functions: Optional[list[ProductFunctionIn]] = None
    remark: Optional[str] = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    code: str
    name: str
    description: Optional[str] = None
    tags: list
    events: list = Field(default_factory=list)
    functions: list = Field(default_factory=list)
    remark: Optional[str] = None


class DeviceBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int
    name_prefix: str = Field(..., min_length=1, max_length=80)
    code_prefix: str = Field(..., min_length=1, max_length=40)
    count: int = Field(..., ge=1)


class BatchDeviceOut(BaseModel):
    id: int
    uuid: str
    code: str
    name: str
    product_id: int
    device_token: str


class OfflineRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    device_id: Optional[int] = None
    severity: str = Field(default="warning", max_length=20)


class TrendWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: int
    tag_key: str = Field(..., min_length=1, max_length=100)
    value: float
    sampled_at: Optional[datetime] = None


class TrendPointOut(BaseModel):
    time: datetime
    value: float
