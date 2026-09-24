"""KU-AI Agent 档案/授权 Pydantic Schemas（KR-D8/D9）。

请求模型 extra=forbid，禁止夹带 tenantId；响应模型不回 tenant_id。
业务规则（闭集/互斥/空名单）在服务层校验并抛 400，不在 schema 层拦截，
以便错误语义与 spec 的 400 一致（pydantic 校验失败是 422）。
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100, description="档案名称（组织内唯一）")
    description: Optional[str] = Field(default=None, description="档案描述")
    system_prompt: Optional[str] = Field(default=None, description="系统提示词")
    default_model_id: Optional[int] = Field(
        default=None, ge=1, description="默认模型目录行 ID（须本租户 chat 启用行）"
    )
    knowledge_ids: List[int] = Field(default_factory=list, description="知识库 ID 列表")
    enabled_tools: List[str] = Field(default_factory=list, description="启用工具名（闭集子集）")
    mcp_server_ids: List[int] = Field(default_factory=list, description="MCP 白名单 ID 列表")
    status: Optional[str] = Field(default=None, max_length=20, description="启用|停用，缺省停用")
    grant_mode: str = Field(..., max_length=10, description="ROLE|USER（互斥）")


class AgentProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    # 显式传 null 表示清空默认模型；省略表示不动
    default_model_id: Optional[int] = Field(default=None, ge=1)
    knowledge_ids: Optional[List[int]] = None
    enabled_tools: Optional[List[str]] = None
    mcp_server_ids: Optional[List[int]] = None
    status: Optional[str] = Field(default=None, max_length=20)
    grant_mode: Optional[str] = Field(default=None, max_length=10)


class AgentProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    default_model_id: Optional[int] = None
    knowledge_ids: List[int] = Field(default_factory=list)
    enabled_tools: List[str] = Field(default_factory=list)
    mcp_server_ids: List[int] = Field(default_factory=list)
    status: str
    grant_mode: str
    created_at: datetime
    updated_at: datetime


class AgentProfileOption(BaseModel):
    """档案下拉项：仅当前用户有使用权的启用档案（由 grant_service 过滤）。"""

    id: int
    name: str
    description: Optional[str] = None


class AgentGrantsUpdate(BaseModel):
    """授权名单整体替换（当前 grant_mode 的一侧）。

    target_ids 语义随档案 grant_mode：ROLE=角色 id 列表，USER=用户 id 列表。
    模式切换走档案保存（PUT /agents/{id}），同事务清空对侧名单。
    """

    model_config = ConfigDict(extra="forbid")

    target_ids: List[int] = Field(default_factory=list, description="目标 ID 列表（角色或用户）")


class AgentGrantsOut(BaseModel):
    agent_id: int
    grant_mode: str
    target_ids: List[int] = Field(default_factory=list)
