"""IM API Schema。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ImConversationResponse(BaseModel):
    uuid: str
    kind: str
    title: Optional[str] = None
    is_public: bool = False
    is_pinned: bool = False
    module_codes: list[str] = Field(default_factory=list)
    member_count: int = 0
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    unread_count: int = 0


class ImConversationListResponse(BaseModel):
    items: list[ImConversationResponse]
    total: int


class ImSetPinnedRequest(BaseModel):
    is_pinned: bool


class ImMemberResponse(BaseModel):
    user_id: int
    username: str = ""
    full_name: Optional[str] = None
    label: str = ""
    role: str = "member"


class ImMemberListResponse(BaseModel):
    items: list[ImMemberResponse]
    total: int


class ImMessageResponse(BaseModel):
    uuid: str
    conversation_uuid: str
    sender_id: int
    body: str
    kind: str
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None
    mention_user_ids: list[int] = Field(default_factory=list)
    mention_ku_ai: bool = False
    created_at: datetime


class ImMessageListResponse(BaseModel):
    items: list[ImMessageResponse]
    total: int


class ImSendMessageRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    mention_user_ids: list[int] = Field(default_factory=list)
    mention_ku_ai: bool = False


class ImCreateDirectConversationRequest(BaseModel):
    peer_user_id: int = Field(gt=0)


class ImCreateGroupConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    member_user_ids: list[int] = Field(default_factory=list)
    module_codes: list[str] = Field(default_factory=list)


class ImUpdateGroupConversationRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    member_user_ids: Optional[list[int]] = None
    module_codes: Optional[list[str]] = None
