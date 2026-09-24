"""KU-AI 知识库 Pydantic Schemas（KR-D12，S3 Phase 1）。

请求模型 extra=forbid，禁止夹带 tenantId 等未声明字段；响应模型不回
tenant_id / embedding 向量。业务规则（status 闭集、embedding_model_id 同租户
embed 归属、chunk 参数约束、file_uuid/raw_content 二选一）在服务层校验并抛
400，不在 schema 层拦截（pydantic 校验失败是 422）。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200, description="知识库名称（组织内唯一）")
    description: Optional[str] = Field(default=None, description="知识库描述")
    embedding_model_id: Optional[int] = Field(
        default=None, ge=1, description="Embedding 模型目录行 ID（须本租户 embed 启用行；空=回落）"
    )
    chunk_size: Optional[int] = Field(
        default=None, ge=1, description="切块大小；空=回落租户可运营配置"
    )
    chunk_overlap: Optional[int] = Field(
        default=None, ge=0, description="切块重叠；约束 >0 且 <chunk_size（服务层）"
    )
    expand_enabled: Optional[bool] = Field(
        default=None, description="检索前有限展开开关；空=回落租户配置（默认开）"
    )
    status: Optional[str] = Field(default=None, max_length=20, description="启用|停用，缺省启用")


class KnowledgeBaseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    # 显式传 null 表示清空回落租户配置/默认 embed；省略表示不动
    embedding_model_id: Optional[int] = Field(default=None, ge=1)
    chunk_size: Optional[int] = Field(default=None, ge=1)
    chunk_overlap: Optional[int] = Field(default=None, ge=0)
    expand_enabled: Optional[bool] = None
    status: Optional[str] = Field(default=None, max_length=20)


class KnowledgeBaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    name: str
    description: Optional[str] = None
    embedding_model_id: Optional[int] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    expand_enabled: Optional[bool] = None
    status: str
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseOption(BaseModel):
    """知识库下拉项（档案勾选 knowledge_ids / 对话页选库用）。"""

    id: int
    name: str
    description: Optional[str] = None


class DocumentCreate(BaseModel):
    """文档上传：file_uuid（对象存储读流）与 raw_content（文本直存）二选一，
    服务层校验缺一 400；source_type 决定解析路由（pdf|doc|docx|ppt|pptx|
    xls|xlsx|md|txt）。
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=300, description="文档标题")
    source_type: str = Field(..., min_length=1, max_length=20, description="来源类型（解析路由）")
    file_uuid: Optional[str] = Field(
        default=None, max_length=36, description="附件 file_uuid（对象存储读流）"
    )
    raw_content: Optional[str] = Field(
        default=None, max_length=200000, description="原文内容（文本类来源直存）"
    )


class DocumentListOut(BaseModel):
    """文档列表项：DocumentOut 摘去 ``raw_content`` 全文（列表不回大字段）。
    faq_* 遗留列不接产品，不回；不回 tenant_id。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    knowledge_id: Optional[int] = None
    title: str
    source_type: str
    file_uuid: Optional[str] = None
    status: str
    chunk_count: int = 0
    error_message: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class DocumentOut(DocumentListOut):
    """文档详情响应：列表项 + ``raw_content`` 全文（仅 detail 端点回）。"""

    raw_content: Optional[str] = None


class ChunkOut(BaseModel):
    """切块只读浏览：不回 embedding / embedding_vector / tenant_id。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    chunk_index: int
    content: str
    char_count: int = 0
    created_at: datetime
