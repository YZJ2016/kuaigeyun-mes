"""KU-AI 模型目录 Pydantic Schemas（KR-D5）。

请求模型 extra=forbid，禁止夹带 tenantId 等未声明字段；
响应模型不回 api_key 明文/cipher/tenant_id——provider 详情 api_key 仅回
打码占位（复用 IntegrationConfig 打码口径，见 catalog_service.masked_api_key）。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LlmProviderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=64, description="厂商代码（组织内唯一）")
    name: str = Field(..., min_length=1, max_length=100, description="厂商名称")
    base_url: str = Field(..., min_length=1, max_length=500, description="OpenAI 兼容端点 base_url")
    api_key: Optional[str] = Field(default=None, max_length=500, description="API Key（只写不回明文）")
    provider_type: Optional[str] = Field(
        default=None, max_length=50, description="可选模板标签（非闭集枚举，不挡自定义保存）"
    )
    status: Optional[str] = Field(default=None, max_length=20, description="启用|停用，缺省启用")


class LlmProviderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    base_url: Optional[str] = Field(default=None, min_length=1, max_length=500)
    # api_key 语义同 IntegrationConfig：传打码占位/空串/省略均视为保留原值
    api_key: Optional[str] = Field(default=None, max_length=500)
    provider_type: Optional[str] = Field(default=None, max_length=50)
    status: Optional[str] = Field(default=None, max_length=20)


class LlmProviderOut(BaseModel):
    """厂商行响应。api_key 恒为打码占位或 None，绝不回明文/cipher。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    code: str
    name: str
    base_url: str
    api_key: Optional[str] = None
    api_key_configured: bool = False
    provider_type: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime


# model_* 字段名与 pydantic 保护命名空间冲突，本模块统一关闭
_NO_PROTECTED = {"protected_namespaces": ()}


class LlmModelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", **_NO_PROTECTED)

    provider_id: int = Field(..., ge=1, description="所属厂商目录行 ID")
    model_name: str = Field(..., min_length=1, max_length=200, description="模型名（自由填）")
    model_type: str = Field(..., max_length=20, description="chat|embed|vision")
    status: Optional[str] = Field(default=None, max_length=20, description="启用|停用，缺省启用")


class LlmModelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", **_NO_PROTECTED)

    provider_id: Optional[int] = Field(default=None, ge=1)
    model_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    model_type: Optional[str] = Field(default=None, max_length=20)
    status: Optional[str] = Field(default=None, max_length=20)


class LlmModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, **_NO_PROTECTED)

    id: int
    uuid: str
    provider_id: int
    model_name: str
    model_type: str
    status: str
    created_at: datetime
    updated_at: datetime


class LlmModelOption(BaseModel):
    """模型下拉项：不含 api_key/base_url 等连接信息。"""

    model_config = ConfigDict(**_NO_PROTECTED)

    id: int
    provider_id: int
    provider_name: Optional[str] = None
    model_name: str
    model_type: str
