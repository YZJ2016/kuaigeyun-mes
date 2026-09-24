"""KU-AI S3 单测：M1/m9 修复面（并发/重解析语义）。

全部 mock Tortoise / AiJobService / model_factory，不需要真实数据库与 LLM。

- M1：``index_document`` 入口 ``in_transaction()`` + ``select_for_update()``
  行锁——并发第二个 job 锁到 ``parsing`` 行仍按重解析语义跑通；
  ``request_parse`` 拒 fresh ``parsing``（``updated_at`` 30 分钟内）→
  ``BusinessLogicError``，陈旧 ``parsing`` 放行重投；
- m9：``request_parse`` 前置 ``_get_enabled_kb``（停用库 400，不投递）。
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import apps.kuaiai.services.knowledge_service as ks
from apps.kuaiai.models.knowledge import (
    KuaiaiKnowledgeBase,
    KuaiaiKnowledgeDocument,
)
from core.utils.timezone_utils import now_utc
from infra.exceptions.exceptions import BusinessLogicError

TENANT = 7
USER_ID = 5


def _kb(**kw):
    base = dict(
        id=9,
        tenant_id=TENANT,
        name="kb",
        embedding_model_id=33,
        chunk_size=800,
        chunk_overlap=100,
        expand_enabled=None,
        status="启用",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _doc(**kw):
    base = dict(
        id=41,
        tenant_id=TENANT,
        knowledge_id=9,
        title="文档",
        source_type="txt",
        raw_content="正文内容，用于切块与索引。",
        file_uuid=None,
        status="pending",
        chunk_count=0,
        error_message=None,
        is_active=True,
        deleted_at=None,
        updated_at=now_utc(),
    )
    base.update(kw)
    doc = SimpleNamespace(**base)
    doc.save = AsyncMock()
    return doc


class _FakeQS:
    """模拟 Tortoise QuerySet 链式调用与 await（含 select_for_update 行锁）。"""

    def __init__(self, items=None):
        self._items = list(items or [])
        self.update = AsyncMock(return_value=len(self._items))
        self.delete = AsyncMock(return_value=len(self._items))
        self.count = AsyncMock(return_value=len(self._items))
        self.select_for_update = MagicMock(return_value=self)
        self.values = AsyncMock(return_value=list(self._items))

    def filter(self, **kw):
        return self

    def order_by(self, *a):
        return self

    def offset(self, n):
        return self

    def limit(self, n):
        return self

    async def first(self):
        return self._items[0] if self._items else None

    async def all(self):
        return list(self._items)

    def __await__(self):
        async def _it():
            return list(self._items)

        return _it().__await__()


class _FakeTx:
    """``async with in_transaction() as conn`` 假连接。"""

    def __init__(self):
        self.conn = MagicMock()
        self.calls = []

        async def _record(sql, params=None):
            self.calls.append((sql, params))

        self.conn.execute_query = AsyncMock(side_effect=_record)

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *a):
        return False


def _patch_get_or_none(model, value):
    return patch.object(
        model, "get_or_none", new=AsyncMock(return_value=value)
    )


def _patch_tx():
    tx = _FakeTx()
    return tx, patch.object(
        ks, "in_transaction", MagicMock(return_value=tx)
    )


def _patch_embeddings():
    emb = MagicMock()
    emb.aembed_documents = AsyncMock(
        side_effect=lambda texts: [[0.1] * 768 for _ in texts]
    )
    return emb, patch(
        "core.ai.runtime.model_factory.build_embeddings",
        new=AsyncMock(return_value=emb),
    )


def _job_svc(job=None):
    svc = MagicMock()
    svc.create_job = AsyncMock(
        return_value=job or SimpleNamespace(job_id="j-1", status="queued")
    )
    return svc


class TestRequestParseGuards:
    """M1/m9：request_parse 前置校验。"""

    @pytest.mark.asyncio
    async def test_disabled_kb_rejected_before_dispatch(self):
        """m9：前置 _get_enabled_kb——停用库 400，不投递 job。"""
        job_svc = _job_svc()
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, _doc()),
            _patch_get_or_none(KuaiaiKnowledgeBase, _kb(status="停用")),
            patch("core.ai.jobs.AiJobService", job_svc),
        ):
            with pytest.raises(BusinessLogicError) as exc:
                await ks.KnowledgeService.request_parse(TENANT, USER_ID, 41)
        assert exc.value.status_code == 400
        job_svc.create_job.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fresh_parsing_rejected(self):
        """M1：status=parsing 且 updated_at 在 30 分钟内 → 400 拒绝重投。"""
        doc = _doc(status="parsing", updated_at=now_utc())
        job_svc = _job_svc()
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            _patch_get_or_none(KuaiaiKnowledgeBase, _kb()),
            patch("core.ai.jobs.AiJobService", job_svc),
        ):
            with pytest.raises(BusinessLogicError):
                await ks.KnowledgeService.request_parse(TENANT, USER_ID, 41)
        job_svc.create_job.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stale_parsing_redispatched(self):
        """M1：陈旧 parsing（updated_at 超过 30 分钟阈值）自愈——放行重投。"""
        doc = _doc(
            status="parsing",
            updated_at=now_utc() - timedelta(minutes=31),
        )
        job = SimpleNamespace(job_id="j-2", status="queued")
        job_svc = _job_svc(job)
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            _patch_get_or_none(KuaiaiKnowledgeBase, _kb()),
            patch("core.ai.jobs.AiJobService", job_svc),
        ):
            result = await ks.KnowledgeService.request_parse(
                TENANT, USER_ID, 41
            )
        assert result is job
        job_svc.create_job.assert_awaited_once()
        assert job_svc.create_job.await_args.kwargs["job_type"] == "rag_reindex"

    @pytest.mark.asyncio
    async def test_failed_document_redispatched(self):
        """failed 文档重投不受 parsing 闸门影响。"""
        doc = _doc(status="failed", updated_at=now_utc())
        job = SimpleNamespace(job_id="j-3", status="queued")
        job_svc = _job_svc(job)
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            _patch_get_or_none(KuaiaiKnowledgeBase, _kb()),
            patch("core.ai.jobs.AiJobService", job_svc),
        ):
            result = await ks.KnowledgeService.request_parse(
                TENANT, USER_ID, 41
            )
        assert result is job
        job_svc.create_job.assert_awaited_once()


class TestIndexDocumentConcurrency:
    """M1：入口行锁串行化并发 reindex。"""

    @pytest.mark.asyncio
    async def test_second_job_locks_row_and_reparses(self):
        """并发第二个 job：行锁后拿到 status=parsing 的 doc，仍按重解析
        语义跑通至 ready（拒绝语义只在 request_parse 投递侧）。"""
        doc = _doc(status="parsing", updated_at=now_utc())
        doc_qs = _FakeQS([doc])
        tx, tx_patch = _patch_tx()
        emb, emb_patch = _patch_embeddings()
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            patch.object(
                KuaiaiKnowledgeDocument,
                "filter",
                MagicMock(return_value=doc_qs),
            ),
            _patch_get_or_none(KuaiaiKnowledgeBase, _kb()),
            emb_patch,
            tx_patch,
        ):
            await ks.KnowledgeService.index_document(TENANT, 41)
        # 入口行锁确实走了 select_for_update
        assert doc_qs.select_for_update.called
        assert doc.status == "ready"
        assert doc.chunk_count >= 1
        assert any("INSERT INTO" in c[0] for c in tx.calls)
