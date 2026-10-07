"""HTTP 入站请求体。未声明字段忽略，供后续切片扩展同一条路径。"""

from typing import Any, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field


class IngestBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tags: dict[str, Any] = Field(default_factory=dict, max_length=200)
    qualities: dict[str, Literal["good", "bad", "uncertain"]] = Field(default_factory=dict, max_length=200)
    events: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    timestamp: Optional[str] = None
    idempotency_key: Optional[str] = Field(default=None, max_length=128)
