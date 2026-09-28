"""星报表执行响应。字段与 UniReport executeReport 约定一致。"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecuteReportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    success: bool = True
    summary: dict[str, float | int] = Field(default_factory=dict)
