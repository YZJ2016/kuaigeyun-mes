"""KU-AI Tool 目录 Pydantic Schemas（spec 189）。

目录项由后端 manifest ``ai_tools`` 声明下发，前端档案页/消息轨迹
不再维护本地 Tool 名闭集与中文映射表。``kind``（read|write）是
spec 191 能力绑定的依赖字段，必须随目录下发。
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class ToolCatalogItem(BaseModel):
    """一个可装配 Tool 的目录视图（不含 handler 路径、参数 schema）。"""

    name: str = Field(..., description="Tool 名（ENABLED_TOOL_NAMES 闭集内）")
    label: str = Field(..., description="中文显示名（manifest ai_tools[].label）")
    description: Optional[str] = Field(default=None, description="Tool 描述")
    kind: str = Field(..., description="read|write")
    permission: Optional[str] = Field(
        default=None, description="业务权限码（一 Tool 一码，SC-D7）"
    )
    permissions_any: Optional[List[str]] = Field(
        default=None,
        description="任一命中即放行的多权限码（spec 207 X2=b，与 permission 二选一）",
    )
