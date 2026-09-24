"""KU-AI 会话/消息 Pydantic Schemas。

响应模型一律不回 tenant_id；请求模型 extra=forbid，禁止夹带 tenantId 等未声明字段。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ChatSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(default=None, max_length=300, description="会话标题，留空由首条消息生成")
    # 归属校验在服务层：S2 起挂接前复核本租户档案（跨租户 404）
    agent_id: Optional[int] = Field(default=None, description="Agent 档案 ID（S2 起装配使用）")
    model: Optional[str] = Field(default=None, max_length=100, description="会话选用模型名")


class ChatSessionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(default=None, max_length=300)
    agent_id: Optional[int] = None  # 同上：服务层复核本租户档案归属
    model: Optional[str] = Field(default=None, max_length=100)


class ChatSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    user_id: int
    title: str
    agent_id: Optional[int] = None
    model: Optional[str] = None
    last_message_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    session_id: int
    seq: int
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    created_at: datetime
