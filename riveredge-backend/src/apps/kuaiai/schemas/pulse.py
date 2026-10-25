"""KU-AI 异常感知 Pulse Schemas（spec 182；契约对齐设计 §6.2/§11.3）。

- 统一异常项字段固定为设计 §6.2 闭集；新增字段须回写设计与 spec；
- errors[] 只含脱敏 code/message，不回堆栈、SQL、资源 ID；
- summary 只统计成功 detector 产出，失败领域不计为 0。
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class PulseItemOut(BaseModel):
    """统一异常项（设计 §6.2）。"""

    id: str = Field(description="稳定项 ID：{domain}:{rule_code}:{resource_id}")
    domain: str = Field(
        description="production|inventory|sales|quality|equipment"
    )
    severity: str = Field(description="info|warning|error|critical")
    priority: str = Field(description="low|medium|high")
    title: str
    fact: str = Field(description="事实摘要（不含客户敏感明细/SQL/堆栈）")
    suggestion: str
    resource_type: str
    resource_id: str
    resource_uuid: Optional[str] = None
    route: Optional[str] = Field(
        default=None, description="服务端白名单业务路由；不可用为 null"
    )
    detected_at: datetime
    rule_code: str


class PulseSummaryOut(BaseModel):
    """汇总只统计成功 detector 的筛选后结果集。"""

    total: int = 0
    high_priority: int = 0
    critical: int = 0
    warning_or_error: int = 0
    domain_count: int = 0


class PulseSourceOut(BaseModel):
    """领域内来源级状态（spec 220 X8=a）。

    status 闭集 ok|no_permission|unavailable；非 ok 来源由前端渲染
    占位小节（无权/暂不可用），count 为该来源贡献的信号条数。
    """

    key: str
    label: str
    status: str = Field(description="ok|no_permission|unavailable")
    count: int = 0


class PulseGroupOut(BaseModel):
    domain: str
    label: str
    count: int = Field(description="该领域筛选后总条数（非本页条数）")
    items: List[PulseItemOut] = Field(default_factory=list)
    sources: List[PulseSourceOut] = Field(
        default_factory=list,
        description="spec 220：来源级状态；旧前端忽略该字段仍可用",
    )


class PulseErrorOut(BaseModel):
    """局部错误（脱敏）：permission_denied|timeout|detector_error|not_connected。"""

    domain: str
    code: str
    message: str


class PulseOut(BaseModel):
    summary: PulseSummaryOut
    groups: List[PulseGroupOut] = Field(default_factory=list)
    errors: List[PulseErrorOut] = Field(default_factory=list)
    complete: bool = Field(
        default=True,
        description="任一已实现 detector 失败/越权时为 false；未接入领域不影响",
    )
    generated_at: datetime
