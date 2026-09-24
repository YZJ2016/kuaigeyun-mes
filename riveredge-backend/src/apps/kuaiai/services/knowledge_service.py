"""KU-AI S3 知识文档服务（KR-D12 / 设计 §9）。

文档/切块/解析面（KB 管理面在 knowledge_base_service，并行单元）：

- 归属校验统一入口 ``_get_kb`` / ``get_document``：tenant_id 强过滤，
  跨租户/软删/不存在一律 404（KR-I1/I2）；
- ``create_document``：KB 启用校验 + ``file_uuid``/``raw_content`` 二选一
  必填；``file_uuid`` 经 ``FileService.get_file_by_uuid`` 复核归属；
- ``delete_document``：同一事务软删 chunks；
- ``request_parse``：投递 taskiq ``rag_reindex``（探测点已存在于
  ``core/tasks/ai_tasks.py``，KR-I6 显式 tenant_id 参数形态）；
- ``index_document``：入口 ``select_for_update`` 行锁串行化并发 job
  （崩溃残留 parsing 自愈重跑）；解析→切块→embedding→事务写 chunks
  的失败关闭状态机（业务异常 ``error_message`` 存可读文案、未知异常
  脱敏 ``Type@stage``，不残留半截 chunk）。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Tuple
from uuid import uuid4

from loguru import logger
from tortoise.transactions import in_transaction

from apps.kuaiai.constants import STATUS_ENABLED
from apps.kuaiai.models.knowledge import (
    KuaiaiKnowledgeBase,
    KuaiaiKnowledgeChunk,
    KuaiaiKnowledgeDocument,
)
from apps.kuaiai.services.document_parsers import extract_text
from apps.kuaiai.services.retrieval import resolve_embed_model_id
from core.utils.timezone_utils import make_aware, now_utc
from infra.exceptions.exceptions import (
    BusinessLogicError,
    NotFoundError,
    ValidationError,
)

_EMBED_DIM = 768

# 切块参数回落链：库列 → 租户可运营配置（SystemParameter）→ 默认
_DEFAULT_CHUNK_SIZE = 800
_DEFAULT_CHUNK_OVERLAP = 100
_PARAM_CHUNK_SIZE = "kuaiai_rag_chunk_size"
_PARAM_CHUNK_OVERLAP = "kuaiai_rag_chunk_overlap"

# 文档解析状态机（沿用表列既有写法 pending|parsing|ready|failed）
_STATUS_PENDING = "pending"
_STATUS_PARSING = "parsing"
_STATUS_READY = "ready"
_STATUS_FAILED = "failed"

# request_parse 去重窗口：status='parsing' 且 updated_at 落在该窗口内视为
# 进行中拒绝重复投递；超出窗口的陈旧 parsing 判定为崩溃残留，放行重投（自愈）
_PARSING_FRESH_WINDOW = timedelta(minutes=30)

# create_document source_type 白名单：file_uuid 路径允许全部解析路由类型；
# raw_content 文本直存仅 txt|md（其余类型应走附件路径）
_FILE_SOURCE_TYPES = frozenset(
    {"pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "md", "txt"}
)
_RAW_SOURCE_TYPES = frozenset({"txt", "md"})
# raw_content 长度上限（schema max_length 之外的 service 双重校验）
_RAW_CONTENT_MAX_LENGTH = 200000

_DELETE_CHUNKS_SQL = (
    'DELETE FROM "apps_kuaiai_knowledge_chunks" '
    'WHERE "tenant_id" = $1 AND "document_id" = $2'
)
# embedding_vector 物理列 vector(768) 仅占位映射，写入走原始 SQL ::vector 强转；
# embedding JSONB 冗余列不重复写（KR-G7 前单向量列为准）
_INSERT_CHUNK_SQL = (
    'INSERT INTO "apps_kuaiai_knowledge_chunks" '
    '("uuid", "tenant_id", "document_id", "chunk_index", "content", '
    '"char_count", "embedding_vector") '
    "VALUES ($1, $2, $3, $4, $5, $6, $7::vector)"
)
_MARK_READY_SQL = (
    'UPDATE "apps_kuaiai_knowledge_documents" '
    'SET "status" = $1, "chunk_count" = $2, "error_message" = NULL, '
    '"updated_at" = $3 '
    'WHERE "tenant_id" = $4 AND "id" = $5'
)


async def _param_int(tenant_id: int, key: str, default: int) -> int:
    """租户可运营配置 int 读取；服务异常/未配置/非法值按默认处理。"""
    try:
        from core.services.system.system_parameter_service import (
            SystemParameterService,
        )

        param = await SystemParameterService.get_parameter(tenant_id, key)
        if param is None:
            return default
        return int(param.get_value())
    except Exception:
        return default


async def _resolve_chunk_params(
    tenant_id: int, kb: KuaiaiKnowledgeBase
) -> Tuple[int, int]:
    """(chunk_size, chunk_overlap)：库列 → 租户参数 → 默认 800/100。

    约束 ``overlap > 0 且 < chunk_size`` 不满足时整体回落默认对
    （不混用半套非法参数）。
    """
    size = kb.chunk_size
    if size is None:
        size = await _param_int(tenant_id, _PARAM_CHUNK_SIZE, _DEFAULT_CHUNK_SIZE)
    overlap = kb.chunk_overlap
    if overlap is None:
        overlap = await _param_int(
            tenant_id, _PARAM_CHUNK_OVERLAP, _DEFAULT_CHUNK_OVERLAP
        )
    try:
        size = int(size)
        overlap = int(overlap)
    except (TypeError, ValueError):
        return _DEFAULT_CHUNK_SIZE, _DEFAULT_CHUNK_OVERLAP
    if size <= 0 or overlap <= 0 or overlap >= size:
        return _DEFAULT_CHUNK_SIZE, _DEFAULT_CHUNK_OVERLAP
    return size, overlap


def _vector_literal(vector: List[float]) -> str:
    return "[" + ",".join(str(float(v)) for v in vector) + "]"


async def _extract_document_text(tenant_id: int, doc) -> str:
    """取原文：file_uuid → 对象存储读流 → extract_text；raw_content 直接用。"""
    file_uuid = (getattr(doc, "file_uuid", None) or "").strip()
    if file_uuid:
        from core.services.file.file_service import FileService

        data = await FileService.get_file_content(tenant_id, file_uuid)
        return await extract_text(getattr(doc, "source_type", "") or "", data)
    raw = getattr(doc, "raw_content", None)
    if raw and str(raw).strip():
        return str(raw)
    raise BusinessLogicError("文档缺少可解析内容（file_uuid/raw_content 均为空）")


def _audit_create(user: Any) -> Dict[str, Any]:
    """文档行落库审计字段：created_by/updated_by 及 *_name（迁移 454 已补列）。"""
    if user is None or getattr(user, "id", None) is None:
        return {}
    name = getattr(user, "full_name", None) or getattr(user, "username", None)
    return {
        "created_by": user.id,
        "created_by_name": name,
        "updated_by": user.id,
        "updated_by_name": name,
    }


class KnowledgeService:
    """文档/切块/解析面（类方法集合，对齐 router 调用形态）。"""

    @classmethod
    async def _get_kb(
        cls, tenant_id: int, knowledge_id: int
    ) -> KuaiaiKnowledgeBase:
        kb = await KuaiaiKnowledgeBase.get_or_none(
            tenant_id=tenant_id,
            id=int(knowledge_id),
            deleted_at__isnull=True,
        )
        if kb is None:
            raise NotFoundError("知识库", str(knowledge_id))
        return kb

    @classmethod
    async def _get_enabled_kb(
        cls, tenant_id: int, knowledge_id: int
    ) -> KuaiaiKnowledgeBase:
        kb = await cls._get_kb(tenant_id, knowledge_id)
        if kb.status != STATUS_ENABLED:
            raise BusinessLogicError("知识库已停用")
        return kb

    @classmethod
    async def list_documents(
        cls,
        tenant_id: int,
        knowledge_id: int,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """库下文档分页 {items,total}；先复核库归属（跨租户 404）。"""
        await cls._get_kb(tenant_id, knowledge_id)
        qs = KuaiaiKnowledgeDocument.filter(
            tenant_id=tenant_id,
            knowledge_id=int(knowledge_id),
            deleted_at__isnull=True,
        )
        total = await qs.count()
        items = await (
            qs.order_by("-id")
            .offset(max(0, (int(page) - 1) * int(page_size)))
            .limit(int(page_size))
        )
        return {"items": list(items), "total": total}

    @classmethod
    async def create_document(
        cls,
        tenant_id: int,
        user,
        knowledge_id: int,
        payload,
    ) -> KuaiaiKnowledgeDocument:
        """新建文档：KB 归属+启用校验；file_uuid/raw_content 二选一必填。

        另校验：title 去空白非空；source_type 建时白名单（file_uuid 路径放
        行全部解析路由类型，raw_content 文本直存仅 txt|md 且 ≤200000 字符）。
        """
        await cls._get_enabled_kb(tenant_id, knowledge_id)
        file_uuid = (getattr(payload, "file_uuid", None) or "").strip() or None
        raw = getattr(payload, "raw_content", None)
        raw = raw if (raw or "").strip() else None
        if file_uuid and raw:
            raise BusinessLogicError("file_uuid 与 raw_content 仅可二选一")
        if not file_uuid and not raw:
            raise BusinessLogicError("file_uuid 与 raw_content 须至少提供一项")
        title = str(payload.title).strip()
        if not title:
            raise BusinessLogicError("文档标题不能为空")
        source_type = (payload.source_type or "").strip().lower()
        if file_uuid:
            if source_type not in _FILE_SOURCE_TYPES:
                raise BusinessLogicError(
                    "source_type 不在支持范围（pdf|doc|docx|ppt|pptx|xls|xlsx|md|txt）"
                )
            # 归属复核：跨租户/不存在 → NotFoundError（404）
            from core.services.file.file_service import FileService

            await FileService.get_file_by_uuid(tenant_id, file_uuid)
        else:
            if source_type not in _RAW_SOURCE_TYPES:
                raise BusinessLogicError("raw_content 直存仅支持 txt|md 来源类型")
            if len(raw) > _RAW_CONTENT_MAX_LENGTH:
                raise BusinessLogicError(
                    f"raw_content 长度超过 {_RAW_CONTENT_MAX_LENGTH} 字符上限"
                )
        return await KuaiaiKnowledgeDocument.create(
            tenant_id=tenant_id,
            knowledge_id=int(knowledge_id),
            title=title,
            source_type=source_type,
            file_uuid=file_uuid,
            raw_content=raw,
            status=_STATUS_PENDING,
            **_audit_create(user),
        )

    @classmethod
    async def get_document(
        cls, tenant_id: int, document_id: int
    ) -> KuaiaiKnowledgeDocument:
        doc = await KuaiaiKnowledgeDocument.get_or_none(
            tenant_id=tenant_id,
            id=int(document_id),
            deleted_at__isnull=True,
        )
        if doc is None:
            raise NotFoundError("知识文档", str(document_id))
        return doc

    @classmethod
    async def delete_document(cls, tenant_id: int, document_id: int) -> None:
        """删文档同事务软删 chunks（含向量行）。"""
        doc = await cls.get_document(tenant_id, document_id)
        now = now_utc()
        async with in_transaction():
            await KuaiaiKnowledgeChunk.filter(
                tenant_id=tenant_id,
                document_id=doc.id,
                deleted_at__isnull=True,
            ).update(deleted_at=now)
            doc.deleted_at = now
            await doc.save(update_fields=["deleted_at", "updated_at"])

    @classmethod
    async def request_parse(
        cls, tenant_id: int, user_id: int, document_id: int
    ):
        """投递 rag_reindex 异步任务（taskiq），返回 job 状态对象。

        前置校验（投递前拒绝，不再投递后空跑）：
        - 归属库停用 → 400（m9）；
        - ``status='parsing'`` 且 ``updated_at`` 在 30 分钟窗口内 → 400
          「解析进行中」；超出窗口的陈旧 parsing 判定为崩溃残留，放行
          重新投递（自愈，M1）。
        """
        doc = await cls.get_document(tenant_id, document_id)
        if doc.knowledge_id is None:
            raise BusinessLogicError("文档未挂载知识库")
        await cls._get_enabled_kb(tenant_id, doc.knowledge_id)
        updated_at = getattr(doc, "updated_at", None)
        if doc.status == _STATUS_PARSING and updated_at is not None:
            if updated_at.tzinfo is None:
                updated_at = make_aware(updated_at, "UTC")
            if updated_at > now_utc() - _PARSING_FRESH_WINDOW:
                raise BusinessLogicError("解析进行中，请稍后")
        from core.ai.jobs import AiJobService

        return await AiJobService.create_job(
            tenant_id=tenant_id,
            user_id=user_id,
            job_type="rag_reindex",
            payload={"document_id": int(document_id)},
        )

    @classmethod
    async def list_chunks(
        cls,
        tenant_id: int,
        document_id: int,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """切块只读浏览 {items,total}；先复核文档归属（跨租户 404）。"""
        await cls.get_document(tenant_id, document_id)
        qs = KuaiaiKnowledgeChunk.filter(
            tenant_id=tenant_id,
            document_id=int(document_id),
            deleted_at__isnull=True,
        )
        total = await qs.count()
        # m4：只取 ChunkOut 需要列，不拉 embedding/embedding_vector 大字段
        items = await (
            qs.order_by("chunk_index")
            .offset(max(0, (int(page) - 1) * int(page_size)))
            .limit(int(page_size))
            .values("id", "chunk_index", "content", "char_count", "created_at")
        )
        return {"items": list(items), "total": total}

    @classmethod
    async def index_document(cls, tenant_id: int, document_id: int) -> None:
        """taskiq ``rag_reindex`` 探测点（KR-I6：tenant_id 显式参数）。

        并发幂等（M1）：入口在 ``in_transaction()`` 内对文档行
        ``select_for_update()`` 行锁，并发 job 在此串行化——后到者等
        前一 job 提交后再读行。锁内读到 ``status='parsing'`` 意味着前一
        job 崩溃残留（行锁随连接释放但 status 停在中途），按重解析继续
        跑（自愈）。chunks 侧再由部分唯一索引
        ``uidx_kuaiai_kchunk_doc_chunk``（迁移 20260925120000）兜底双写。

        状态机：归属+启用校验（不过→抛错回滚，不动 status）→ ``parsing`` →
        取原文/切块/embedding → 事务内删旧 chunks + 逐条写向量 + 置
        ``ready`` 回填 ``chunk_count``。任何步骤异常 → ``failed`` +
        ``error_message``（业务异常存可读文案截 500；未知异常仍
        ``Type@stage`` 脱敏，不落原文/key），并清掉残留 chunks
        （重解析语义：失败时旧 chunks 也删，不留半截）。
        """
        async with in_transaction():
            doc = await (
                KuaiaiKnowledgeDocument.filter(
                    tenant_id=tenant_id,
                    id=int(document_id),
                    deleted_at__isnull=True,
                )
                .select_for_update()
                .first()
            )
            if doc is None:
                raise NotFoundError("知识文档", str(document_id))
            if doc.knowledge_id is None:
                raise BusinessLogicError("文档未挂载知识库")
            kb = await cls._get_enabled_kb(tenant_id, doc.knowledge_id)

            doc.status = _STATUS_PARSING
            doc.error_message = None
            await doc.save(
                update_fields=["status", "error_message", "updated_at"]
            )

            stage = "extract"
            try:
                text = await _extract_document_text(tenant_id, doc)

                stage = "split"
                from langchain_text_splitters import (
                    RecursiveCharacterTextSplitter,
                )

                chunk_size, chunk_overlap = await _resolve_chunk_params(
                    tenant_id, kb
                )
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=chunk_size, chunk_overlap=chunk_overlap
                )
                chunks = [
                    c for c in splitter.split_text(text) if c and c.strip()
                ]
                if not chunks:
                    raise BusinessLogicError("文档切块结果为空")

                stage = "embed"
                model_id = await resolve_embed_model_id(
                    tenant_id, kb.embedding_model_id
                )
                if model_id is None:
                    raise BusinessLogicError(
                        "未配置 embedding 模型，请先在模型目录中添加 embed 模型"
                    )
                from core.ai.runtime.model_factory import build_embeddings

                embeddings = await build_embeddings(tenant_id, model_id)
                vectors = await embeddings.aembed_documents(chunks)
                if len(vectors) != len(chunks) or any(
                    len(v) != _EMBED_DIM for v in vectors
                ):
                    # 维度 ≠768 失败关闭：不截断、不静默写入（KR-G7）
                    raise BusinessLogicError(
                        "embedding 维度与 vector(768) 不符"
                    )

                stage = "persist"
                now = now_utc()
                # 嵌套 in_transaction：外层行锁事务内的 savepoint，失败回滚到
                # savepoint 后外层仍可写 failed 状态
                async with in_transaction() as conn:
                    await conn.execute_query(
                        _DELETE_CHUNKS_SQL, [tenant_id, doc.id]
                    )
                    for idx, (content, vector) in enumerate(
                        zip(chunks, vectors)
                    ):
                        await conn.execute_query(
                            _INSERT_CHUNK_SQL,
                            [
                                str(uuid4()),
                                tenant_id,
                                doc.id,
                                idx,
                                content,
                                len(content),
                                _vector_literal(vector),
                            ],
                        )
                    await conn.execute_query(
                        _MARK_READY_SQL,
                        [_STATUS_READY, len(chunks), now, tenant_id, doc.id],
                    )
                doc.status = _STATUS_READY
                doc.chunk_count = len(chunks)
            except Exception as exc:
                logger.warning(
                    "KU-AI 文档解析失败 document_id={} stage={} error_type={}",
                    doc.id,
                    stage,
                    type(exc).__name__,
                )
                try:
                    await KuaiaiKnowledgeChunk.filter(
                        tenant_id=tenant_id, document_id=doc.id
                    ).delete()
                except Exception:
                    logger.warning(
                        "KU-AI 解析失败残留切块清理失败 document_id={}", doc.id
                    )
                doc.status = _STATUS_FAILED
                if isinstance(exc, (ValidationError, BusinessLogicError)):
                    # m7：业务异常文案本就可读，保留（截 500）便于前端展示
                    doc.error_message = str(
                        getattr(exc, "message", "") or exc
                    )[:500]
                else:
                    doc.error_message = f"{type(exc).__name__}@{stage}"
                await doc.save(
                    update_fields=["status", "error_message", "updated_at"]
                )
