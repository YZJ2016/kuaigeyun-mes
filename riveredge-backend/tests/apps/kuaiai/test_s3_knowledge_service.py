"""KU-AI S3 单测：KnowledgeService 文档面 + index_document 状态机。

全部 mock Tortoise / FileService / model_factory / AiJobService，不需要真实
数据库与 LLM 端点。覆盖：
- KB/文档归属 404；停用库拒建；file_uuid/raw_content 二选一必填
- 删文档同事务软删 chunks
- index_document：未绑 embed→第一条启用→仍无 failed；≠768 失败关闭；
  空文本 failed；失败清残留 chunks；事务内删旧+写向量+置 ready
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import apps.kuaiai.services.knowledge_service as ks
from apps.kuaiai.models.catalog import KuaiaiLlmModel
from apps.kuaiai.models.knowledge import (
    KuaiaiKnowledgeBase,
    KuaiaiKnowledgeChunk,
    KuaiaiKnowledgeDocument,
)
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

TENANT = 7
USER_ID = 5


def _user(uid=USER_ID):
    return SimpleNamespace(id=uid, full_name="测试用户", username="tester")


def _kb(**kw):
    base = dict(
        id=9,
        tenant_id=TENANT,
        name="kb",
        embedding_model_id=None,
        chunk_size=None,
        chunk_overlap=None,
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
        updated_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
    )
    base.update(kw)
    doc = SimpleNamespace(**base)
    doc.save = AsyncMock()
    return doc


def _payload(**kw):
    base = dict(
        title="文档",
        source_type="txt",
        file_uuid=None,
        raw_content="正文",
    )
    base.update(kw)
    return SimpleNamespace(**base)


class _FakeQS:
    """模拟 Tortoise QuerySet 链式调用与 await。

    - ``select_for_update()``（M1 行锁）返回自身并记录调用；
    - ``.values(...)``（m4 dict 行）await 后返回 ``_items``（测试侧放 dict）；
    - ``order_by`` 记录参数供位序断言（m5）。
    """

    def __init__(self, items=None):
        self._items = list(items or [])
        self.update = AsyncMock(return_value=len(self._items))
        self.delete = AsyncMock(return_value=len(self._items))
        self.count = AsyncMock(return_value=len(self._items))
        self.select_for_update = MagicMock(return_value=self)
        self.values = AsyncMock(return_value=list(self._items))
        self.order_by_calls = []

    def filter(self, **kw):
        return self

    def order_by(self, *a):
        self.order_by_calls.append(a)
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
        self.conn.execute_query = AsyncMock()
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


def _patch_filter(model, qs):
    return patch.object(model, "filter", new=MagicMock(return_value=qs))


def _patch_tx():
    tx = _FakeTx()
    return tx, patch.object(
        ks, "in_transaction", MagicMock(return_value=tx)
    )


def _patch_doc_lock(doc):
    """M1：index_document 入口 ``filter(...).select_for_update().first()``
    行锁链。返回 (qs, patch)；qs.select_for_update 可断言已上锁。"""
    qs = _FakeQS([doc] if doc is not None else [])
    return qs, _patch_filter(KuaiaiKnowledgeDocument, qs)


def _patch_params(size=None, overlap=None):
    """SystemParameterService.get_parameter → 指定值/None（未配置）。"""

    async def _get(tenant_id, key, use_cache=True):
        value = {
            "kuaiai_rag_chunk_size": size,
            "kuaiai_rag_chunk_overlap": overlap,
        }.get(key)
        if value is None:
            return None
        param = MagicMock()
        param.get_value = MagicMock(return_value=value)
        return param

    return patch(
        "core.services.system.system_parameter_service."
        "SystemParameterService.get_parameter",
        new=AsyncMock(side_effect=_get),
    )


def _patch_embed_row(row):
    """本租户第一条启用 embed 目录行（resolve_embed_model_id 回落查询）。"""
    qs = _FakeQS([row] if row is not None else [])
    return _patch_filter(KuaiaiLlmModel, qs)


def _patch_embeddings(vectors=None, side_effect=None):
    emb = MagicMock()
    if side_effect is not None:
        emb.aembed_documents = AsyncMock(side_effect=side_effect)
    else:
        emb.aembed_documents = AsyncMock(
            side_effect=lambda texts: [[0.1] * 768 for _ in texts]
        )
    return emb, patch(
        "core.ai.runtime.model_factory.build_embeddings",
        new=AsyncMock(return_value=emb),
    )


class TestOwnershipAndCrud:
    @pytest.mark.asyncio
    async def test_list_documents_cross_tenant_kb_404(self):
        with _patch_get_or_none(KuaiaiKnowledgeBase, None):
            with pytest.raises(NotFoundError):
                await ks.KnowledgeService.list_documents(TENANT, 9)

    @pytest.mark.asyncio
    async def test_list_documents_paginates(self):
        docs = [_doc(id=2), _doc(id=1)]
        qs = _FakeQS(docs)
        with (
            _patch_get_or_none(KuaiaiKnowledgeBase, _kb()),
            _patch_filter(KuaiaiKnowledgeDocument, qs),
        ):
            result = await ks.KnowledgeService.list_documents(
                TENANT, 9, page=1, page_size=20
            )
        assert result["total"] == 2
        assert [d.id for d in result["items"]] == [2, 1]

    @pytest.mark.asyncio
    async def test_create_document_disabled_kb_rejected(self):
        # m2：业务拒绝统一 BusinessLogicError（400），不再抛 ValidationError
        with _patch_get_or_none(
            KuaiaiKnowledgeBase, _kb(status="停用")
        ):
            with pytest.raises(BusinessLogicError) as exc:
                await ks.KnowledgeService.create_document(
                    TENANT, USER_ID, 9, _payload()
                )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_document_requires_one_source(self):
        with _patch_get_or_none(KuaiaiKnowledgeBase, _kb()):
            with pytest.raises(BusinessLogicError):
                await ks.KnowledgeService.create_document(
                    TENANT,
                    USER_ID,
                    9,
                    _payload(file_uuid=None, raw_content=None),
                )

    @pytest.mark.asyncio
    async def test_create_document_rejects_both_sources(self):
        with _patch_get_or_none(KuaiaiKnowledgeBase, _kb()):
            with pytest.raises(BusinessLogicError):
                await ks.KnowledgeService.create_document(
                    TENANT,
                    USER_ID,
                    9,
                    _payload(file_uuid="f-1", raw_content="x"),
                )

    @pytest.mark.asyncio
    async def test_create_document_file_uuid_verified(self):
        file_svc = MagicMock()
        file_svc.get_file_by_uuid = AsyncMock(
            return_value=SimpleNamespace(id=1)
        )
        created = _doc(file_uuid="f-1", raw_content=None)
        with (
            _patch_get_or_none(KuaiaiKnowledgeBase, _kb()),
            patch(
                "core.services.file.file_service.FileService",
                file_svc,
            ),
            patch.object(
                KuaiaiKnowledgeDocument,
                "create",
                new=AsyncMock(return_value=created),
            ) as mock_create,
        ):
            # 传 user 对象（对齐 create_base 的 current_user 约定）：
            # nit 落地后写 created_by_name/updated_by_name
            result = await ks.KnowledgeService.create_document(
                TENANT,
                _user(),
                9,
                _payload(file_uuid="f-1", raw_content=None),
            )
        assert result is created
        file_svc.get_file_by_uuid.assert_awaited_once_with(TENANT, "f-1")
        kw = mock_create.await_args.kwargs
        assert kw["status"] == "pending"
        assert kw["knowledge_id"] == 9
        assert kw["tenant_id"] == TENANT

    @pytest.mark.asyncio
    async def test_get_document_cross_tenant_404(self):
        with _patch_get_or_none(KuaiaiKnowledgeDocument, None):
            with pytest.raises(NotFoundError):
                await ks.KnowledgeService.get_document(TENANT, 41)

    @pytest.mark.asyncio
    async def test_delete_document_soft_deletes_chunks_in_tx(self):
        doc = _doc()
        chunk_qs = _FakeQS([SimpleNamespace(id=1)])
        tx, tx_patch = _patch_tx()
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            _patch_filter(KuaiaiKnowledgeChunk, chunk_qs),
            tx_patch,
        ):
            await ks.KnowledgeService.delete_document(TENANT, 41)
        chunk_qs.update.assert_awaited_once()
        assert chunk_qs.update.await_args.kwargs["deleted_at"] is not None
        assert doc.deleted_at is not None
        doc.save.assert_awaited()

    @pytest.mark.asyncio
    async def test_request_parse_dispatches_rag_reindex(self):
        job = SimpleNamespace(job_id="j-1", status="queued")
        job_svc = MagicMock()
        job_svc.create_job = AsyncMock(return_value=job)
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, _doc()),
            # m9：request_parse 前置 _get_enabled_kb（启用库放行）
            _patch_get_or_none(KuaiaiKnowledgeBase, _kb()),
            patch("core.ai.jobs.AiJobService", job_svc),
        ):
            result = await ks.KnowledgeService.request_parse(
                TENANT, USER_ID, 41
            )
        assert result is job
        kw = job_svc.create_job.await_args.kwargs
        assert kw["job_type"] == "rag_reindex"
        assert kw["tenant_id"] == TENANT
        assert kw["user_id"] == USER_ID
        assert kw["payload"] == {"document_id": 41}

    @pytest.mark.asyncio
    async def test_list_chunks_requires_owned_document(self):
        with _patch_get_or_none(KuaiaiKnowledgeDocument, None):
            with pytest.raises(NotFoundError):
                await ks.KnowledgeService.list_chunks(TENANT, 41)

    @pytest.mark.asyncio
    async def test_list_chunks_paginates(self):
        """m4：list_chunks 走 .values(...) 返回 dict 行。"""
        chunks = [{"id": 1, "chunk_index": 0, "content": "片段"}]
        qs = _FakeQS(chunks)
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, _doc()),
            _patch_filter(KuaiaiKnowledgeChunk, qs),
        ):
            result = await ks.KnowledgeService.list_chunks(
                TENANT, 41, page=1, page_size=20
            )
        assert result["total"] == 1
        assert result["items"][0]["chunk_index"] == 0


class TestIndexDocument:
    """index_document 状态机：失败关闭 + 事务内写 chunks。"""

    @pytest.mark.asyncio
    async def test_document_not_found(self):
        lock_qs, lock_patch = _patch_doc_lock(None)
        tx, tx_patch = _patch_tx()
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, None),
            lock_patch,
            tx_patch,
        ):
            with pytest.raises(NotFoundError):
                await ks.KnowledgeService.index_document(TENANT, 41)

    @pytest.mark.asyncio
    async def test_disabled_kb_rejected_before_status_write(self):
        # m2：停用库业务拒绝 BusinessLogicError（400）
        doc = _doc()
        lock_qs, lock_patch = _patch_doc_lock(doc)
        tx, tx_patch = _patch_tx()
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            lock_patch,
            _patch_get_or_none(KuaiaiKnowledgeBase, _kb(status="停用")),
            tx_patch,
        ):
            with pytest.raises(BusinessLogicError) as exc:
                await ks.KnowledgeService.index_document(TENANT, 41)
        assert exc.value.status_code == 400
        doc.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raw_content_index_success(self):
        """raw_content 直用 → 切块 → embed → 事务内删旧+写向量+ready。"""
        doc = _doc()
        kb = _kb(embedding_model_id=33, chunk_size=50, chunk_overlap=10)
        lock_qs, lock_patch = _patch_doc_lock(doc)
        tx, tx_patch = _patch_tx()
        emb, emb_patch = _patch_embeddings()
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            lock_patch,
            _patch_get_or_none(KuaiaiKnowledgeBase, kb),
            emb_patch,
            tx_patch,
        ):
            await ks.KnowledgeService.index_document(TENANT, 41)
        assert doc.status == "ready"
        assert doc.chunk_count >= 1
        sqls = [c[0] for c in tx.calls]
        assert any("DELETE FROM" in s for s in sqls)
        inserts = [c for c in tx.calls if "INSERT INTO" in c[0]]
        assert len(inserts) == doc.chunk_count
        assert "::vector" in inserts[0][0]
        assert any(
            "UPDATE" in sql and params and params[0] == "ready"
            for sql, params in tx.calls
        )
        # 库绑定 embed id 直通 build_embeddings
        assert emb.aembed_documents.await_count == 1

    @pytest.mark.asyncio
    async def test_unbound_kb_falls_back_to_first_enabled_embed(self):
        """kb.embedding_model_id 空 → 本租户第一条启用 embed 行。"""
        doc = _doc()
        embed_row = SimpleNamespace(id=77, model_type="embed", status="启用")
        lock_qs, lock_patch = _patch_doc_lock(doc)
        tx, tx_patch = _patch_tx()
        emb, emb_patch = _patch_embeddings()
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            lock_patch,
            _patch_get_or_none(KuaiaiKnowledgeBase, _kb()),
            _patch_embed_row(embed_row),
            _patch_params(),
            emb_patch,
            tx_patch,
        ):
            await ks.KnowledgeService.index_document(TENANT, 41)
        assert doc.status == "ready"

    @pytest.mark.asyncio
    async def test_no_embed_row_fails_not_ready(self):
        """无可用 embed 行 → status=failed，不得标成功。"""
        doc = _doc()
        lock_qs, lock_patch = _patch_doc_lock(doc)
        tx, tx_patch = _patch_tx()
        emb, emb_patch = _patch_embeddings()
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            lock_patch,
            _patch_get_or_none(KuaiaiKnowledgeBase, _kb()),
            _patch_embed_row(None),
            _patch_params(),
            emb_patch,
            tx_patch,
            _patch_filter(KuaiaiKnowledgeChunk, _FakeQS()),
        ):
            await ks.KnowledgeService.index_document(TENANT, 41)
        assert doc.status == "failed"
        assert "embed" in (doc.error_message or "")
        assert not any("INSERT INTO" in c[0] for c in tx.calls)
        emb.aembed_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dim_mismatch_fails_closed(self):
        """≠768 维 → failed，不截断、不写向量。"""
        doc = _doc()
        lock_qs, lock_patch = _patch_doc_lock(doc)
        tx, tx_patch = _patch_tx()
        emb, emb_patch = _patch_embeddings(
            side_effect=lambda texts: [[0.1] * 512 for _ in texts]
        )
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            lock_patch,
            _patch_get_or_none(
                KuaiaiKnowledgeBase, _kb(embedding_model_id=33)
            ),
            emb_patch,
            tx_patch,
            _patch_filter(KuaiaiKnowledgeChunk, _FakeQS()),
        ):
            await ks.KnowledgeService.index_document(TENANT, 41)
        assert doc.status == "failed"
        assert "embed" in (doc.error_message or "")
        assert not any("INSERT INTO" in c[0] for c in tx.calls)

    @pytest.mark.asyncio
    async def test_empty_text_fails_and_cleans_chunks(self):
        """空原文 → failed + 残留 chunks 清理（重解析语义）。

        m7：已知异常（ValidationError/BusinessLogicError）的 message 进
        ``error_message``，不再是 ``Type@stage``。
        """
        doc = _doc(raw_content=None, file_uuid=None)
        lock_qs, lock_patch = _patch_doc_lock(doc)
        chunk_qs = _FakeQS([SimpleNamespace(id=1)])
        tx, tx_patch = _patch_tx()
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            lock_patch,
            _patch_get_or_none(KuaiaiKnowledgeBase, _kb()),
            _patch_filter(KuaiaiKnowledgeChunk, chunk_qs),
            tx_patch,
        ):
            await ks.KnowledgeService.index_document(TENANT, 41)
        assert doc.status == "failed"
        assert "可解析内容" in (doc.error_message or "")
        chunk_qs.delete.assert_awaited_once()
        # 失败于 extract 阶段：不得有任何 chunk 写入
        assert not any("INSERT INTO" in c[0] for c in tx.calls)

    @pytest.mark.asyncio
    async def test_file_uuid_path_extracts_bytes(self):
        """file_uuid → FileService.get_file_content bytes → extract_text。"""
        doc = _doc(raw_content=None, file_uuid="f-9", source_type="pdf")
        file_svc = MagicMock()
        file_svc.get_file_content = AsyncMock(return_value=b"%PDF-1.4")
        lock_qs, lock_patch = _patch_doc_lock(doc)
        tx, tx_patch = _patch_tx()
        emb, emb_patch = _patch_embeddings()
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            lock_patch,
            _patch_get_or_none(
                KuaiaiKnowledgeBase, _kb(embedding_model_id=33)
            ),
            patch(
                "core.services.file.file_service.FileService",
                file_svc,
            ),
            patch.object(
                ks, "extract_text", new=AsyncMock(return_value="解析文本")
            ) as mock_extract,
            emb_patch,
            tx_patch,
        ):
            await ks.KnowledgeService.index_document(TENANT, 41)
        file_svc.get_file_content.assert_awaited_once_with(TENANT, "f-9")
        mock_extract.assert_awaited_once_with("pdf", b"%PDF-1.4")
        assert doc.status == "ready"

    @pytest.mark.asyncio
    async def test_chunk_params_fallback_to_tenant_params(self):
        """库列空 → 租户参数 kuaiai_rag_chunk_size/overlap。"""
        doc = _doc(raw_content="短文本")
        kb = _kb(embedding_model_id=33)  # chunk_size/overlap 均空
        lock_qs, lock_patch = _patch_doc_lock(doc)
        tx, tx_patch = _patch_tx()
        emb, emb_patch = _patch_embeddings()
        splitter_seen = {}

        class _SpySplitter:
            def __init__(self, chunk_size, chunk_overlap, **kw):
                splitter_seen["size"] = chunk_size
                splitter_seen["overlap"] = chunk_overlap

            def split_text(self, text):
                return [text]

        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            lock_patch,
            _patch_get_or_none(KuaiaiKnowledgeBase, kb),
            _patch_embed_row(SimpleNamespace(id=77)),
            _patch_params(size=400, overlap=40),
            emb_patch,
            tx_patch,
            patch(
                "langchain_text_splitters.RecursiveCharacterTextSplitter",
                _SpySplitter,
            ),
        ):
            await ks.KnowledgeService.index_document(TENANT, 41)
        assert doc.status == "ready"
        assert splitter_seen == {"size": 400, "overlap": 40}

    @pytest.mark.asyncio
    async def test_invalid_overlap_falls_back_to_defaults(self):
        """overlap ≥ chunk_size → 整体回落默认 800/100。"""
        doc = _doc(raw_content="短文本")
        kb = _kb(embedding_model_id=33, chunk_size=50, chunk_overlap=50)
        lock_qs, lock_patch = _patch_doc_lock(doc)
        tx, tx_patch = _patch_tx()
        emb, emb_patch = _patch_embeddings()
        splitter_seen = {}

        class _SpySplitter:
            def __init__(self, chunk_size, chunk_overlap, **kw):
                splitter_seen["size"] = chunk_size
                splitter_seen["overlap"] = chunk_overlap

            def split_text(self, text):
                return [text]

        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            lock_patch,
            _patch_get_or_none(KuaiaiKnowledgeBase, kb),
            emb_patch,
            tx_patch,
            patch(
                "langchain_text_splitters.RecursiveCharacterTextSplitter",
                _SpySplitter,
            ),
        ):
            await ks.KnowledgeService.index_document(TENANT, 41)
        assert doc.status == "ready"
        assert splitter_seen == {"size": 800, "overlap": 100}

    @pytest.mark.asyncio
    async def test_tenant_id_is_explicit_param(self):
        """KR-I6：tenant_id 为显式参数，index_document 不依赖上下文。"""
        doc = _doc()
        lock_qs, lock_patch = _patch_doc_lock(doc)
        tx, tx_patch = _patch_tx()
        emb, emb_patch = _patch_embeddings()
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            lock_patch,
            _patch_get_or_none(
                KuaiaiKnowledgeBase, _kb(embedding_model_id=33)
            ),
            emb_patch,
            tx_patch,
        ):
            await ks.KnowledgeService.index_document(
                tenant_id=TENANT, document_id=41
            )
        delete_calls = [c for c in tx.calls if "DELETE FROM" in c[0]]
        assert delete_calls[0][1][0] == TENANT

    @pytest.mark.asyncio
    async def test_insert_chunk_sql_param_order(self):
        """_INSERT_CHUNK_SQL 参数位序（review 点名断言）：

        $1=uuid, $2=tenant_id, $3=document_id, $4=chunk_index,
        $5=content, $6=char_count, $7=vector（::vector 强转）。
        """
        doc = _doc()
        lock_qs, lock_patch = _patch_doc_lock(doc)
        tx, tx_patch = _patch_tx()
        emb, emb_patch = _patch_embeddings()
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            lock_patch,
            _patch_get_or_none(
                KuaiaiKnowledgeBase, _kb(embedding_model_id=33)
            ),
            emb_patch,
            tx_patch,
        ):
            await ks.KnowledgeService.index_document(TENANT, 41)
        inserts = [c for c in tx.calls if "INSERT INTO" in c[0]]
        assert inserts, "未执行 chunk 插入"
        sql, params = inserts[0]
        assert "$7::vector" in sql
        _uuid.UUID(params[0])  # $1 uuid 字符串可解析
        assert params[1] == TENANT  # $2 tenant_id
        assert params[2] == doc.id  # $3 document_id
        assert params[3] == 0  # $4 首个 chunk_index
        assert isinstance(params[4], str) and params[4]  # $5 content
        assert params[5] == len(params[4])  # $6 char_count
        assert params[6].startswith("[") and params[6].endswith("]")  # $7 vector


class TestIndexErrorMessage:
    """m7：index_document 失败时 error_message 形态——

    ValidationError/BusinessLogicError 取 message（截断）；
    未知异常保持 ``Type@stage``。
    """

    @pytest.mark.asyncio
    async def test_known_error_message_written_verbatim(self):
        doc = _doc()
        lock_qs, lock_patch = _patch_doc_lock(doc)
        tx, tx_patch = _patch_tx()
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            lock_patch,
            _patch_get_or_none(
                KuaiaiKnowledgeBase, _kb(embedding_model_id=33)
            ),
            patch.object(
                ks,
                "_extract_document_text",
                AsyncMock(
                    side_effect=BusinessLogicError("业务校验失败原因")
                ),
            ),
            _patch_filter(KuaiaiKnowledgeChunk, _FakeQS()),
            tx_patch,
        ):
            await ks.KnowledgeService.index_document(TENANT, 41)
        assert doc.status == "failed"
        assert "业务校验失败原因" in (doc.error_message or "")

    @pytest.mark.asyncio
    async def test_unknown_error_keeps_type_at_stage(self):
        """未知异常 → ``Type@stage``（不落原始堆栈细节）。"""
        doc = _doc()
        lock_qs, lock_patch = _patch_doc_lock(doc)
        tx, tx_patch = _patch_tx()
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            lock_patch,
            _patch_get_or_none(
                KuaiaiKnowledgeBase, _kb(embedding_model_id=33)
            ),
            patch.object(
                ks,
                "_extract_document_text",
                AsyncMock(side_effect=RuntimeError("boom")),
            ),
            _patch_filter(KuaiaiKnowledgeChunk, _FakeQS()),
            tx_patch,
        ):
            await ks.KnowledgeService.index_document(TENANT, 41)
        assert doc.status == "failed"
        assert doc.error_message == "RuntimeError@extract"

    @pytest.mark.asyncio
    async def test_known_error_message_truncated(self):
        """已知异常 message 截断后落 error_message。"""
        doc = _doc()
        lock_qs, lock_patch = _patch_doc_lock(doc)
        tx, tx_patch = _patch_tx()
        long_msg = "校验失败" * 5000  # 远超任何合理截断上限
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            lock_patch,
            _patch_get_or_none(
                KuaiaiKnowledgeBase, _kb(embedding_model_id=33)
            ),
            patch.object(
                ks,
                "_extract_document_text",
                AsyncMock(side_effect=BusinessLogicError(long_msg)),
            ),
            _patch_filter(KuaiaiKnowledgeChunk, _FakeQS()),
            tx_patch,
        ):
            await ks.KnowledgeService.index_document(TENANT, 41)
        assert doc.status == "failed"
        assert len(doc.error_message) < len(long_msg)
        assert doc.error_message.startswith(long_msg[:8])

    @pytest.mark.asyncio
    async def test_document_without_kb_rejected(self):
        """文档未挂载知识库 → 400 业务拒绝（m2）。"""
        doc = _doc(knowledge_id=None)
        lock_qs, lock_patch = _patch_doc_lock(doc)
        tx, tx_patch = _patch_tx()
        with (
            _patch_get_or_none(KuaiaiKnowledgeDocument, doc),
            lock_patch,
            tx_patch,
        ):
            with pytest.raises(BusinessLogicError):
                await ks.KnowledgeService.index_document(TENANT, 41)


class TestCreateDocumentValidation:
    """nit：create_document 新校验（m2 统一 BusinessLogicError）。"""

    @pytest.mark.asyncio
    async def test_blank_title_400(self):
        """title strip 后为空 → 400。"""
        with _patch_get_or_none(KuaiaiKnowledgeBase, _kb()):
            with pytest.raises(BusinessLogicError):
                await ks.KnowledgeService.create_document(
                    TENANT, USER_ID, 9, _payload(title="   ")
                )

    @pytest.mark.asyncio
    async def test_source_type_whitelist_for_file(self):
        """file_uuid 路径 source_type 走文件类型闭集（解析路由类型之外 → 400）。"""
        with _patch_get_or_none(KuaiaiKnowledgeBase, _kb()):
            with pytest.raises(BusinessLogicError):
                await ks.KnowledgeService.create_document(
                    TENANT,
                    USER_ID,
                    9,
                    _payload(
                        source_type="exe",
                        file_uuid="f-1",
                        raw_content=None,
                    ),
                )

    @pytest.mark.asyncio
    async def test_raw_content_only_text_source_type(self):
        """raw_content 直存仅允许 txt/md 类文本 source_type。"""
        with _patch_get_or_none(KuaiaiKnowledgeBase, _kb()):
            with pytest.raises(BusinessLogicError):
                await ks.KnowledgeService.create_document(
                    TENANT,
                    USER_ID,
                    9,
                    _payload(
                        source_type="pdf",
                        file_uuid=None,
                        raw_content="文本内容",
                    ),
                )

    @pytest.mark.asyncio
    async def test_raw_content_too_long_400(self):
        """raw_content 长度上限 200000。"""
        with _patch_get_or_none(KuaiaiKnowledgeBase, _kb()):
            with pytest.raises(BusinessLogicError):
                await ks.KnowledgeService.create_document(
                    TENANT,
                    USER_ID,
                    9,
                    _payload(raw_content="x" * 200_001),
                )

    @pytest.mark.asyncio
    async def test_audit_name_fields_written(self):
        """create_document 写 created_by_name/updated_by_name
        （签名对齐 create_base：user 对象而非裸 user_id）。"""
        created = _doc()
        with (
            _patch_get_or_none(KuaiaiKnowledgeBase, _kb()),
            patch.object(
                KuaiaiKnowledgeDocument,
                "create",
                new=AsyncMock(return_value=created),
            ) as mock_create,
        ):
            await ks.KnowledgeService.create_document(
                TENANT, _user(), 9, _payload()
            )
        kw = mock_create.await_args.kwargs
        assert kw["created_by"] == USER_ID
        assert kw["updated_by"] == USER_ID
        assert kw["created_by_name"] == "测试用户"
        assert kw["updated_by_name"] == "测试用户"
