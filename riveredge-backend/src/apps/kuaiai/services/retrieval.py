"""KU-AI S3 检索唯一 facade（KR-D12 / 设计 §9）。

``retrieve(tenant_id, query, knowledge_ids, *, top_k=5)`` 七步流水线：

a. 空 ``knowledge_ids``/``query`` → ``[]``；``knowledge_ids`` 复核为本租户
   **启用**库行（越权/停用/已删 id 过滤掉而非报错——档案 JSONB 可能残留）；
b. **压缩**：chat 模型把口语 query 压成检索句，任何异常/超时回退原句；
c. **有限展开**（默认开）：库级 ``expand_enabled`` 非空时库级优先（多库
   取 id 最小库的非空值），否则租户参数 ``kuaiai_rag_expand_enabled``（默认 true）；
   条数 ``kuaiai_rag_expand_count``（默认 2，上限 4）；失败只留压缩句；
d. **分库检索**：库绑定 embed 行 → ``build_embeddings``；本租户无 embed
   行/向量维度异常 → 该库跳过（整体无命中返回 []，不炸）；原始 SQL
   ``ORDER BY embedding_vector <=> $n::vector``，全参数化；
e. **RRF**（k=60 标准常数）跨 query 变体融合去重；
f. **打分再排序**：chat 模型对头部候选打分重排；任何失败保留 RRF 顺序；
g. **±1 扩窗**：命中 chunk 拼同文档 ``chunk_index±1`` 邻居（禁整篇）。

全程失败关闭：检索整体异常 → 返回 ``[]``（调用方走纯对话），日志只记
``error_type``，不落 key/base_url/内部路径（KR-I5）。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage
from loguru import logger
from tortoise import Tortoise

from apps.kuaiai.constants import STATUS_ENABLED
from apps.kuaiai.models.catalog import KuaiaiLlmModel
from apps.kuaiai.models.knowledge import (
    KuaiaiKnowledgeBase,
    KuaiaiKnowledgeChunk,
)
from core.ai.runtime.model_factory import build_chat_model, build_embeddings

_EMBED_DIM = 768
_RRF_K = 60
_EXPAND_COUNT_DEFAULT = 2
_EXPAND_COUNT_MAX = 4
# 打分再排序只取 RRF 头部候选，控制 prompt 体积
_RERANK_CANDIDATES = 10

_COMPRESS_PROMPT = (
    "你是检索查询改写器。把下面的用户问题压缩成一句适合知识库检索的查询句，"
    "去掉口语与寒暄，保留关键实体与意图。只输出改写后的查询句，不要解释。\n\n"
    "用户问题：{query}"
)
_EXPAND_PROMPT = (
    "你是检索查询改写器。围绕下面的检索句，生成最多 {count} 条语义相近但措辞不同"
    "的检索变体，每行一条，不要编号、不要解释。\n\n检索句：{query}"
)
_RERANK_PROMPT = (
    "你是检索相关性打分器。对下面每个候选片段按与问题的相关性打 0-10 分。"
    "只输出与候选数量相同的、逗号分隔的分数，不要解释。\n\n"
    "问题：{query}\n\n候选片段：\n{candidates}"
)

# 向量列不经 ORM 字段读写（embedding_vector 是占位映射），检索走参数化原始 SQL
_CHUNK_SEARCH_SQL = """
SELECT c."id", c."document_id", c."chunk_index", c."content",
       d."title" AS "file_name",
       c."embedding_vector" <=> $3::vector AS "distance"
FROM "apps_kuaiai_knowledge_chunks" c
JOIN "apps_kuaiai_knowledge_documents" d
  ON d."id" = c."document_id"
 AND d."tenant_id" = c."tenant_id"
 AND d."deleted_at" IS NULL
 AND d."is_active" = TRUE
WHERE c."tenant_id" = $1
  AND d."knowledge_id" = $2
  AND c."deleted_at" IS NULL
  AND c."embedding_vector" IS NOT NULL
