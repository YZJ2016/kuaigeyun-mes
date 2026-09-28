"""指令创建、回执与消息列表。"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class CommandCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    function_key: str = Field(..., min_length=1, max_length=100)
    params: dict[str, Any] = Field(default_factory=dict)


class CommandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    device_id: int
    function_key: str
    params: dict
    dispatch_channel: str
    status: str
    result: Optional[dict] = None
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class CommandResultIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    command_uuid: str
    success: bool
    result: Optional[dict] = None
    error_message: Optional[str] = None


class MessageLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    device_id: int
    direction: str
    msg_type: str
    payload: Optional[dict] = None
    result: str
    error_message: Optional[str] = None
    created_at: datetime
