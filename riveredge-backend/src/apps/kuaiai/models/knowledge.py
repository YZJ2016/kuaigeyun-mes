"""KU-AI 知识库数据面（KR-D12，S3 Phase 1）

- KuaiaiKnowledgeBase：知识库父表（新建；name + embedding_model_id +
  切块参数 chunk_size/chunk_overlap/expand_enabled 可空回落租户可运营配置 +
  status 闭集 启用|停用）
- KuaiaiKnowledgeDocument：文档表（既有表 apps_kuaiai_knowledge_documents
  映射 + 新增 knowledge_id 挂库；faq_* 列本期不接产品）
- KuaiaiKnowledgeChunk：切块表（既有表映射；embedding_vector 物理列为
  pgvector vector(768)，tortoise 无原生类型，仅占位映射——向量写入/检索
  一律走原始 SQL，不经 ORM 字段读写）

embedding_model_id / knowledge_id / document_id 均不加 DB 级 FK，
归属（同租户 + model_type='embed' + 启用）由服务层复核（KR-D12/失败关闭）。
"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiaiKnowledgeBase(BaseModel):
    """KU-AI 知识库（检索与档案 knowledge_ids 的挂接单元）。"""

    class Meta:
        table = "apps_kuaiai_knowledge_bases"
        table_description = "KU-AI 知识库"
        indexes = [
            ("tenant_id",),
        ]
        # DB 侧 (tenant_id, name) 为 deleted_at IS NULL 部分唯一索引
        # （迁移 20260925110000_kuaiai_knowledge_base），软删行不占唯一键、可重建同名库
        unique_together = (("tenant_id", "uuid"), ("tenant_id", "name"))

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="组织 ID")
    name = fields.CharField(max_length=200, description="知识库名称（组织内唯一）")
    description = fields.TextField(null=True, description="知识库描述")
    embedding_model_id = fields.IntField(
        null=True,
        description="Embedding 模型目录行 ID（apps_kuaiai_llm_models.id，须本租户 model_type=embed 启用行；"
        "空=回落本租户第一条启用 embed；服务层校验，无 DB FK）",
    )
    chunk_size = fields.IntField(null=True, description="切块大小；NULL=回落租户可运营配置")
    chunk_overlap = fields.IntField(
        null=True, description="切块重叠；NULL=回落租户配置；约束 overlap>0 且 <chunk_size（服务层）"
    )
    expand_enabled = fields.BooleanField(
        null=True, description="检索前有限展开开关；NULL=回落租户配置（默认开）"
    )
    status = fields.CharField(max_length=20, default="启用", description="启用|停用")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def __str__(self) -> str:
        return f"KuaiaiKnowledgeBase: {self.id} ({self.name})"


class KuaiaiKnowledgeDocument(BaseModel):
    """KU-AI 知识文档（既有表映射 + knowledge_id 挂库）。

    faq_question/faq_answer 为既有遗留列，本期不接产品（KR-D18），仅作映射。
    status 为文档解析状态机（pending|parsing|ready|failed，服务层流转）。
    """

    class Meta:
        table = "apps_kuaiai_knowledge_documents"
        table_description = "KU-AI 知识文档"
        indexes = [
            ("tenant_id", "status"),
            ("tenant_id", "source_type"),
            ("tenant_id", "knowledge_id"),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="组织 ID")
    knowledge_id = fields.IntField(
        null=True,
        description="所属知识库 ID（apps_kuaiai_knowledge_bases.id；无 DB FK，服务层复核归属）",
    )
    title = fields.CharField(max_length=300, description="文档标题")
    source_type = fields.CharField(
        max_length=20, description="来源类型（pdf|doc|docx|ppt|pptx|xls|xlsx|md|txt|faq 等）"
    )
    raw_content = fields.TextField(null=True, description="原文内容（文本类来源直存）")
    file_uuid = fields.CharField(
        max_length=36, null=True, description="附件 file_uuid（对象存储读流解析）"
    )
    faq_question = fields.TextField(null=True, description="FAQ 问题（遗留列，本期不接产品）")
    faq_answer = fields.TextField(null=True, description="FAQ 答案（遗留列，本期不接产品）")
    status = fields.CharField(max_length=20, default="pending", description="解析状态（默认 pending）")
    chunk_count = fields.IntField(default=0, description="切块数")
    error_message = fields.TextField(null=True, description="解析失败文案")
    is_active = fields.BooleanField(default=True, description="是否参与检索")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def __str__(self) -> str:
        return f"KuaiaiKnowledgeDocument: {self.id} ({self.title})"


class KuaiaiKnowledgeChunk(BaseModel):
    """KU-AI 知识切块（含 embedding 列）。

    embedding_vector 物理列是 pgvector vector(768)（迁移 517 建列 +
    HNSW cosine 索引）；tortoise 无 vector 原生类型，这里用 TextField 占位，
    仅作模型映射——向量写入（::vector 强转）与相似度检索一律走原始 SQL，
    不经该字段读写；embedding JSONB 为既有冗余列。
    """

    class Meta:
        table = "apps_kuaiai_knowledge_chunks"
        table_description = "KU-AI 知识切块"
        indexes = [
            ("tenant_id", "document_id"),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="组织 ID")
    document_id = fields.IntField(
        description="所属文档 ID（apps_kuaiai_knowledge_documents.id；无 DB FK）"
    )
    chunk_index = fields.IntField(description="文档内切块序号")
    content = fields.TextField(description="切块文本")
    char_count = fields.IntField(default=0, description="切块字符数")
    embedding = fields.JSONField(null=True, description="向量 JSONB 冗余列（既有）")
    # 占位映射：DB 物理列 vector(768)，ORM 不读写，写入/检索走原始 SQL
    embedding_vector = fields.TextField(
        null=True, description="向量列占位（物理 vector(768)，仅原始 SQL 读写）"
    )
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def __str__(self) -> str:
        return f"KuaiaiKnowledgeChunk: doc={self.document_id} idx={self.chunk_index}"


# 兼容别名：私仓时代探测点（如 core/ai/stats_service.py 的
# _knowledge_document_count，属本应用白名单外）按旧名 KuaiKnowledgeDocument
# import；canonical 类名为 KuaiaiKnowledgeDocument。
KuaiKnowledgeDocument = KuaiaiKnowledgeDocument
