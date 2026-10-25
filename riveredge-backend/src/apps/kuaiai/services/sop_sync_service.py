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
- spec 219（X7=a）：``attachments`` 中可解析附件逐一经 FileService 租户路径
  拉取 bytes → 走 ``document_parsers.extract_text`` 同一管线 → 文本按
  「【附件：文件名】」分段拼接进同一文档 raw_content；不支持类型/无文本层/
  超限/拉取失败的附件跳过并记同步日志，不影响正文；附件增删由「按当前
  attachments 全量重建同一文档」天然幂等覆盖；作废下架整篇（含附件段）。
- 审计字段写系统身份（created_by=0, "系统"，spec 181 约定），日志不记正文
  与附件明文。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from apps.kuaiai.constants import STATUS_ENABLED
from apps.kuaiai.models.knowledge import KuaiaiKnowledgeDocument

SOURCE_REF_TYPE_SOP = "sop"
_TITLE_MAX = 300
_RAW_CONTENT_MAX = 200000
# 附件上限沿用现有约束：SOP 附件上传字段 max=10
# （前端 DocumentAttachmentsField 默认值）；大小上限沿用文件上传/解析管线
# 的 FileService.MAX_FILE_SIZE，超限附件跳过并记录
_ATTACHMENT_MAX_COUNT = 10
_ATTACHMENT_NAME_MAX = 200
# 可进 extract_text 的附件扩展名（与 document_parsers 路由保持一致；
# doc/ppt 旧二进制与图片/视频等不在内 → 跳过记录，不做 OCR）
_ATTACHMENT_TEXT_TYPES = frozenset(
    {"pdf", "docx", "pptx", "xlsx", "xls", "md", "markdown", "txt", "text"}
)
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


def _iter_sop_attachments(sop) -> List[Any]:
    """归一化 ``sop.attachments``：list 项 / ``{files: [...]}`` 形态统一拍平，
    dict 项与裸 file_uuid 字符串均接受（与 master_data 侧
    ``_normalize_attachments`` 及前端 ``mapSopAttachmentsToUploadList``
    的双形态约定一致）。"""
    raw = getattr(sop, "attachments", None)
    if raw is None:
        return []
    items = raw
    if isinstance(raw, dict):
        files = raw.get("files")
        items = files if isinstance(files, list) else [raw]
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, (dict, str))]


def _attachment_ref(item: Any) -> Tuple[Optional[str], str]:
    """(file_uuid, name)：uid/uuid/file_uuid 取文件标识；name/original_name/
    file_name 取展示名；裸字符串项按 file_uuid 处理。"""
    if isinstance(item, str):
        uuid = item.strip()
        return (uuid or None), ""
    uuid = str(
        item.get("uid") or item.get("uuid") or item.get("file_uuid") or ""
    ).strip()
    name = str(
        item.get("name")
        or item.get("original_name")
        or item.get("file_name")
        or ""
    ).strip()
    return (uuid or None), name


def _attachment_ext(*candidates: str) -> str:
    """取扩展名：优先含 ``.`` 的文件名后缀；否则接受裸扩展名 token。"""
    for cand in candidates:
        cand = (cand or "").strip().lower()
        if "." in cand:
            return cand.rsplit(".", 1)[-1].strip()
    for cand in candidates:
        cand = (cand or "").strip().lower()
        # isalnum 对「点检表」等 CJK 展示名也返 True，须叠加 ASCII 约束，
        # 否则无扩展名的展示名会劫持后续 ext/file_extension 候选
        if cand and len(cand) <= 8 and cand.isascii() and cand.isalnum():
            return cand
    return ""


def _clean_attachment_name(name: str, fallback: str) -> str:
    name = re.sub(r"[\r\n]+", " ", name or "").strip()
    return (name or fallback)[:_ATTACHMENT_NAME_MAX]


