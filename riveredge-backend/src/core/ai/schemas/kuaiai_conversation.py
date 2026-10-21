"""KU-AI 助手对话历史 API Schema。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from core.schemas.base import BaseSchema


class KuAiStoredMessageSchema(BaseModel):
    role: str = Field(..., min_length=1, max_length=32)
    content: str = Field(..., max_length=200_000)
    speaker_name: Optional[str] = Field(default=None, max_length=100, description="发言显示名")
    spoken_at: Optional[str] = Field(
        default=None,
        max_length=32,
        description="发言时刻（站点墙钟 YYYY-MM-DD HH:MM:SS）",
    )


class KuAiConversationSummarySchema(BaseSchema):
    id: str = Field(..., description="会话 UUID")
    title: str
    updated_at: str = Field(..., description="站点墙钟时间")
    last_speaker_name: Optional[str] = Field(default=None, description="末条消息发言者")
    last_spoken_at: Optional[str] = Field(default=None, description="末条消息发言时刻")
    inquirer_name: Optional[str] = Field(default=None, description="首条用户提问的发言显示名")


class KuAiConversationDetailSchema(KuAiConversationSummarySchema):
    messages: List[KuAiStoredMessageSchema] = Field(default_factory=list)


class KuAiConversationListResponse(BaseModel):
    items: List[KuAiConversationSummarySchema] = Field(default_factory=list)


class KuAiConversationUpsertBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    messages: List[KuAiStoredMessageSchema] = Field(default_factory=list)


class KuAiConversationCreateBody(BaseModel):
    id: str = Field(..., min_length=8, max_length=36, description="客户端生成的会话 UUID")
    title: str = Field(..., min_length=1, max_length=200)
    messages: List[KuAiStoredMessageSchema] = Field(default_factory=list)


class KuAiConversationImportBody(BaseModel):
    items: List[KuAiConversationCreateBody] = Field(..., max_length=80)
