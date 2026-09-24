"""KU-AI 知识库管理服务（KR-D12，S3）：knowledge_bases CRUD + options。

- 归属校验统一入口 get_base：tenant_id 强过滤，跨租户/软删/不存在一律 404（KR-I1）。
- embedding_model_id 非空时须指向本租户 model_type=embed 的启用目录行：
  跨租户/不存在 404，类型或状态不符 400（对齐 agent_service._require_chat_model 口径）。
- chunk_size/chunk_overlap 为库级可空参数（NULL 回落租户可运营配置）；
  非空时均须 >0 且 overlap < chunk_size（spec 136 §1 Scope）。
- delete_base 仅软删本行：档案 knowledge_ids 为 JSONB 引用、文档行挂 knowledge_id，
  均不做级联——检索侧（services/retrieval.py）与档案装配按 deleted_at/status 过滤，
  删库后自然不再命中；重建同名库受部分唯一索引保护。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from apps.kuaiai.constants import (
    CATALOG_STATUSES,
    MODEL_TYPE_EMBED,
    STATUS_ENABLED,
)
from apps.kuaiai.models.catalog import KuaiaiLlmModel
from apps.kuaiai.models.knowledge import KuaiaiKnowledgeBase
from apps.kuaiai.schemas.knowledge import KnowledgeBaseCreate, KnowledgeBaseUpdate
from core.utils.timezone_utils import now_utc
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError
from infra.models.user import User


def _audit_create(user: Optional[User]) -> Dict[str, Any]:
    if user is None or getattr(user, "id", None) is None:
        return {}
    name = getattr(user, "full_name", None) or getattr(user, "username", None)
    return {
        "created_by": user.id,
        "created_by_name": name,
        "updated_by": user.id,
        "updated_by_name": name,
    }


def _audit_update(user: Optional[User]) -> Dict[str, Any]:
    if user is None or getattr(user, "id", None) is None:
        return {}
    return {
        "updated_by": user.id,
        "updated_by_name": getattr(user, "full_name", None)
        or getattr(user, "username", None),
    }


def _require_status(value: Optional[str]) -> str:
    stripped = (value or "").strip()
    if stripped not in CATALOG_STATUSES:
        raise BusinessLogicError("status 仅允许 启用|停用")
    return stripped


def _validate_chunk_params(
    chunk_size: Optional[int], chunk_overlap: Optional[int]
) -> None:
    """库级切块参数：可空回落租户配置；非空时 >0 且 overlap < chunk_size。"""
    if chunk_size is not None and chunk_size <= 0:
        raise BusinessLogicError("chunk_size 须大于 0")
    if chunk_overlap is not None and chunk_overlap <= 0:
        raise BusinessLogicError("chunk_overlap 须大于 0")
    if (
        chunk_size is not None
        and chunk_overlap is not None
        and chunk_overlap >= chunk_size
    ):
        raise BusinessLogicError("chunk_overlap 须小于 chunk_size")


async def _require_embed_model(tenant_id: int, model_id: int) -> KuaiaiLlmModel:
    """embedding_model_id 归属复核：本租户行才接受（跨租户/不存在 404）。"""
    model = await KuaiaiLlmModel.get_or_none(
        tenant_id=tenant_id, id=model_id, deleted_at__isnull=True
    )
    if model is None:
        raise NotFoundError("LLM 模型", str(model_id))
    if model.model_type != MODEL_TYPE_EMBED or model.status != STATUS_ENABLED:
        raise BusinessLogicError(
            "embedding_model_id 须指向本租户 embed 类型的启用模型行"
        )
    return model


async def get_base(tenant_id: int, kb_id: int) -> KuaiaiKnowledgeBase:
    """本租户知识库查询：跨租户/软删/不存在一律 404（KR-I1）。"""
    base = await KuaiaiKnowledgeBase.get_or_none(
        tenant_id=tenant_id, id=kb_id, deleted_at__isnull=True
    )
    if base is None:
        raise NotFoundError("知识库", str(kb_id))
    return base


async def list_bases(
    tenant_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
) -> Dict[str, Any]:
    """管理 list：本租户知识库分页 {items,total}；keyword 命中 name/description。"""
    q = KuaiaiKnowledgeBase.filter(tenant_id=tenant_id, deleted_at__isnull=True)
    kw = (keyword or "").strip()
    if kw:
        q = q.filter(name__icontains=kw)
    total = await q.count()
    items = await q.order_by("id").offset((page - 1) * page_size).limit(page_size)
    return {"items": items, "total": total}


async def base_options(tenant_id: int) -> List[Dict[str, Any]]:
    """启用知识库下拉项（档案勾选 knowledge_ids / 对话页选库用）。"""
    rows = await KuaiaiKnowledgeBase.filter(
        tenant_id=tenant_id, status=STATUS_ENABLED, deleted_at__isnull=True
    ).order_by("id").all()
    return [{"id": r.id, "name": r.name, "description": r.description} for r in rows]


async def create_base(
    tenant_id: int, user: User, payload: KnowledgeBaseCreate
) -> KuaiaiKnowledgeBase:
    # 先校验纯字段规则（不触库），再做重名/归属查询（KR-I3：失败先于 DB 写入）
    status = (
        _require_status(payload.status)
        if payload.status is not None
        else STATUS_ENABLED
    )
    name = payload.name.strip()
    _validate_chunk_params(payload.chunk_size, payload.chunk_overlap)
    dup = await KuaiaiKnowledgeBase.get_or_none(
        tenant_id=tenant_id, name=name, deleted_at__isnull=True
    )
    if dup is not None:
        raise BusinessLogicError(f"知识库名称 {name} 已存在")
    if payload.embedding_model_id is not None:
        await _require_embed_model(tenant_id, payload.embedding_model_id)
    return await KuaiaiKnowledgeBase.create(
        tenant_id=tenant_id,
        name=name,
        description=payload.description,
        embedding_model_id=payload.embedding_model_id,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
        expand_enabled=payload.expand_enabled,
        status=status,
        **_audit_create(user),
    )


async def update_base(
    tenant_id: int, user: User, kb_id: int, payload: KnowledgeBaseUpdate
) -> KuaiaiKnowledgeBase:
    base = await get_base(tenant_id, kb_id)
    data = payload.model_dump(exclude_unset=True)

    # 非空列显式传 null 视为非法（避免写入 NULL）；可空列 null 表示清空回落
    if "name" in data:
        if data["name"] is None:
            raise BusinessLogicError("name 不允许为空")
        name = data["name"].strip()
        dup = await KuaiaiKnowledgeBase.get_or_none(
            tenant_id=tenant_id, name=name, deleted_at__isnull=True
        )
        if dup is not None and dup.id != base.id:
            raise BusinessLogicError(f"知识库名称 {name} 已存在")
        data["name"] = name
    if "status" in data:
        data["status"] = _require_status(data["status"])
    if "chunk_size" in data or "chunk_overlap" in data:
        # 单侧更新时与另一侧生效值合并校验（显式 null = 清空回落，不参与比较）
        _validate_chunk_params(
            data.get("chunk_size", base.chunk_size),
            data.get("chunk_overlap", base.chunk_overlap),
        )
    if "embedding_model_id" in data and data["embedding_model_id"] is not None:
        await _require_embed_model(tenant_id, data["embedding_model_id"])

    data.update(_audit_update(user))
    await base.update_from_dict(data).save()
    return base


async def delete_base(tenant_id: int, user: User, kb_id: int) -> None:
    """软删知识库。档案 knowledge_ids（JSONB）引用不做级联：检索侧按
    deleted_at/status 过滤已删库，允许直接删除（spec 136 不要求级联）。"""
    base = await get_base(tenant_id, kb_id)
    base.deleted_at = now_utc()
    base.update_from_dict(_audit_update(user))
    await base.save()
