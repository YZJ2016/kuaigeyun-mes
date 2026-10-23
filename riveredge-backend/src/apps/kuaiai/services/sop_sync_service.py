"""SOP → 知识库同步服务（spec 200 / SC-D11）。

- 配置读视图：站点设置 ``integrations.kuaiai.sop_sync = {enabled, knowledge_id}``
  （S1-a）；未启用或未配置目标库时同步任务跳过并记录，不报错影响文控；
- 投递入口 ``enqueue_sop_sync``：SOP 文控 publish/obsolete 成功后由
  ``SopControlService`` 探测调用（KU-AI 未组装则 import 失败不投递）；
- ``sync_sop_document``：Taskiq 任务内幂等执行——以 SOP **当前**状态为准
  （任务乱序安全）：
  * 生效中且有电子正文 → 按 ``(source_ref_type="sop", source_ref_id=sop.id)``
    建或更新同一条文档（source_type=md，正文=标题/版本/工序信息+content），
    置 ``pending`` 后直接调用 ``KnowledgeService.index_document``（任务内
    同步解析，不再经 rag_reindex 二次排队；失败留 ``status=failed`` +
    ``error_message``，可在 /knowledge 或 /corpus 重试）；
  * 非生效（作废/草稿/审核中）、纸质载体或正文为空 → 已入库文档软删下架
    （chunks 同事务软删，不再参与 search_knowledge 检索）；未入库则记录跳过；
- 审计字段写系统身份（created_by=0, "系统"，spec 181 约定），日志不记正文。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from loguru import logger

from apps.kuaiai.constants import STATUS_ENABLED
from apps.kuaiai.models.knowledge import KuaiaiKnowledgeDocument

SOURCE_REF_TYPE_SOP = "sop"
_TITLE_MAX = 300
_RAW_CONTENT_MAX = 200000
_CARRIER_LABELS = {
    "electronic": "电子",
    "paper": "纸质",
    "hybrid": "混合",
}
_SYSTEM_AUDIT = {
    "created_by": 0,
    "created_by_name": "系统",
    "updated_by": 0,
    "updated_by_name": "系统",
}


async def enqueue_sop_sync(tenant_id: int, sop_id: int) -> None:
    """投递 Taskiq 同步任务（SOP 文控侧探测调用）。

    投递失败只告警、不向外抛——同步失败不回滚 SOP 发布结果（spec 200 AC3/AC4）。
    """
    try:
        from core.tasks.ai_tasks import run_sop_knowledge_sync
    except ImportError:
        return
    try:
        await run_sop_knowledge_sync.kiq(
            tenant_id=int(tenant_id), sop_id=int(sop_id)
        )
    except Exception as exc:
        logger.warning(
            "SOP 知识同步任务投递失败 sop_id={} error_type={}",
            sop_id,
            type(exc).__name__,
        )


async def get_sop_sync_config(tenant_id: int) -> Optional[Dict[str, Any]]:
    """读 ``integrations.kuaiai.sop_sync``；未启用/未配置知识库 → None。"""
    from core.services.system.site_setting_service import SiteSettingService
    from core.utils.integration_settings import (
        get_kuaiai_integration,
        read_sop_sync,
    )

    site = await SiteSettingService.get_settings(tenant_id)
    kuaiai = get_kuaiai_integration(site.settings or {})
    cfg = read_sop_sync(kuaiai)
    if not cfg["enabled"] or not cfg.get("knowledge_id"):
        return None
    return cfg


async def _find_sop_document(
    tenant_id: int, sop_id: int
) -> Optional[KuaiaiKnowledgeDocument]:
    return await KuaiaiKnowledgeDocument.filter(
        tenant_id=int(tenant_id),
        source_ref_type=SOURCE_REF_TYPE_SOP,
        source_ref_id=int(sop_id),
        deleted_at__isnull=True,
    ).first()


async def _takedown(tenant_id: int, sop_id: int) -> bool:
    """已入库文档软删下架（chunks 同事务软删）；无文档 → False。"""
    doc = await _find_sop_document(tenant_id, sop_id)
    if doc is None:
        return False
    from apps.kuaiai.services.knowledge_service import KnowledgeService

    await KnowledgeService.delete_document(tenant_id, doc.id)
    return True


async def _operation_label(tenant_id: int, sop) -> Optional[str]:
    """关联工序展示名（code name）；无关联或行缺失 → None。"""
    operation_id = getattr(sop, "operation_id", None)
    if not operation_id:
        return None
    from apps.master_data.models.process import Operation

    op = await Operation.filter(
        tenant_id=int(tenant_id),
        id=int(operation_id),
        deleted_at__isnull=True,
    ).first()
    if op is None:
        return None
    label = " ".join(
        p for p in (str(op.code or ""), str(op.name or "")) if p
    ).strip()
    return label or None


async def _build_document_payload(
    tenant_id: int, sop
) -> tuple[str, str]:
    """(title, raw_content)：标题=名称（编码）；正文=元信息头 + content。"""
    revision = (
        getattr(sop, "current_revision", None)
        or getattr(sop, "version", None)
        or "1.0"
    )
    carrier = getattr(sop, "carrier", None) or "electronic"
    content = str(getattr(sop, "content", None) or "").strip()
    title = f"{sop.name}（{sop.code}）"[:_TITLE_MAX]

    meta = [
        f"- SOP 编码：{sop.code}",
        f"- 版本：{revision}",
        f"- 载体：{_CARRIER_LABELS.get(carrier, carrier)}",
    ]
    op_label = await _operation_label(tenant_id, sop)
    if op_label:
        meta.append(f"- 关联工序：{op_label}")
    raw = f"# {sop.name}\n\n" + "\n".join(meta) + f"\n\n{content}"
    if len(raw) > _RAW_CONTENT_MAX:
        logger.warning(
            "SOP 知识同步正文超长截断 sop_id={} length={}",
            getattr(sop, "id", None),
            len(raw),
        )
        raw = raw[:_RAW_CONTENT_MAX]
    return title, raw


async def _upsert_and_parse(
    tenant_id: int, sop, knowledge_id: int
) -> Dict[str, Any]:
    """建或更新该 SOP 的唯一同步文档，并直接执行解析管线。"""
    from apps.kuaiai.services.knowledge_service import KnowledgeService
    from tortoise.exceptions import IntegrityError

    title, raw = await _build_document_payload(tenant_id, sop)
    doc = await _find_sop_document(tenant_id, sop.id)
    if doc is None:
        try:
            doc = await KuaiaiKnowledgeDocument.create(
                tenant_id=int(tenant_id),
                knowledge_id=int(knowledge_id),
                title=title,
                source_type="md",
                raw_content=raw,
                status="pending",
                source_ref_type=SOURCE_REF_TYPE_SOP,
                source_ref_id=int(sop.id),
                is_active=True,
                **_SYSTEM_AUDIT,
            )
        except IntegrityError:
            # 并发双投：部分唯一索引兜底拒绝第二条，回落更新既有文档
            doc = await _find_sop_document(tenant_id, sop.id)
            if doc is None:
                raise
    else:
        doc.knowledge_id = int(knowledge_id)
        doc.title = title
        doc.raw_content = raw
        doc.status = "pending"
        doc.error_message = None
        doc.is_active = True
        doc.updated_by = 0
        doc.updated_by_name = "系统"
        await doc.save(
            update_fields=[
                "knowledge_id",
                "title",
                "raw_content",
                "status",
                "error_message",
                "is_active",
                "updated_by",
                "updated_by_name",
                "updated_at",
            ]
        )
    await KnowledgeService.index_document(
        tenant_id=int(tenant_id), document_id=int(doc.id)
    )
    return {
        "document_id": int(doc.id),
        "knowledge_id": int(knowledge_id),
    }


async def sync_sop_document(tenant_id: int, sop_id: int) -> Dict[str, Any]:
    """任务入口：幂等同步该 SOP 的知识文档（以其当前状态为准）。"""
    from apps.master_data.models.process import SOP

    cfg = await get_sop_sync_config(tenant_id)
    if cfg is None:
        logger.info(
            "SOP 知识同步跳过（未启用或未配置知识库）sop_id={}", sop_id
        )
        return {"skipped": "not_configured"}

    sop = await SOP.filter(
        tenant_id=int(tenant_id),
        id=int(sop_id),
        deleted_at__isnull=True,
    ).first()
    if sop is None:
        logger.info("SOP 知识同步跳过（SOP 不存在或已删除）sop_id={}", sop_id)
        return {"skipped": "sop_missing"}

    control_status = getattr(sop, "control_status", None)
    carrier = getattr(sop, "carrier", None) or "electronic"
    content = str(getattr(sop, "content", None) or "").strip()
    if control_status != "effective" or carrier == "paper" or not content:
        reason = (
            "not_effective"
            if control_status != "effective"
            else "no_electronic_content"
        )
        removed = await _takedown(tenant_id, sop.id)
        logger.info(
            "SOP 知识同步下架/跳过 sop_id={} reason={} removed={}",
            sop.id,
            reason,
            removed,
        )
        return {"skipped": reason, "removed": removed}

    # 目标库归属/启用复核：停用或跨租户 → 失败关闭（任务报错但不动 SOP）
    from apps.kuaiai.models.knowledge import KuaiaiKnowledgeBase

    kb = await KuaiaiKnowledgeBase.filter(
        tenant_id=int(tenant_id),
        id=int(cfg["knowledge_id"]),
        status=STATUS_ENABLED,
        deleted_at__isnull=True,
    ).first()
    if kb is None:
        logger.warning(
            "SOP 知识同步跳过（目标知识库不存在或已停用）sop_id={} knowledge_id={}",
            sop.id,
            cfg["knowledge_id"],
        )
        return {"skipped": "knowledge_base_unavailable"}

    result = await _upsert_and_parse(tenant_id, sop, int(cfg["knowledge_id"]))
    logger.info(
        "SOP 知识同步完成 sop_id={} document_id={} knowledge_id={}",
        sop.id,
        result["document_id"],
        result["knowledge_id"],
    )
    return {"synced": True, **result}