ORDER BY "distance" ASC
LIMIT $4
"""


def _vector_literal(vector: List[float]) -> str:
    """pgvector 文本字面量（经 ``$n::vector`` 参数化传入，不拼接进 SQL）。"""
    return "[" + ",".join(str(float(v)) for v in vector) + "]"


def _normalize_ids(knowledge_ids: Optional[List[Any]]) -> List[int]:
    out: List[int] = []
    for raw in knowledge_ids or []:
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in out:
            out.append(value)
    return out


async def resolve_embed_model_id(
    tenant_id: int, embedding_model_id: Optional[int]
) -> Optional[int]:
    """embed 目录行绑定：库列优先；空则本租户第一条启用 ``model_type=embed``
    行；仍无返回 ``None``（调用方决定失败关闭还是跳过）。"""
    if embedding_model_id is not None:
        return int(embedding_model_id)
    row = await (
        KuaiaiLlmModel.filter(
            tenant_id=tenant_id,
            model_type="embed",
            status=STATUS_ENABLED,
            deleted_at__isnull=True,
        )
        .order_by("id")
        .first()
    )
    return row.id if row is not None else None


async def _param_value(tenant_id: int, key: str) -> Optional[Any]:
    """租户可运营配置读取；参数服务异常按未配置处理（不炸检索）。"""
    try:
        from core.services.system.system_parameter_service import (
            SystemParameterService,
        )

        param = await SystemParameterService.get_parameter(tenant_id, key)
        if param is None:
            return None
        return param.get_value()
    except Exception as exc:
        logger.warning(
            "KU-AI 检索参数读取失败 key={} error_type={}",
            key,
            type(exc).__name__,
        )
        return None


async def _param_bool(tenant_id: int, key: str, default: bool) -> bool:
    value = await _param_value(tenant_id, key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes", "on")


async def _param_int(tenant_id: int, key: str, default: int) -> int:
    value = await _param_value(tenant_id, key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


async def _compress_query(tenant_id: int, query: str) -> str:
    """口语 query 压成检索句；任何异常/超时回退原句（不 fail）。"""
    try:
        chat = await build_chat_model(tenant_id, None)
        resp = await chat.ainvoke(
            [HumanMessage(content=_COMPRESS_PROMPT.format(query=query))]
        )
        compressed = str(getattr(resp, "content", "") or "").strip()
        return compressed or query
    except Exception as exc:
        logger.warning(
            "KU-AI 检索压缩失败，回退原句 error_type={}", type(exc).__name__
        )
        return query


async def _expand_enabled(tenant_id: int, kbs: List[KuaiaiKnowledgeBase]) -> bool:
    """库级 expand_enabled 非空时库级优先（多库取 **id 最小库** 的非空值——
    kbs 由调用方按 id 升序取回，保证确定性）；全空回落租户参数
    kuaiai_rag_expand_enabled（默认开）。"""
    for kb in kbs:
        if kb.expand_enabled is not None:
            return bool(kb.expand_enabled)
    return await _param_bool(tenant_id, "kuaiai_rag_expand_enabled", True)


async def _expand_queries(
    tenant_id: int, kbs: List[KuaiaiKnowledgeBase], query: str
) -> List[str]:
    """有限展开：chat 模型产 ≤count 条改写变体；失败只留压缩句。"""
    if not await _expand_enabled(tenant_id, kbs):
        return []
    count = await _param_int(
        tenant_id, "kuaiai_rag_expand_count", _EXPAND_COUNT_DEFAULT
    )
    count = max(1, min(count, _EXPAND_COUNT_MAX))
    try:
        chat = await build_chat_model(tenant_id, None)
        resp = await chat.ainvoke(
            [
                HumanMessage(
                    content=_EXPAND_PROMPT.format(query=query, count=count)
                )
            ]
        )
        variants: List[str] = []
        for line in str(getattr(resp, "content", "") or "").splitlines():
            # 只剥项目符号与空白（数字保留，可能是查询实体一部分）；
            # 行首 "N." / "N、" 编号前缀另用正则剥
            variant = line.strip().strip("-•*、 ").strip()
            variant = re.sub(r"^\d+\s*[.、]\s*", "", variant).strip()
            if variant and variant != query and variant not in variants:
                variants.append(variant)
            if len(variants) >= count:
                break
        return variants
    except Exception as exc:
        logger.warning(
            "KU-AI 检索展开失败，仅留压缩句 error_type={}", type(exc).__name__
        )
        return []


async def _resolve_kb_embeddings(
    tenant_id: int, kbs: List[KuaiaiKnowledgeBase]
) -> Dict[int, Any]:
    """每库解析 embedding 实例；无 embed 行/构建失败 → None（该库跳过）。

    本租户没有可用 embed 行时检索返回空集而非炸——索引期本来就要求 embed
    行才能产出向量，缺行语义上即「不可检索」，不是调用方错误。
    """
    out: Dict[int, Any] = {}
    for kb in kbs:
        model_id = await resolve_embed_model_id(
            tenant_id, kb.embedding_model_id
        )
        if model_id is None:
            out[kb.id] = None
            continue
        try:
            out[kb.id] = await build_embeddings(tenant_id, model_id)
        except Exception as exc:
            logger.warning(
                "KU-AI 检索 embed 构建失败 knowledge_id={} error_type={}",
                kb.id,
                type(exc).__name__,
            )
            out[kb.id] = None
    return out


async def _search_kb(
    conn: Any,
    tenant_id: int,
    knowledge_id: int,
    vector: List[float],
    limit: int,
) -> List[Dict[str, Any]]:
    rows = await conn.execute_query_dict(
        _CHUNK_SEARCH_SQL,
        [tenant_id, knowledge_id, _vector_literal(vector), limit],
    )
    return list(rows or [])


def _rrf_fuse(rank_lists: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """RRF（k=60）跨 query 变体融合；同 chunk 去重取首次出现的行数据。"""
    scores: Dict[int, float] = {}
    best: Dict[int, Dict[str, Any]] = {}
    for ranked in rank_lists:
        for rank, row in enumerate(ranked):
            chunk_id = int(row["id"])
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (
                _RRF_K + rank + 1
            )
            if chunk_id not in best:
                best[chunk_id] = row
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [best[cid] for cid, _ in ordered]


async def _rerank(
    tenant_id: int, query: str, candidates: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """chat 模型对候选打分重排；任何失败/超时/形态不符保留 RRF 顺序。"""
    if len(candidates) <= 1:
        return candidates
    try:
        chat = await build_chat_model(tenant_id, None)
        numbered = "\n".join(
            f"[{i}] {str(c.get('content') or '')[:300]}"
            for i, c in enumerate(candidates)
        )
        resp = await chat.ainvoke(
            [
                HumanMessage(
                    content=_RERANK_PROMPT.format(
                        query=query, candidates=numbered
                    )
                )
            ]
        )
        parts = re.findall(
            r"-?\d+(?:\.\d+)?", str(getattr(resp, "content", "") or "")
        )
        if len(parts) != len(candidates):
            raise ValueError("打分数量与候选数不符")
        scores = [float(p) for p in parts]
        return [
            c
            for _, c in sorted(
                zip(scores, candidates), key=lambda kv: kv[0], reverse=True
            )
        ]
    except Exception as exc:
        logger.warning(
            "KU-AI 检索打分失败，保留 RRF 顺序 error_type={}",
            type(exc).__name__,
        )
        return candidates


async def _expand_window(
    tenant_id: int, rows: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """±1 扩窗：命中 chunk 拼同文档 chunk_index±1 邻居（禁整篇、禁越界）。

    邻居缺失（文档头尾/被删）自然跳过；窗口查询本身失败时退化回命中块原文。
    """
    out: List[Dict[str, Any]] = []
    for row in rows:
        idx = int(row["chunk_index"])
        document_id = int(row["document_id"])
        content = str(row.get("content") or "")
        try:
            # m4：只取 content 列，不拉 embedding/embedding_vector 大字段
            neighbors = await (
                KuaiaiKnowledgeChunk.filter(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    chunk_index__in=[idx - 1, idx, idx + 1],
                    deleted_at__isnull=True,
                )
                .order_by("chunk_index")
                .values("content")
            )
            joined = "\n".join(
                str(c.get("content") or "")
                for c in neighbors
                if c.get("content")
            )
            if joined.strip():
                content = joined
        except Exception as exc:
            logger.warning(
                "KU-AI 扩窗查询失败 document_id={} error_type={}",
                document_id,
                type(exc).__name__,
            )
        out.append(
            {
                "content": content,
                "file_name": row.get("file_name"),
                "document_id": document_id,
                "chunk_index": idx,
            }
        )
    return out


async def _retrieve(
    tenant_id: int,
    query: str,
    knowledge_ids: Optional[List[Any]],
    *,
    top_k: int,
) -> List[Dict[str, Any]]:
    query = (query or "").strip()
    ids = _normalize_ids(knowledge_ids)
    if not tenant_id or not query or not ids or top_k <= 0:
        return []
    kbs = await (
        KuaiaiKnowledgeBase.filter(
            tenant_id=tenant_id,
            id__in=ids,
            status=STATUS_ENABLED,
            deleted_at__isnull=True,
        )
        .order_by("id")
        .all()
    )
    if not kbs:
        return []

    compressed = await _compress_query(tenant_id, query)
    variants = [compressed] + await _expand_queries(tenant_id, kbs, compressed)
    kb_embeddings = await _resolve_kb_embeddings(tenant_id, kbs)
    if all(v is None for v in kb_embeddings.values()):
        return []

    conn = Tortoise.get_connection("default")
    limit = max(1, top_k)
    rank_lists: List[List[Dict[str, Any]]] = []
    for variant in variants:
        merged: List[Dict[str, Any]] = []
        for kb in kbs:
            embeddings = kb_embeddings.get(kb.id)
            if embeddings is None:
                continue
            try:
                vector = await embeddings.aembed_query(variant)
            except Exception as exc:
                logger.warning(
                    "KU-AI 检索向量生成失败 knowledge_id={} error_type={}",
                    kb.id,
                    type(exc).__name__,
                )
                continue
            if len(vector) != _EMBED_DIM:
                logger.warning(
                    "KU-AI 检索向量维度异常 knowledge_id={} dim={}",
                    kb.id,
                    len(vector),
                )
                continue
            merged.extend(
                await _search_kb(conn, tenant_id, kb.id, vector, limit)
            )
        merged.sort(key=lambda r: float(r.get("distance") or 0.0))
        rank_lists.append(merged)

    fused = _rrf_fuse(rank_lists)
    if not fused:
        return []
    head = await _rerank(tenant_id, compressed, fused[:_RERANK_CANDIDATES])
    ranked = head + fused[_RERANK_CANDIDATES:]
    return await _expand_window(tenant_id, ranked[:top_k])


async def retrieve(
    tenant_id: int,
    query: str,
    knowledge_ids: Optional[List[Any]],
    *,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """检索唯一入口；整体失败关闭返回 ``[]``（调用方走纯对话）。"""
    try:
        return await _retrieve(
            tenant_id, query, knowledge_ids, top_k=top_k
        )
    except Exception as exc:
        logger.warning(
            "KU-AI RAG 检索整体失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        return []
