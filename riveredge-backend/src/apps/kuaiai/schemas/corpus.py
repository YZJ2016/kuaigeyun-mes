"""KU-AI 知识语料运营视图 Schemas（spec 183；设计 §11.4）。

契约逐字对齐设计 §11.4：列表项不回 raw_content/tenant_id/存储 file_uuid；
写请求 extra=forbid，禁止夹带未声明字段。
"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class CorpusItemOut(BaseModel):
    """跨库语料列表项。

    ``type`` 由服务层从 ``source_type``/``file_uuid`` 推导（faq|text|file）；
    ``error_summary`` 为已脱敏失败摘要（业务文案或 ``Type@stage`` 截断），
    不回内部堆栈/路径；不回 ``raw_content`` 全文（详情走既有文档 API）。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    knowledge_id: Optional[int] = None
    knowledge_name: Optional[str] = None
    title: str
    type: str = Field(description="faq|text|file，由 source_type/file_uuid 推导")
    source_type: str
    chunk_count: int = 0
    status: str = Field(description="pending|parsing|ready|failed")
    error_summary: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class CorpusListOut(BaseModel):
    items: List[CorpusItemOut]
    total: int
    page: int
    page_size: int


class CorpusKnowledgeOption(BaseModel):
    """语料页知识库下拉项：仅当前租户启用库（id + name）。"""

    id: int
    name: str


class CorpusFaqCreate(BaseModel):
    """POST /operations/corpus/faqs 请求体：必选本租户启用知识库。

    问题/答案必填；生成正文 ``问题：{q}\\n答案：{a}`` 合计 ≤200000 由服务层
    复核（answer 上限随 question 长度收紧，故此处只放 schema 硬顶）。
    """

    model_config = ConfigDict(extra="forbid")

    knowledge_id: int = Field(ge=1)
    question: str = Field(min_length=1, max_length=300)
    answer: str = Field(min_length=1, max_length=200000)
    is_active: bool = True


class CorpusSeedFaqsIn(BaseModel):
    """POST /operations/corpus/seed-faqs 请求体（当前闭集 missing_only）。"""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["missing_only"] = "missing_only"
    knowledge_id: int = Field(ge=1)


class CorpusSeedFaqsOut(BaseModel):
    created: int
    skipped: int


class CorpusBatchIn(BaseModel):
    """批量索引/删除请求体：1..100 个文档 ID。"""

    model_config = ConfigDict(extra="forbid")

    ids: List[int] = Field(min_length=1, max_length=100)


class CorpusBatchItemOut(BaseModel):
    """批量操作单项结果：error 为脱敏文案（不存在/业务错误/操作失败）。"""

    id: int
    success: bool
    error: Optional[str] = None


class CorpusBatchOut(BaseModel):
    items: List[CorpusBatchItemOut]