async def _attachment_sections(
    tenant_id: int, sop
) -> Tuple[List[str], int]:
    """逐附件拉取→解析→渲染「【附件：name】」分段；返回 (分段列表, 跳过数)。

    失败关闭语义仅到附件级：类型不支持/无文本层/超限/文件缺失/解析异常
    一律跳过并记同步日志（不记附件明文），不抛出、不影响正文同步。
    """
    items = _iter_sop_attachments(sop)
    if not items:
        return [], 0
    sop_id = getattr(sop, "id", None)
    skipped = 0
    if len(items) > _ATTACHMENT_MAX_COUNT:
        logger.warning(
            "SOP 知识同步附件数量超限 sop_id={} count={} cap={}（仅处理前 {} 个）",
            sop_id,
            len(items),
            _ATTACHMENT_MAX_COUNT,
            _ATTACHMENT_MAX_COUNT,
        )
        # 截断丢弃项计入 skipped：返回统计口径=「未进入正文的附件数」
        skipped += len(items) - _ATTACHMENT_MAX_COUNT
        items = items[:_ATTACHMENT_MAX_COUNT]

    from apps.kuaiai.services.document_parsers import extract_text
    from core.services.file.file_service import FileService
    from infra.exceptions.exceptions import NotFoundError, ValidationError

    def _skip(name: str, reason: str) -> None:
        logger.warning(
            "SOP 附件未解析 sop_id={} attachment={} reason={}",
            sop_id,
            name,
            reason,
        )

    sections: List[str] = []
    seen: set = set()
    for item in items:
        file_uuid, name = _attachment_ref(item)
        label = _clean_attachment_name(name, file_uuid or "未命名附件")
        if not file_uuid:
            skipped += 1
            _skip(label, "缺少文件标识")
            continue
        if file_uuid in seen:
            continue
        seen.add(file_uuid)

        try:
            file = await FileService.get_file_by_uuid(tenant_id, file_uuid)
        except NotFoundError:
            skipped += 1
            _skip(label, "文件不存在或已删除")
            continue
        except Exception as exc:
            # 读取异常（DB/存储故障等）不冒名「不存在」，记类型不记明文
            skipped += 1
            _skip(label, f"读取失败（{type(exc).__name__}）")
            continue
        if not name:
            name = str(getattr(file, "original_name", "") or "").strip()
            label = _clean_attachment_name(name, file_uuid)
        ext = _attachment_ext(
            name,
            str(item.get("ext") or "") if isinstance(item, dict) else "",
            str(getattr(file, "file_extension", "") or ""),
            str(getattr(file, "original_name", "") or ""),
        )
        if ext not in _ATTACHMENT_TEXT_TYPES:
            skipped += 1
            _skip(label, f"类型不支持（{ext or '无扩展名'}）")
            continue
        size = int(getattr(file, "file_size", 0) or 0)
        if size > FileService.MAX_FILE_SIZE:
            skipped += 1
            _skip(label, "超过大小上限")
            continue
        try:
            data = await FileService.get_file_content(tenant_id, file_uuid)
            text = await extract_text(ext, data)
        except ValidationError as exc:
            skipped += 1
            _skip(label, str(getattr(exc, "message", "") or exc)[:100])
            continue
        except Exception as exc:
            skipped += 1
            _skip(label, f"解析失败（{type(exc).__name__}）")
            continue
        sections.append(f"【附件：{label}】\n\n{text.strip()}")
    return sections, skipped


async def _build_document_payload(
    tenant_id: int, sop
) -> Tuple[str, str, Dict[str, int]]:
    """(title, raw_content, attachment_stats)：标题=名称（编码）；
    正文=元信息头 + content + 各可解析附件「【附件：文件名】」分段。"""
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
    sections, skipped = await _attachment_sections(tenant_id, sop)
    if sections:
        raw += "\n\n" + "\n\n".join(sections)
    if len(raw) > _RAW_CONTENT_MAX:
        logger.warning(
            "SOP 知识同步正文超长截断 sop_id={} length={}",
            getattr(sop, "id", None),
            len(raw),
        )
        raw = raw[:_RAW_CONTENT_MAX]
    return title, raw, {"parsed": len(sections), "skipped": skipped}


async def _upsert_and_parse(
    tenant_id: int, sop, knowledge_id: int
) -> Dict[str, Any]:
    """建或更新该 SOP 的唯一同步文档，并直接执行解析管线。"""
    from apps.kuaiai.services.knowledge_service import KnowledgeService
    from tortoise.exceptions import IntegrityError

    title, raw, attach_stats = await _build_document_payload(tenant_id, sop)
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
        "attachments": attach_stats,
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
        "SOP 知识同步完成 sop_id={} document_id={} knowledge_id={} "
        "attachments_parsed={} attachments_skipped={}",
        sop.id,
        result["document_id"],
        result["knowledge_id"],
        result["attachments"]["parsed"],
        result["attachments"]["skipped"],
    )
    return {"synced": True, **result}
