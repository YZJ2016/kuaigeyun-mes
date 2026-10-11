"""KU-AI 知识语料运营视图服务（spec 183；设计 §7/§11.4）。

- 跨库扁平列表以 ``apps_kuaiai_knowledge_documents`` 为单一真源，逐查询带
  ``tenant_id``；``type`` 由 ``source_type``/``file_uuid`` 推导
  （``source_type=faq`` → ``faq``；``file_uuid`` 非空 → ``file``；其余 →
  ``text``），列表不回 ``raw_content``/tenant_id/存储键；
- FAQ 创建/出厂种子复用 ``KnowledgeService`` 同一 pending→parse→index 生命
  周期；种子幂等键 ``(tenant_id, knowledge_id, source_type=faq,
  faq_question)`` 精确匹配非软删行，同题（含人工 FAQ）只跳过绝不覆盖；
  同一知识库并发种子经库行 ``select_for_update`` 串行化；
- 批量索引/删除逐项隔离结果：跨租户/软删 ID 一律按不存在处理（无存在性
  泄露），单项失败不回滚已成功项；
- JSONL 导出：流式分批查询（硬上限），白名单序列化器只输出训练文本字段
  （type/title/question/answer/content），不含 tenant_id、UUID、错误堆栈。
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from loguru import logger
from tortoise.transactions import in_transaction

from apps.kuaiai.constants import STATUS_ENABLED
from apps.kuaiai.models.knowledge import (
    KuaiaiKnowledgeBase,
    KuaiaiKnowledgeDocument,
)
from apps.kuaiai.services.knowledge_service import KnowledgeService
from core.utils.timezone_utils import site_day_bounds_utc
from infra.exceptions.exceptions import (
    BusinessLogicError,
    NotFoundError,
    ValidationError,
)

_DOC_STATUS_CLOSED = frozenset({"pending", "parsing", "ready", "failed"})

# JSONL 导出：分批查询 + 总行数硬上限（防无界导出占内存/连接）
_EXPORT_BATCH_SIZE = 500
_EXPORT_MAX_ROWS = 20000
# error_summary 展示上限（底层 error_message 写入时已脱敏/截 500）
_ERROR_SUMMARY_MAX = 200
# 批量单项返回错误文案上限（复用业务异常可读文案）
_ITEM_ERROR_MAX = 200

# 出厂 FAQ 种子（小型内置集合，通用 MES/AI 使用问答）：
# 按 (knowledge_id, source_type=faq, faq_question) 精确匹配幂等，
# 同题人工 FAQ 只跳过、绝不覆盖。
_SEED_FAQS: Tuple[Tuple[str, str], ...] = (
    (
        "星AI 智能助手能做什么？",
        "星AI 是企业内嵌的 AI 助手：可以基于对话进行业务问答、"
        "通过只读业务工具查询授权范围内的工单、库存、采购等数据，"
        "并检索企业知识库中的文档与 FAQ 给出答案。",
    ),
    (
        "如何让智能体回答企业知识？",
        "把 FAQ、文本或文件文档加入某个启用状态的知识库并完成索引，"
        "智能体在对话中即可检索引用这些内容。文件上传与文本添加在"
        "知识库管理页完成，FAQ 可在本页直接添加。",
    ),
    (
        "知识库支持哪些文档格式？",
        "知识库文件上传支持 pdf、doc、docx、ppt、pptx、xls、xlsx、"
        "md、txt；此外还支持直接添加文本与 FAQ 问答对。",
    ),
    (
        "FAQ 与普通文档有什么区别？",
        "FAQ 以标准问答对形式入库，适合固定问题的统一答复；"
        "普通文档按原文切块索引，适合长文档检索。两者使用同一套"
        "解析、切块、向量索引与删除生命周期。",
    ),
    (
        "索引状态待索引、索引中、已索引、索引失败分别是什么意思？",
        "待索引：已保存但尚未解析；索引中：正在解析并生成向量索引；"
        "已索引：可正常参与检索；索引失败：解析或索引出错，"
        "可查看失败摘要后重试索引。",
    ),
    (
        "停用的语料还会被智能体检索到吗？",
        "不会。停用（is_active 关闭）的语料不参与向量检索；"
        "重新启用后按文档生命周期重新索引即可恢复检索。",
    ),
)


def _doc_type(doc: Any) -> str:
    """列表类型推导：faq 优先于 file_uuid 判断（source_type=faq 无附件）。"""
    if (getattr(doc, "source_type", "") or "").strip().lower() == "faq":
        return "faq"
    if (getattr(doc, "file_uuid", "") or "").strip():
        return "file"
    return "text"


def _filtered_queryset(
    tenant_id: int,
    *,
    keyword: Optional[str] = None,
    knowledge_id: Optional[int] = None,
    doc_type: Optional[str] = None,
    doc_status: Optional[str] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
):
    """跨库文档筛选基座：tenant_id + 非软删恒置，非法闭集参数静默忽略
    （路由层已用 pattern 收口，此处双保险不放大查询面）。"""
    qs = KuaiaiKnowledgeDocument.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    )
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(title__icontains=kw)
    if knowledge_id is not None:
        qs = qs.filter(knowledge_id=int(knowledge_id))
    if doc_type == "faq":
        qs = qs.filter(source_type="faq")
    elif doc_type == "file":
        qs = qs.filter(file_uuid__isnull=False)
    elif doc_type == "text":
        qs = qs.filter(file_uuid__isnull=True).exclude(source_type="faq")
    if doc_status in _DOC_STATUS_CLOSED:
        qs = qs.filter(status=doc_status)
    if created_from is not None:
        start, _ = site_day_bounds_utc(created_from)
        qs = qs.filter(created_at__gte=start)
    if created_to is not None:
        _, end = site_day_bounds_utc(created_to)
        qs = qs.filter(created_at__lt=end)
    return qs


def _to_item(doc: Any, kb_names: Dict[int, str]) -> Dict[str, Any]:
    """列表项白名单序列化：不回 raw_content/tenant_id/file_uuid。"""
    error_summary = None
    if doc.status == "failed":
        error_summary = (getattr(doc, "error_message", None) or "")[
            :_ERROR_SUMMARY_MAX
        ] or None
    return {
        "id": doc.id,
        "uuid": doc.uuid,
        "knowledge_id": doc.knowledge_id,
        "knowledge_name": kb_names.get(doc.knowledge_id),
        "title": doc.title,
        "type": _doc_type(doc),
        "source_type": doc.source_type,
        "chunk_count": doc.chunk_count or 0,
        "status": doc.status,
        "error_summary": error_summary,
        "is_active": bool(doc.is_active),
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


async def list_corpus(
    tenant_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    knowledge_id: Optional[int] = None,
    doc_type: Optional[str] = None,
    doc_status: Optional[str] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
) -> Dict[str, Any]:
    """GET /operations/corpus：跨库扁平分页 {items,total}（本租户）。"""
    qs = _filtered_queryset(
        tenant_id,
        keyword=keyword,
        knowledge_id=knowledge_id,
        doc_type=doc_type,
        doc_status=doc_status,
        created_from=created_from,
        created_to=created_to,
    )
    total = await qs.count()
    rows = await (
        qs.order_by("-id")
        .offset(max(0, (int(page) - 1) * int(page_size)))
        .limit(int(page_size))
    )
    kb_ids = {r.knowledge_id for r in rows if r.knowledge_id is not None}
    kb_names: Dict[int, str] = {}
    if kb_ids:
        kbs = await KuaiaiKnowledgeBase.filter(
            tenant_id=tenant_id,
            id__in=list(kb_ids),
        ).all()
        kb_names = {kb.id: kb.name for kb in kbs}
    return {"items": [_to_item(r, kb_names) for r in rows], "total": total}


async def knowledge_options(tenant_id: int) -> List[Dict[str, Any]]:
    """语料页知识库下拉项：仅本租户启用库（筛选/FAQ 归属必选）。

    corpus:display 可读——本接口不回描述、不回停用库，最小暴露面。
    """
    kbs = await (
        KuaiaiKnowledgeBase.filter(
            tenant_id=tenant_id,
            status=STATUS_ENABLED,
            deleted_at__isnull=True,
        )
        .order_by("id")
        .all()
    )
    return [{"id": kb.id, "name": kb.name} for kb in kbs]


async def create_faq(tenant_id: int, user: Any, payload: Any):
    """POST /operations/corpus/faqs：FAQ 语料创建（201 语料项）。

    必选本租户启用知识库（_get_enabled_kb 复核）；source_type=faq +
    faq_question/faq_answer + 生成 raw_content，落库 pending 后沿用既有
    request_parse/index_document 生命周期。
    """
    doc = await KnowledgeService.create_faq(
        tenant_id,
        user,
        payload.knowledge_id,
        question=payload.question,
        answer=payload.answer,
        is_active=payload.is_active,
    )
    kb_names: Dict[int, str] = {}
    if doc.knowledge_id is not None:
        kb = await KuaiaiKnowledgeBase.get_or_none(
            tenant_id=tenant_id,
            id=doc.knowledge_id,
            deleted_at__isnull=True,
        )
        if kb is not None:
            kb_names[kb.id] = kb.name
    return _to_item(doc, kb_names)


async def seed_faqs(
    tenant_id: int, user: Any, knowledge_id: int
) -> Dict[str, int]:
    """POST /operations/corpus/seed-faqs：出厂 FAQ 幂等加载。

    库行 ``select_for_update`` 串行化同库并发种子；锁内复核归属+启用。
    同题（精确匹配非软删 faq_question，含人工 FAQ）跳过不覆盖；
    不同题经同一 create_faq 生命周期落库 pending。
    """
    created = 0
    skipped = 0
    async with in_transaction():
        kb = await (
            KuaiaiKnowledgeBase.filter(
                tenant_id=tenant_id,
                id=int(knowledge_id),
                deleted_at__isnull=True,
            )
            .select_for_update()
            .first()
        )
        if kb is None:
            raise NotFoundError("知识库", str(knowledge_id))
        if kb.status != STATUS_ENABLED:
            raise BusinessLogicError("知识库已停用")
        for question, answer in _SEED_FAQS:
            exists = await KuaiaiKnowledgeDocument.filter(
                tenant_id=tenant_id,
                knowledge_id=int(knowledge_id),
                source_type="faq",
                faq_question=question,
                deleted_at__isnull=True,
            ).exists()
            if exists:
                skipped += 1
                continue
            await KnowledgeService.create_faq(
                tenant_id,
                user,
                int(knowledge_id),
                question=question,
                answer=answer,
                is_active=True,
            )
            created += 1
    return {"created": created, "skipped": skipped}


def _batch_error(exc: Exception) -> str:
    """批量单项错误脱敏：不存在统一文案（无跨租户存在性泄露）。"""
    if isinstance(exc, NotFoundError):
        return "文档不存在或已删除"
    if isinstance(exc, (BusinessLogicError, ValidationError)):
        return str(getattr(exc, "message", "") or exc)[:_ITEM_ERROR_MAX]
    return "操作失败"


async def batch_index(
    tenant_id: int, user: Any, ids: List[int]
) -> Dict[str, Any]:
    """POST /operations/corpus/batch-index：逐项调用同一
    ``KnowledgeService.request_parse``（不绕过解析状态机、不要求知识库
    管理权限）；逐项租户复核，单项失败不影响其它项。
    """
    items: List[Dict[str, Any]] = []
    user_id = int(getattr(user, "id", None) or 0)
    for doc_id in dict.fromkeys(int(i) for i in ids):
        try:
            await KnowledgeService.request_parse(
                tenant_id, user_id, doc_id
            )
            items.append({"id": doc_id, "success": True, "error": None})
        except Exception as exc:
            if not isinstance(exc, (NotFoundError, BusinessLogicError,
                                    ValidationError)):
                logger.warning(
                    "corpus 批量索引单项失败 document_id={} error_type={}",
                    doc_id,
                    type(exc).__name__,
                )
            items.append(
                {"id": doc_id, "success": False,
                 "error": _batch_error(exc)}
            )
    return {"items": items}


async def batch_delete(
    tenant_id: int, ids: List[int]
) -> Dict[str, Any]:
    """POST /operations/corpus/batch-delete：逐项事务软删（chunks 同事务），
    单项失败不回滚已成功项；跨租户/已删 ID 逐项按不存在处理。
    """
    items: List[Dict[str, Any]] = []
    for doc_id in dict.fromkeys(int(i) for i in ids):
        try:
            await KnowledgeService.delete_document(tenant_id, doc_id)
            items.append({"id": doc_id, "success": True, "error": None})
        except Exception as exc:
            if not isinstance(exc, (NotFoundError, BusinessLogicError,
                                    ValidationError)):
                logger.warning(
                    "corpus 批量删除单项失败 document_id={} error_type={}",
                    doc_id,
                    type(exc).__name__,
                )
            items.append(
                {"id": doc_id, "success": False,
                 "error": _batch_error(exc)}
            )
    return {"items": items}


def _export_record(doc: Any) -> Optional[Dict[str, Any]]:
    """JSONL 白名单序列化器：只输出训练文本字段。

    faq → {type,title,question,answer}；text/file → {type,title,content}
    （file 行无文本正文时跳过——文件二进制不进入训练文本）。
    绝不输出 tenant_id、uuid/file_uuid、error_message、内部字段。
    """
    dtype = _doc_type(doc)
    title = (getattr(doc, "title", "") or "").strip()
    if dtype == "faq":
        question = (getattr(doc, "faq_question", "") or "").strip()
        answer = (getattr(doc, "faq_answer", "") or "").strip()
        if not question and not answer:
            return None
        return {
            "type": "faq",
            "title": title,
            "question": question,
            "answer": answer,
        }
    content = (getattr(doc, "raw_content", "") or "").strip()
    if not content:
        return None
    return {"type": dtype, "title": title, "content": content}


async def iter_export_jsonl(
    tenant_id: int,
    *,
    keyword: Optional[str] = None,
    knowledge_id: Optional[int] = None,
    doc_type: Optional[str] = None,
    doc_status: Optional[str] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
) -> AsyncIterator[str]:
    """GET /operations/corpus/export.jsonl 行迭代器。

    按当前筛选分批查询（``_EXPORT_BATCH_SIZE``/批，``_EXPORT_MAX_ROWS``
    硬上限）；一行一个合法 UTF-8 JSON（ensure_ascii=False）。
    """
    offset = 0
    emitted = 0
    while emitted < _EXPORT_MAX_ROWS:
        qs = _filtered_queryset(
            tenant_id,
            keyword=keyword,
            knowledge_id=knowledge_id,
            doc_type=doc_type,
            doc_status=doc_status,
            created_from=created_from,
            created_to=created_to,
        )
        rows = await qs.order_by("id").offset(offset).limit(
            min(_EXPORT_BATCH_SIZE, _EXPORT_MAX_ROWS - emitted)
        )
        if not rows:
            break
        for doc in rows:
            if emitted >= _EXPORT_MAX_ROWS:
                return
            record = _export_record(doc)
            if record is not None:
                yield json.dumps(record, ensure_ascii=False) + "\n"
            emitted += 1
        offset += len(rows)
        if len(rows) < _EXPORT_BATCH_SIZE:
            break
