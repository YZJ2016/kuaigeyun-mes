"""KU-AI spec 219 单测：SOP 附件同步进知识库（全部 mock，不触真库）。

覆盖要点（X7=a：附件文本合并进同一 source_ref 文档，按「【附件：文件名】」
分段标注）：
- 含附件 SOP：逐附件 FileService 租户路径拉取 → extract_text 解析 →
  分段拼接进同一文档 raw_content；
- 不支持类型/无文本层/超限/文件缺失/缺 file_uuid → 跳过并记日志，
  同步不失败、正文不回滚；
- 附件增删 → 同一文档按当前 attachments 全量重建（幂等）；
- 作废 → 整篇下架（附件段随文档一起软删）；
- 正文-only SOP 与 spec 200 行为不回归；纸质/无正文门禁保留
  （attachments 单独存在不产生文档）。
"""

from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.models.knowledge import KuaiaiKnowledgeBase, KuaiaiKnowledgeDocument
from apps.kuaiai.services import sop_sync_service as sss
from apps.master_data.models.process import SOP, Operation
from infra.exceptions.exceptions import NotFoundError, ValidationError

TENANT = 7
SOP_ID = 88
KB_ID = 42


def _qs(rows=(), first=None):
    q = MagicMock()
    for m in ("filter", "order_by", "offset", "limit", "select_for_update"):
        setattr(q, m, MagicMock(return_value=q))
    q.all = AsyncMock(return_value=list(rows))
    q.first = AsyncMock(
        return_value=first if first is not None else (rows[0] if rows else None)
    )
    q.count = AsyncMock(return_value=len(rows))
    q.exists = AsyncMock(return_value=bool(rows))
    return q


