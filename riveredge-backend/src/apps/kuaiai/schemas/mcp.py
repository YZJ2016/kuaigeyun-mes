"""KU-AI MCP 白名单 Pydantic Schemas（KR-D11，S4）。

请求模型 extra=forbid，禁止夹带 tenantId 等未声明字段；响应模型不回
tenant_id / token 明文——token 仅回打码占位（"****" + token_configured，
口径同 catalog_service.masked_api_key_fields）。业务规则（transport 仅
http、endpoint 出站地址守卫、allowed_tools 非空+SQL 黑名单、status 闭集）
在服务层经 services/mcp_guard 校验并抛 400，不在 schema 层拦截
（pydantic 校验失败是 422）。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class McpServerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=64, description="服务器代码（组织内唯一）")
    name: str = Field(..., min_length=1, max_length=100, description="服务器名称")
    transport: Optional[str] = Field(
        default=None, max_length=20, description="传输类型（仅 http，缺省 http）"
    )
    endpoint: str = Field(
        ..., min_length=1, max_length=500, description="MCP 服务端点 URL（http/https）"
    )
    token: Optional[str] = Field(
        default=None, max_length=4096, description="Bearer Token（只写不回明文）"
    )
    allowed_tools: str = Field(
        ..., min_length=1, max_length=4096, description="允许工具名 CSV（非空；SQL 类工具名拒绝）"
    )
    status: Optional[str] = Field(default=None, max_length=20, description="启用|停用，缺省启用")


class McpServerUpdate(BaseModel):
    """全部 Optional；省略=不动。token 显式 null=清空，打码占位/空白=保留原值。"""

    model_config = ConfigDict(extra="forbid")

    code: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    transport: Optional[str] = Field(default=None, max_length=20)
    endpoint: Optional[str] = Field(default=None, min_length=1, max_length=500)
    token: Optional[str] = Field(default=None, max_length=4096)
    allowed_tools: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    status: Optional[str] = Field(default=None, max_length=20)


class McpServerOut(BaseModel):
    """MCP 服务器行响应。token 恒为打码占位或 None，绝不回明文/tenant_id。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    code: str
    name: str
    transport: str
    endpoint: str
    token: Optional[str] = None
    token_configured: bool = False
    allowed_tools: str
    status: str
    created_at: datetime
    updated_at: datetime


class McpServerOption(BaseModel):
    """MCP 服务器下拉项（Agent 档案勾选 mcp_server_ids 用）；不含连接信息。"""

    id: int
    name: str
    code: str