def _sop(**kw):
    base = dict(
        id=SOP_ID,
        tenant_id=TENANT,
        code="SOP-WELD-01",
        name="焊接作业指导",
        version="1.0",
        current_revision="1.0",
        carrier="electronic",
        control_status="effective",
        content="第一步：准备焊枪；第二步：按轨迹焊接。",
        operation_id=None,
        attachments=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _kb(enabled=True):
    return SimpleNamespace(
        id=KB_ID,
        tenant_id=TENANT,
        name="工艺知识库",
        status="启用" if enabled else "停用",
    )


def _file(uuid, name, size=1024, ext=None):
    return SimpleNamespace(
        uuid=uuid,
        original_name=name,
        file_size=size,
        file_extension=ext or name.rsplit(".", 1)[-1].lower(),
    )


def _att(uuid, name=None):
    """前端 normalizeDocumentAttachments 落库形态。"""
    return {
        "uid": uuid,
        "name": name or f"{uuid}.pdf",
        "status": "done",
        "url": f"/api/files/{uuid}/download",
    }


class _AttachmentEnv:
    """sync_sop_document 的公共 mock 面（spec 200 基线 + 文件/解析边界）。"""

    def __init__(self, sop, doc=None, files=None, texts=None, kb=None):
        self.sop = sop
        self.doc = doc
        self.files = files or {}
        self.texts = texts or {}
        self.kb = _kb() if kb is None else kb
        self.create_mock = AsyncMock(
            return_value=SimpleNamespace(id=600, tenant_id=TENANT)
        )
        self.index_mock = AsyncMock()
        self.delete_mock = AsyncMock()
        self.get_by_uuid = AsyncMock(side_effect=self._get_file)
        self.get_content = AsyncMock(side_effect=self._get_content)
        self.extract = AsyncMock(side_effect=self._extract)
        self.by_uuid_calls: list = []
        self.content_calls: list = []

    async def _get_file(self, tenant_id, uuid):
        assert tenant_id == TENANT
        self.by_uuid_calls.append(uuid)
        f = self.files.get(uuid)
        if isinstance(f, Exception):
            raise f
        if f is None:
            raise NotFoundError("文件")
        return f

    async def _get_content(self, tenant_id, uuid):
        assert tenant_id == TENANT
        self.content_calls.append(uuid)
        return b"%PDF-bytes"

    async def _extract(self, ext, data):
        out = self.texts.get(ext)
        if isinstance(out, Exception):
            raise out
        if out is None:
            raise ValidationError("解析结果为空文本")
        return out

    async def run(self):
        with ExitStack() as stack:
            for p in self.patches():
                stack.enter_context(p)
            return await sss.sync_sop_document(TENANT, SOP_ID)

    def patches(self):
        return (
            patch.object(
                sss,
                "get_sop_sync_config",
                AsyncMock(return_value={"enabled": True, "knowledge_id": KB_ID}),
            ),
            patch.object(SOP, "filter", MagicMock(return_value=_qs([self.sop]))),
            patch.object(
                KuaiaiKnowledgeBase,
                "filter",
                MagicMock(return_value=_qs([self.kb])),
            ),
            patch.object(
                KuaiaiKnowledgeDocument,
                "filter",
                MagicMock(
                    return_value=_qs([self.doc] if self.doc else [])
                ),
            ),
            patch.object(KuaiaiKnowledgeDocument, "create", self.create_mock),
            patch.object(Operation, "filter", MagicMock(return_value=_qs([]))),
            patch(
                "apps.kuaiai.services.knowledge_service"
                ".KnowledgeService.index_document",
                self.index_mock,
            ),
            patch(
                "apps.kuaiai.services.knowledge_service"
                ".KnowledgeService.delete_document",
                self.delete_mock,
            ),
            patch(
                "core.services.file.file_service"
                ".FileService.get_file_by_uuid",
                self.get_by_uuid,
            ),
            patch(
                "core.services.file.file_service"
                ".FileService.get_file_content",
                self.get_content,
            ),
            patch(
                "apps.kuaiai.services.document_parsers.extract_text",
                self.extract,
            ),
        )


class TestAttachmentMerge:
    """T2：含附件 SOP → 分段拼接进同一 source_ref 文档。"""

    @pytest.mark.asyncio
    async def test_multi_attachments_merged_with_markers(self):
        sop = _sop(
            attachments=[
                _att("u-pdf", "工艺卡.pdf"),
                _att("u-docx", "参数表.docx"),
            ]
        )
        env = _AttachmentEnv(
            sop,
            files={"u-pdf": _file("u-pdf", "工艺卡.pdf"),
                   "u-docx": _file("u-docx", "参数表.docx")},
            texts={"pdf": "焊接电流 180A", "docx": "电压 24V"},
        )
        out = await env.run()

        assert out["synced"] is True
        assert out["attachments"] == {"parsed": 2, "skipped": 0}
        raw = env.create_mock.await_args.kwargs["raw_content"]
        assert "第一步：准备焊枪" in raw
        assert "【附件：工艺卡.pdf】\n\n焊接电流 180A" in raw
        assert "【附件：参数表.docx】\n\n电压 24V" in raw
        # 分段顺序与 attachments 列表一致
        assert raw.index("工艺卡.pdf") < raw.index("参数表.docx")
        env.index_mock.assert_awaited_once_with(
            tenant_id=TENANT, document_id=600
        )

    @pytest.mark.asyncio
    async def test_dict_files_form_accepted(self):
        """{files:[{uuid,original_name}]} 文控形态同样解析。"""
        sop = _sop(
            attachments={
                "files": [
                    {"uuid": "u-f1", "original_name": "扫描工艺.pdf"},
                ]
            }
        )
        env = _AttachmentEnv(
            sop,
            files={"u-f1": _file("u-f1", "扫描工艺.pdf")},
            texts={"pdf": "扫描件文本层"},
        )
        out = await env.run()
        assert out["attachments"] == {"parsed": 1, "skipped": 0}
        raw = env.create_mock.await_args.kwargs["raw_content"]
        assert "【附件：扫描工艺.pdf】\n\n扫描件文本层" in raw

    @pytest.mark.asyncio
    async def test_bare_string_uuid_item(self):
        sop = _sop(attachments=["u-str"])
        env = _AttachmentEnv(
            sop,
            files={"u-str": _file("u-str", "说明.txt")},
            texts={"txt": "纯文本附件内容"},
        )
        out = await env.run()
        assert out["attachments"] == {"parsed": 1, "skipped": 0}
        raw = env.create_mock.await_args.kwargs["raw_content"]
        assert "【附件：说明.txt】\n\n纯文本附件内容" in raw

    @pytest.mark.asyncio
    async def test_duplicate_uuid_dedup(self):
        sop = _sop(
            attachments=[_att("u-dup", "a.pdf"), _att("u-dup", "a.pdf")]
        )
        env = _AttachmentEnv(
            sop,
            files={"u-dup": _file("u-dup", "a.pdf")},
            texts={"pdf": "文本"},
        )
        out = await env.run()
        assert out["attachments"] == {"parsed": 1, "skipped": 0}
        raw = env.create_mock.await_args.kwargs["raw_content"]
        assert raw.count("【附件：a.pdf】") == 1


class TestAttachmentSkip:
    """T2/T3：跳过不失败、不回滚正文。"""

    @pytest.mark.asyncio
    async def test_unsupported_type_skipped(self):
        sop = _sop(
            attachments=[
                _att("u-mp4", "操作视频.mp4"),
                _att("u-pdf", "工艺卡.pdf"),
            ]
        )
        env = _AttachmentEnv(
            sop,
            files={"u-mp4": _file("u-mp4", "操作视频.mp4"),
                   "u-pdf": _file("u-pdf", "工艺卡.pdf")},
            texts={"pdf": "可解析文本"},
        )
        out = await env.run()
        assert out["synced"] is True
        assert out["attachments"] == {"parsed": 1, "skipped": 1}
        raw = env.create_mock.await_args.kwargs["raw_content"]
        assert "操作视频" not in raw
        assert "【附件：工艺卡.pdf】" in raw
        # 不支持的类型不进入内容拉取
        assert "u-mp4" not in env.content_calls

    @pytest.mark.asyncio
    async def test_no_text_layer_skipped(self):
        """扫描件无文本层（extract_text 拒绝空文本）→ 跳过不失败。"""
        sop = _sop(
            attachments=[
                _att("u-scan", "扫描件.pdf"),
                _att("u-ok", "参数.xlsx"),
            ]
        )
        env = _AttachmentEnv(
            sop,
            files={"u-scan": _file("u-scan", "扫描件.pdf"),
                   "u-ok": _file("u-ok", "参数.xlsx")},
            texts={"xlsx": "扭矩 12N·m"},
        )
        out = await env.run()
        assert out["attachments"] == {"parsed": 1, "skipped": 1}
        raw = env.create_mock.await_args.kwargs["raw_content"]
        assert "扫描件" not in raw
        assert "【附件：参数.xlsx】" in raw

    @pytest.mark.asyncio
    async def test_oversize_attachment_skipped(self):
        from core.services.file.file_service import FileService

        sop = _sop(
            attachments=[
                _att("u-big", "大包.pdf"),
                _att("u-ok", "参数.pdf"),
            ]
        )
        env = _AttachmentEnv(
            sop,
            files={
                "u-big": _file(
                    "u-big", "大包.pdf", size=FileService.MAX_FILE_SIZE + 1
                ),
                "u-ok": _file("u-ok", "参数.pdf"),
            },
            texts={"pdf": "正常文本"},
        )
        out = await env.run()
        assert out["attachments"] == {"parsed": 1, "skipped": 1}
        assert "u-big" not in env.content_calls

    @pytest.mark.asyncio
    async def test_missing_file_and_missing_uuid_skipped(self):
        sop = _sop(
            attachments=[
                _att("u-gone", "已删.pdf"),
                {"name": "无标识.pdf", "status": "done"},  # 无 uid/uuid
                _att("u-ok", "ok.pdf"),
            ]
        )
        env = _AttachmentEnv(
            sop,
            files={"u-ok": _file("u-ok", "ok.pdf")},  # u-gone 不存在
            texts={"pdf": "存在文本"},
        )
        out = await env.run()
        assert out["attachments"] == {"parsed": 1, "skipped": 2}
        raw = env.create_mock.await_args.kwargs["raw_content"]
        assert "【附件：ok.pdf】" in raw

    @pytest.mark.asyncio
    async def test_fetch_error_reason_not_misreported_as_missing(self):
        """拉取异常（非 NotFoundError）记「读取失败（error_type）」；
        真不存在仍记「文件不存在或已删除」。"""
        from loguru import logger

        records: list = []
        sink = logger.add(
            lambda m: records.append(m.record["message"]), level="WARNING"
        )
        try:
            sop = _sop(
                attachments=[
                    _att("u-gone", "已删.pdf"),
                    _att("u-err", "故障.pdf"),
                    _att("u-ok", "ok.pdf"),
                ]
            )
            env = _AttachmentEnv(
                sop,
                files={
                    "u-err": RuntimeError("db down"),  # u-gone 不存在
                    "u-ok": _file("u-ok", "ok.pdf"),
                },
                texts={"pdf": "存在文本"},
            )
            out = await env.run()
        finally:
            logger.remove(sink)

        assert out["attachments"] == {"parsed": 1, "skipped": 2}
        assert any("文件不存在或已删除" in m for m in records)
        assert any("读取失败（RuntimeError）" in m for m in records)
        # 读取失败不得冒名「不存在」：两个 reason 分属不同附件各出现一次
        assert not any("读取失败" in m and "已删" in m for m in records)

    @pytest.mark.asyncio
    async def test_cjk_display_name_not_treated_as_extension(self):
        """审计 minor：CJK 展示名 isalnum() 为真，不得被第二循环误判为
        扩展名而劫持靠后的 item.ext / file_extension 候选。"""
        sop = _sop(
            attachments=[
                # 展示名无扩展名，真实类型只在 item.ext / file_extension
                {"uid": "u-cjk", "name": "点检表", "ext": "pdf"},
            ]
        )
        env = _AttachmentEnv(
            sop,
            files={"u-cjk": _file("u-cjk", "点检表", ext="pdf")},
            texts={"pdf": "点检项次文本"},
        )
        out = await env.run()
        assert out["attachments"] == {"parsed": 1, "skipped": 0}
        raw = env.create_mock.await_args.kwargs["raw_content"]
        assert "【附件：点检表】\n\n点检项次文本" in raw

    @pytest.mark.asyncio
    async def test_truncated_attachments_counted_in_skipped(self):
        """审计 minor：>10 截断丢弃的附件计入 skipped 统计。"""
        atts = [_att(f"u-{i}", f"a{i}.pdf") for i in range(12)]
        sop = _sop(attachments=atts)
        env = _AttachmentEnv(
            sop,
            files={f"u-{i}": _file(f"u-{i}", f"a{i}.pdf") for i in range(12)},
            texts={"pdf": "附件文本"},
        )
        out = await env.run()
        assert out["attachments"] == {"parsed": 10, "skipped": 2}
        # 只拉取前 10 个
        assert len(env.content_calls) == 10
        assert "u-10" not in env.content_calls


class TestIncrementalAndTakedown:
    """T3：附件增删幂等更新；作废整篇下架。"""

    def _existing_doc(self):
        doc = MagicMock()
        doc.id = 601
        doc.save = AsyncMock()
        return doc

    @pytest.mark.asyncio
    async def test_attachment_add_remove_updates_same_doc(self):
        doc = self._existing_doc()
        files = {
            "u-a": _file("u-a", "a.pdf"),
            "u-b": _file("u-b", "b.pdf"),
            "u-c": _file("u-c", "c.pdf"),
        }
        texts = {"pdf": "附件文本"}

        # 第一次：[a, b]
        sop1 = _sop(attachments=[_att("u-a", "a.pdf"), _att("u-b", "b.pdf")])
        env1 = _AttachmentEnv(sop1, doc=doc, files=files, texts=texts)
        out1 = await env1.run()
        env1.create_mock.assert_not_awaited()
        assert "【附件：a.pdf】" in doc.raw_content
        assert "【附件：b.pdf】" in doc.raw_content
        assert out1["document_id"] == 601

        # 第二次（增量）：删 a 增 c → [b, c]
        sop2 = _sop(attachments=[_att("u-b", "b.pdf"), _att("u-c", "c.pdf")])
        env2 = _AttachmentEnv(sop2, doc=doc, files=files, texts=texts)
        out2 = await env2.run()
        assert out2["document_id"] == 601
        assert "【附件：a.pdf】" not in doc.raw_content
        assert "【附件：b.pdf】" in doc.raw_content
        assert "【附件：c.pdf】" in doc.raw_content
        env2.index_mock.assert_awaited_once_with(
            tenant_id=TENANT, document_id=601
        )

        # 幂等：同状态再跑一遍 → 内容一致、仍走同一文档更新
        doc.raw_content = None  # 模拟已持久化后重跑
        env3 = _AttachmentEnv(sop2, doc=doc, files=files, texts=texts)
        out3 = await env3.run()
        assert out3["document_id"] == 601
        assert doc.raw_content.count("【附件：") == 2
        env3.create_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_obsolete_takedown_removes_attachment_content(self):
        doc = self._existing_doc()
        sop = _sop(
            control_status="obsolete",
            attachments=[_att("u-a", "a.pdf")],
        )
        env = _AttachmentEnv(sop, doc=doc)
        out = await env.run()
        env.delete_mock.assert_awaited_once_with(TENANT, 601)
        assert out == {"skipped": "not_effective", "removed": True}
        # 下架路径不触碰附件拉取/解析
        env.get_by_uuid.assert_not_awaited()
        env.extract.assert_not_awaited()


class TestSpec200NoRegression:
    """T4：正文-only 与既有门禁不回归。"""

    @pytest.mark.asyncio
    async def test_content_only_sop_no_attachment_io(self):
        sop = _sop(attachments=None)
        env = _AttachmentEnv(sop)
        out = await env.run()
        assert out["synced"] is True
        assert out["attachments"] == {"parsed": 0, "skipped": 0}
        raw = env.create_mock.await_args.kwargs["raw_content"]
        assert "【附件" not in raw
        assert "SOP-WELD-01" in raw and "焊接作业指导" in raw
        env.get_by_uuid.assert_not_awaited()
        env.get_content.assert_not_awaited()
        env.extract.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_attachments_list_same_as_none(self):
        sop = _sop(attachments=[])
        env = _AttachmentEnv(sop)
        out = await env.run()
        assert out["attachments"] == {"parsed": 0, "skipped": 0}
        env.get_by_uuid.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_paper_carrier_with_attachments_still_takedown(self):
        """纸质载体门禁保留：即使有附件也不入库。"""
        doc = MagicMock()
        doc.id = 602
        doc.save = AsyncMock()
        sop = _sop(carrier="paper", attachments=[_att("u-a", "扫描.pdf")])
        env = _AttachmentEnv(sop, doc=doc)
        out = await env.run()
        assert out == {"skipped": "no_electronic_content", "removed": True}
        env.delete_mock.assert_awaited_once_with(TENANT, 602)
        env.get_by_uuid.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_content_with_attachments_still_takedown(self):
        """spec 200 门禁保留：正文为空不入库——仅含附件不产生文档
        （attachment-only SOP 仍不覆盖，见 spec 219 §4 已知缺口）。"""
        doc = MagicMock()
        doc.id = 603
        doc.save = AsyncMock()
        sop = _sop(content="  ", attachments=[_att("u-a", "a.pdf")])
        env = _AttachmentEnv(sop, doc=doc)
        out = await env.run()
        assert out == {"skipped": "no_electronic_content", "removed": True}
        env.get_by_uuid.assert_not_awaited()
        env.create_mock.assert_not_awaited()
