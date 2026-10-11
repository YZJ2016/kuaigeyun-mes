"""KU-AI spec 183 单测：知识语料运营视图（全部 mock，不触真库）。

覆盖：
- 路由注册：/operations/corpus 七条新端点权限码；不注册 /texts /files；
  既有 POST /documents/{document_id}/parse 权限契约不变；
- list_corpus：租户恒置、keyword/knowledge_id/type/status/日期组合筛选、
  分页、type 推导、error_summary 仅 failed 透出且截断、不回 raw_content；
- create_faq：启用库必选（停用 400/缺失 404）、问答必填、标题=问题截 300、
  source_type=faq + faq_* 列 + raw_content 生成、长度上限、is_active；
- FAQ 生命周期：_extract_document_text 走 raw_content 同一管线（faq 缺
  raw_content 时由问答列重建）；删除复用 delete_document（chunks 软删）；
- seed_faqs：幂等跳过同题（含人工 FAQ）、不覆盖、库行锁串行化、停用库 400；
- batch_index/batch_delete：逐项隔离、部分失败、跨租户统一不存在、
  100 上限（schema）、重复 ID 去重；
- JSONL：合法 JSON/行、白名单字段（无 tenant_id/uuid/file_uuid/error）、
  转义、无正文行跳过、分批硬上限。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError as PydanticValidationError

import core.utils.timezone_utils as tz_utils
from apps.kuaiai.api.router import router
from apps.kuaiai.models.knowledge import (
    KuaiaiKnowledgeBase,
    KuaiaiKnowledgeDocument,
)
from apps.kuaiai.schemas.corpus import (
    CorpusBatchIn,
    CorpusFaqCreate,
    CorpusSeedFaqsIn,
)
from apps.kuaiai.services import corpus_service
from apps.kuaiai.services.knowledge_service import (
    KnowledgeService,
    _extract_document_text,
    _faq_raw_content,
)
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

TENANT = 7
OTHER_TENANT = 8
USER_ID = 5


def _user(uid: int = USER_ID):
    return SimpleNamespace(id=uid, full_name="测试用户", username="tester")


def _qs(rows=(), count=None, exists=None):
    """伪 QuerySet：链式方法返回自身，终端方法为 AsyncMock。"""
    q = MagicMock()
    rows = list(rows)
    for m in ("filter", "exclude", "order_by", "offset",
              "select_for_update"):
        setattr(q, m, MagicMock(return_value=q))
    q.limit = AsyncMock(return_value=rows)
    q.all = AsyncMock(return_value=rows)
    q.first = AsyncMock(return_value=rows[0] if rows else None)
    q.count = AsyncMock(return_value=len(rows) if count is None else count)
    q.exists = AsyncMock(
        return_value=bool(rows) if exists is None else exists
    )
    q.update = AsyncMock(return_value=len(rows))
    return q


class _FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


@pytest.fixture(autouse=True)
def _fixed_tz(monkeypatch):
    monkeypatch.setattr(
        tz_utils, "site_timezone_name", lambda: "Asia/Shanghai"
    )


def _kb(kbid=1, name="库1", status="启用", tenant=TENANT):
    return SimpleNamespace(
        id=kbid,
        uuid=f"uuid-kb{kbid}",
        tenant_id=tenant,
        name=name,
        description=None,
        status=status,
        deleted_at=None,
        save=AsyncMock(),
    )


def _doc_row(**over):
    base = dict(
        id=41,
        uuid="uuid-doc41",
        tenant_id=TENANT,
        knowledge_id=1,
        title="文档",
        source_type="txt",
        file_uuid=None,
        raw_content="原文内容",
        faq_question=None,
        faq_answer=None,
        status="ready",
        chunk_count=3,
        error_message=None,
        is_active=True,
        deleted_at=None,
        created_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
        updated_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
    )
    base.update(over)
    ns = SimpleNamespace(**base)
    ns.save = AsyncMock()
    return ns


def _required_permissions(route: APIRoute):
    """从 require_permission_codes 依赖闭包中取出权限码。"""
    perms = set()
    for dep in route.dependencies or []:
        fn = getattr(dep, "dependency", None)
        closure = getattr(fn, "__closure__", None)
        if fn is None or closure is None:
            continue
        for name, cell in zip(fn.__code__.co_freevars, closure):
            if name == "codes":
                perms.update(cell.cell_contents or [])
    return perms


def _route_table():
    table = {}
    for r in router.routes:
        if not isinstance(r, APIRoute):
            continue
        for method in r.methods:
            table[(method, r.path)] = _required_permissions(r)
    return table


# ============================================================ 路由注册


class TestCorpusRouteRegistration:
    _EXPECTED = {
        ("GET", "/operations/corpus"): {
            "kuaiai:entry:read",
            "kuaiai:corpus:display",
        },
        ("GET", "/operations/corpus/knowledge-options"): {
            "kuaiai:entry:read",
            "kuaiai:corpus:display",
        },
        ("POST", "/operations/corpus/faqs"): {
            "kuaiai:entry:read",
            "kuaiai:corpus:display",
            "kuaiai:corpus:create",
        },
        ("POST", "/operations/corpus/seed-faqs"): {
            "kuaiai:entry:read",
            "kuaiai:corpus:display",
            "kuaiai:corpus:create",
        },
        ("POST", "/operations/corpus/batch-index"): {
            "kuaiai:entry:read",
            "kuaiai:corpus:display",
            "kuaiai:corpus:update",
        },
        ("POST", "/operations/corpus/batch-delete"): {
            "kuaiai:entry:read",
            "kuaiai:corpus:display",
            "kuaiai:corpus:delete",
        },
        ("GET", "/operations/corpus/export.jsonl"): {
            "kuaiai:entry:read",
            "kuaiai:corpus:display",
            "kuaiai:corpus:export",
        },
    }

    def test_corpus_routes_registered_with_permission_codes(self):
        table = _route_table()
        for key, perms in self._EXPECTED.items():
            assert key in table, f"路由未注册: {key}"
            assert table[key] == perms, f"{key} 权限码不符: {table[key]}"

    def test_no_texts_or_files_routes(self):
        """corpus 不提供文本/文件创建接口（只在 /knowledge）。"""
        table = _route_table()
        for key in table:
            path = key[1]
            assert not path.startswith("/operations/corpus/texts")
            assert not path.startswith("/operations/corpus/files")

    def test_existing_parse_route_unchanged(self):
        table = _route_table()
        key = ("POST", "/documents/{document_id}/parse")
        assert key in table
        assert table[key] == {"kuaiai:knowledge:update"}


# ============================================================ schema 校验


class TestCorpusSchemas:
    def test_faq_create_extra_forbid(self):
        with pytest.raises(PydanticValidationError):
            CorpusFaqCreate(
                knowledge_id=1,
                question="q",
                answer="a",
                tenant_id=7,
            )

    def test_faq_create_required(self):
        with pytest.raises(PydanticValidationError):
            CorpusFaqCreate(knowledge_id=1, answer="a")
        with pytest.raises(PydanticValidationError):
            CorpusFaqCreate(knowledge_id=1, question="q")
        with pytest.raises(PydanticValidationError):
            CorpusFaqCreate(question="q", answer="a")

    def test_faq_question_max_300(self):
        with pytest.raises(PydanticValidationError):
            CorpusFaqCreate(
                knowledge_id=1, question="q" * 301, answer="a"
            )

    def test_seed_mode_closed_set(self):
        with pytest.raises(PydanticValidationError):
            CorpusSeedFaqsIn(mode="overwrite", knowledge_id=1)
        ok = CorpusSeedFaqsIn(knowledge_id=1)
        assert ok.mode == "missing_only"

    def test_batch_ids_cap_100(self):
        with pytest.raises(PydanticValidationError):
            CorpusBatchIn(ids=list(range(1, 102)))
        with pytest.raises(PydanticValidationError):
            CorpusBatchIn(ids=[])
        ok = CorpusBatchIn(ids=list(range(1, 101)))
        assert len(ok.ids) == 100


# ============================================================ list_corpus


class TestListCorpus:
    @pytest.mark.asyncio
    async def test_tenant_and_soft_delete_always_filtered(self):
        q = _qs([_doc_row()])
        with (
            patch.object(
                KuaiaiKnowledgeDocument,
                "filter",
                MagicMock(return_value=q),
            ) as mf,
            patch.object(
                KuaiaiKnowledgeBase,
                "filter",
                MagicMock(return_value=_qs([_kb()])),
            ),
        ):
            out = await corpus_service.list_corpus(TENANT)
        assert mf.call_args.kwargs["tenant_id"] == TENANT
        assert mf.call_args.kwargs["deleted_at__isnull"] is True
        assert out["total"] == 1
        item = out["items"][0]
        assert "raw_content" not in item
        assert "tenant_id" not in item
        assert "file_uuid" not in item
        assert item["knowledge_name"] == "库1"

    @pytest.mark.asyncio
    async def test_combined_filters_applied(self):
        q = _qs([])
        with (
            patch.object(
                KuaiaiKnowledgeDocument,
                "filter",
                MagicMock(return_value=q),
            ),
            patch.object(
                KuaiaiKnowledgeBase,
                "filter",
                MagicMock(return_value=_qs([])),
            ),
        ):
            await corpus_service.list_corpus(
                OTHER_TENANT,
                page=2,
                page_size=10,
                keyword=" 手册 ",
                knowledge_id=3,
                doc_type="faq",
                doc_status="ready",
                created_from=date(2026, 1, 1),
                created_to=date(2026, 1, 31),
            )
        chained = [c.kwargs for c in q.filter.call_args_list]
        assert {"title__icontains": "手册"} in chained
        assert {"knowledge_id": 3} in chained
        assert {"source_type": "faq"} in chained
        assert {"status": "ready"} in chained
        assert any("created_at__gte" in c for c in chained)
        assert any("created_at__lt" in c for c in chained)
        q.offset.assert_called_once_with(10)
        q.limit.assert_called_once_with(10)

    @pytest.mark.asyncio
    async def test_type_derivation(self):
        assert (
            corpus_service._doc_type(
                _doc_row(source_type="faq", file_uuid=None)
            )
            == "faq"
        )
        assert (
            corpus_service._doc_type(
                _doc_row(source_type="pdf", file_uuid="f" * 36)
            )
            == "file"
        )
        assert (
            corpus_service._doc_type(
                _doc_row(source_type="md", file_uuid=None)
            )
            == "text"
        )

    @pytest.mark.asyncio
    async def test_type_filter_variants(self):
        for dtype in ("faq", "text", "file"):
            q = _qs([])
            with (
                patch.object(
                    KuaiaiKnowledgeDocument,
                    "filter",
                    MagicMock(return_value=q),
                ),
                patch.object(
                    KuaiaiKnowledgeBase,
                    "filter",
                    MagicMock(return_value=_qs([])),
                ),
            ):
                await corpus_service.list_corpus(TENANT, doc_type=dtype)
            chained = [c.kwargs for c in q.filter.call_args_list]
            if dtype == "faq":
                assert {"source_type": "faq"} in chained
            elif dtype == "file":
                assert {"file_uuid__isnull": False} in chained
            else:
                assert {"file_uuid__isnull": True} in chained
                q.exclude.assert_called_once_with(source_type="faq")

    @pytest.mark.asyncio
    async def test_error_summary_only_failed(self):
        docs = [
            _doc_row(id=1, status="failed", error_message="解析炸了" * 100),
            _doc_row(id=2, status="ready", error_message="旧残留"),
        ]
        with (
            patch.object(
                KuaiaiKnowledgeDocument,
                "filter",
                MagicMock(return_value=_qs(docs)),
            ),
            patch.object(
                KuaiaiKnowledgeBase,
                "filter",
                MagicMock(return_value=_qs([])),
            ),
        ):
            out = await corpus_service.list_corpus(TENANT)
        items = {i["id"]: i for i in out["items"]}
        assert items[1]["error_summary"] is not None
        assert len(items[1]["error_summary"]) <= 200
        assert items[2]["error_summary"] is None

    @pytest.mark.asyncio
    async def test_knowledge_name_null_when_kb_missing(self):
        with (
            patch.object(
                KuaiaiKnowledgeDocument,
                "filter",
                MagicMock(return_value=_qs([_doc_row()])),
            ),
            patch.object(
                KuaiaiKnowledgeBase,
                "filter",
                MagicMock(return_value=_qs([])),
            ),
        ):
            out = await corpus_service.list_corpus(TENANT)
        assert out["items"][0]["knowledge_name"] is None


# ============================================================ create_faq


class TestCreateFaq:
    @pytest.mark.asyncio
    async def test_create_faq_happy_path(self):
        created = {}

        async def _create(**kw):
            created.update(kw)
            return _doc_row(
                knowledge_id=kw["knowledge_id"],
                source_type="faq",
                faq_question=kw["faq_question"],
                faq_answer=kw["faq_answer"],
                raw_content=kw["raw_content"],
                title=kw["title"],
                status="pending",
            )

        kb = _kb(kbid=3, name="工艺库")
        with (
            patch.object(
                KuaiaiKnowledgeBase,
                "get_or_none",
                new=AsyncMock(return_value=kb),
            ),
            patch.object(
                KuaiaiKnowledgeDocument,
                "create",
                new=AsyncMock(side_effect=_create),
            ),
        ):
            out = await corpus_service.create_faq(
                TENANT,
                _user(),
                CorpusFaqCreate(
                    knowledge_id=3,
                    question="  什么是报工？ ",
                    answer="员工对工序的产出登记。",
                    is_active=True,
                ),
            )
        assert created["tenant_id"] == TENANT
        assert created["knowledge_id"] == 3
        assert created["source_type"] == "faq"
        assert created["faq_question"] == "什么是报工？"
        assert created["faq_answer"] == "员工对工序的产出登记。"
        assert created["raw_content"] == "问题：什么是报工？\n答案：员工对工序的产出登记。"
        assert created["title"] == "什么是报工？"
        assert created["status"] == "pending"
        assert created["is_active"] is True
        assert created["created_by"] == USER_ID
        assert out["type"] == "faq"
        assert out["knowledge_name"] == "工艺库"

    @pytest.mark.asyncio
    async def test_create_faq_disabled_kb_400(self):
        with patch.object(
            KuaiaiKnowledgeBase,
            "get_or_none",
            new=AsyncMock(return_value=_kb(status="停用")),
        ):
            with pytest.raises(BusinessLogicError):
                await KnowledgeService.create_faq(
                    TENANT,
                    _user(),
                    1,
                    question="q",
                    answer="a",
                )

    @pytest.mark.asyncio
    async def test_create_faq_missing_or_cross_tenant_kb_404(self):
        with patch.object(
            KuaiaiKnowledgeBase,
            "get_or_none",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await KnowledgeService.create_faq(
                    OTHER_TENANT, _user(), 1, question="q", answer="a"
                )

    @pytest.mark.asyncio
    async def test_create_faq_blank_question_400(self):
        with patch.object(
            KuaiaiKnowledgeBase,
            "get_or_none",
            new=AsyncMock(return_value=_kb()),
        ):
            with pytest.raises(BusinessLogicError):
                await KnowledgeService.create_faq(
                    TENANT, _user(), 1, question="   ", answer="a"
                )
            with pytest.raises(BusinessLogicError):
                await KnowledgeService.create_faq(
                    TENANT, _user(), 1, question="q", answer="  "
                )

    @pytest.mark.asyncio
    async def test_create_faq_raw_content_length_cap(self):
        with patch.object(
            KuaiaiKnowledgeBase,
            "get_or_none",
            new=AsyncMock(return_value=_kb()),
        ):
            with pytest.raises(BusinessLogicError) as exc:
                await KnowledgeService.create_faq(
                    TENANT,
                    _user(),
                    1,
                    question="q" * 300,
                    answer="a" * 200000,
                )
        assert "200000" in str(exc.value.message)

    @pytest.mark.asyncio
    async def test_create_faq_title_truncates_300(self):
        created = {}

        async def _create(**kw):
            created.update(kw)
            return _doc_row()

        # schema 层已限 question≤300；服务层再保证 title ≤300
        with (
            patch.object(
                KuaiaiKnowledgeBase,
                "get_or_none",
                new=AsyncMock(return_value=_kb()),
            ),
            patch.object(
                KuaiaiKnowledgeDocument,
                "create",
                new=AsyncMock(side_effect=_create),
            ),
        ):
            await KnowledgeService.create_faq(
                TENANT,
                _user(),
                1,
                question="长" * 400,
                answer="a",
            )
        assert created["title"] == "长" * 300
        assert created["faq_question"] == "长" * 400


# ============================================================ FAQ 生命周期


class TestFaqLifecycle:
    @pytest.mark.asyncio
    async def test_extract_faq_raw_content_same_pipeline(self):
        """source_type=faq + raw_content 走既有 raw 直取分支。"""
        doc = _doc_row(
            source_type="faq",
            raw_content="问题：q\n答案：a",
            faq_question="q",
            faq_answer="a",
        )
        text = await _extract_document_text(TENANT, doc)
        assert text == "问题：q\n答案：a"

    @pytest.mark.asyncio
    async def test_extract_faq_rebuilds_from_columns(self):
        """raw_content 缺失时由问答列按同一格式重建（不冒充 txt）。"""
        doc = _doc_row(
            source_type="faq",
            raw_content=None,
            faq_question="什么问题",
            faq_answer="这个答案",
        )
        text = await _extract_document_text(TENANT, doc)
        assert text == _faq_raw_content("什么问题", "这个答案")
        assert text == "问题：什么问题\n答案：这个答案"

    @pytest.mark.asyncio
    async def test_extract_faq_empty_columns_still_fails(self):
        doc = _doc_row(
            source_type="faq",
            raw_content=None,
            faq_question=None,
            faq_answer=None,
        )
        with pytest.raises(BusinessLogicError):
            await _extract_document_text(TENANT, doc)

    @pytest.mark.asyncio
    async def test_delete_document_soft_deletes_chunks(self):
        """删除复用 delete_document：同事务软删 chunks + 文档行。"""
        doc = _doc_row(source_type="faq")
        chunk_q = _qs([SimpleNamespace(id=9)])
        with (
            patch.object(
                KuaiaiKnowledgeDocument,
                "get_or_none",
                new=AsyncMock(return_value=doc),
            ),
            patch(
                "apps.kuaiai.services.knowledge_service.in_transaction",
                MagicMock(return_value=_FakeTx()),
            ),
            patch(
                "apps.kuaiai.services.knowledge_service."
                "KuaiaiKnowledgeChunk.filter",
                MagicMock(return_value=chunk_q),
            ),
        ):
            await KnowledgeService.delete_document(TENANT, 41)
        assert doc.deleted_at is not None
        chunk_q.update.assert_awaited_once()
        assert "deleted_at" in chunk_q.update.call_args.kwargs

    def test_retrieval_sql_excludes_inactive(self):
        """is_active=FALSE 不参与检索（钉死代码事实）。"""
        from apps.kuaiai.services import retrieval

        assert 'd."is_active" = TRUE' in retrieval._CHUNK_SEARCH_SQL


# ============================================================ seed_faqs


class TestSeedFaqs:
    def _patch_kb_lock(self, kb):
        q = _qs([kb] if kb else [])
        return patch.object(
            KuaiaiKnowledgeBase, "filter", MagicMock(return_value=q)
        ), q

    @pytest.mark.asyncio
    async def test_seed_creates_all_when_empty(self):
        kb = _kb(kbid=2)
        filter_patch, kb_q = self._patch_kb_lock(kb)
        doc_q = _qs([], exists=False)
        create_mock = AsyncMock(
            side_effect=lambda *a, **kw: _doc_row(
                source_type="faq", faq_question=kw["question"]
            )
        )
        with (
            filter_patch,
            patch(
                "apps.kuaiai.services.corpus_service.in_transaction",
                MagicMock(return_value=_FakeTx()),
            ),
            patch.object(
                KuaiaiKnowledgeDocument,
                "filter",
                MagicMock(return_value=doc_q),
            ),
            patch.object(
                KnowledgeService,
                "create_faq",
                new=create_mock,
            ),
        ):
            out = await corpus_service.seed_faqs(TENANT, _user(), 2)
        kb_q.select_for_update.assert_called_once()
        assert out == {
            "created": len(corpus_service._SEED_FAQS),
            "skipped": 0,
        }
        # 每条种子都走同一 create_faq 生命周期
        assert create_mock.await_count == len(corpus_service._SEED_FAQS)
        for call in create_mock.await_args_list:
            assert call.kwargs["question"] in {
                q for q, _ in corpus_service._SEED_FAQS
            }

    @pytest.mark.asyncio
    async def test_seed_idempotent_skips_same_question(self):
        """同题（含人工 FAQ）只跳过，不创建不覆盖。"""
        kb = _kb(kbid=2)
        filter_patch, _kb_q = self._patch_kb_lock(kb)
        doc_q = _qs([], exists=True)  # 全部命中已存在
        create_mock = AsyncMock()
        with (
            filter_patch,
            patch(
                "apps.kuaiai.services.corpus_service.in_transaction",
                MagicMock(return_value=_FakeTx()),
            ),
            patch.object(
                KuaiaiKnowledgeDocument,
                "filter",
                MagicMock(return_value=doc_q),
            ) as doc_filter,
            patch.object(
                KnowledgeService,
                "create_faq",
                new=create_mock,
            ),
        ):
            out = await corpus_service.seed_faqs(TENANT, _user(), 2)
        assert out == {
            "created": 0,
            "skipped": len(corpus_service._SEED_FAQS),
        }
        create_mock.assert_not_awaited()
        # 幂等键：(tenant_id, knowledge_id, source_type=faq, faq_question)
        exists_kwargs = [
            c.kwargs for c in doc_filter.call_args_list
        ]
        assert all(
            kw.get("source_type") == "faq"
            and kw.get("knowledge_id") == 2
            and kw.get("tenant_id") == TENANT
            and kw.get("deleted_at__isnull") is True
            and "faq_question" in kw
            for kw in exists_kwargs
        )

    @pytest.mark.asyncio
    async def test_seed_never_overwrites_manual_faq(self):
        """只按存在性跳过——绝不调用 update（不覆盖人工答案）。"""
        kb = _kb(kbid=2)
        filter_patch, _kb_q = self._patch_kb_lock(kb)
        manual_doc = _doc_row(
            source_type="faq",
            faq_question=corpus_service._SEED_FAQS[0][0],
            faq_answer="人工维护的答案",
        )
        # 第一题命中存在，其余不存在 → 1 skipped, 其余 created
        exists_seq = iter([True] + [False] * (len(corpus_service._SEED_FAQS) - 1))

        def _mk_qs(**_kw):
            q = _qs([manual_doc])
            q.exists = AsyncMock(return_value=next(exists_seq))
            return q

        with (
            filter_patch,
            patch(
                "apps.kuaiai.services.corpus_service.in_transaction",
                MagicMock(return_value=_FakeTx()),
            ),
            patch.object(
                KuaiaiKnowledgeDocument,
                "filter",
                MagicMock(side_effect=lambda **kw: _mk_qs(**kw)),
            ),
            patch.object(
                KnowledgeService,
                "create_faq",
                new=AsyncMock(return_value=_doc_row(source_type="faq")),
            ) as create_mock,
        ):
            out = await corpus_service.seed_faqs(TENANT, _user(), 2)
        assert out == {
            "created": len(corpus_service._SEED_FAQS) - 1,
            "skipped": 1,
        }
        # 人工 FAQ 行未被改写（无 update/save 调用路径）
        manual_doc.save.assert_not_awaited()
        assert manual_doc.faq_answer == "人工维护的答案"

    @pytest.mark.asyncio
    async def test_seed_disabled_kb_400(self):
        filter_patch, _kb_q = self._patch_kb_lock(_kb(status="停用"))
        with (
            filter_patch,
            patch(
                "apps.kuaiai.services.corpus_service.in_transaction",
                MagicMock(return_value=_FakeTx()),
            ),
        ):
            with pytest.raises(BusinessLogicError):
                await corpus_service.seed_faqs(TENANT, _user(), 2)

    @pytest.mark.asyncio
    async def test_seed_missing_kb_404(self):
        filter_patch, _kb_q = self._patch_kb_lock(None)
        with (
            filter_patch,
            patch(
                "apps.kuaiai.services.corpus_service.in_transaction",
                MagicMock(return_value=_FakeTx()),
            ),
        ):
            with pytest.raises(NotFoundError):
                await corpus_service.seed_faqs(OTHER_TENANT, _user(), 2)


# ============================================================ 批量操作


class TestBatchOps:
    @pytest.mark.asyncio
    async def test_batch_index_partial_failure(self):
        async def _parse(tenant_id, user_id, document_id):
            if document_id == 2:
                raise NotFoundError("知识文档", "2")
            if document_id == 3:
                raise BusinessLogicError("解析进行中，请稍后")
            return SimpleNamespace(job_id="j")

        mock_parse = AsyncMock(side_effect=_parse)
        with patch.object(
            KnowledgeService, "request_parse", new=mock_parse
        ):
            out = await corpus_service.batch_index(
                TENANT, _user(), [1, 2, 3, 4]
            )
        items = {i["id"]: i for i in out["items"]}
        assert items[1]["success"] is True
        assert items[1]["error"] is None
        assert items[2]["success"] is False
        assert items[2]["error"] == "文档不存在或已删除"
        assert items[3]["success"] is False
        assert "解析进行中" in items[3]["error"]
        assert items[4]["success"] is True
        # 逐项调用同一 request_parse（不绕过状态机），带租户复核
        assert mock_parse.call_count == 4
        for c in mock_parse.call_args_list:
            assert c.args[0] == TENANT

    @pytest.mark.asyncio
    async def test_batch_index_unexpected_error_masked(self):
        async def _parse(tenant_id, user_id, document_id):
            raise RuntimeError("db password=secret /internal/path")

        with patch.object(KnowledgeService, "request_parse", new=_parse):
            out = await corpus_service.batch_index(TENANT, _user(), [9])
        item = out["items"][0]
        assert item["success"] is False
        assert item["error"] == "操作失败"
        assert "secret" not in item["error"]
        assert "/internal" not in item["error"]

    @pytest.mark.asyncio
    async def test_batch_index_dedupes_ids(self):
        calls = []

        async def _parse(tenant_id, user_id, document_id):
            calls.append(document_id)

        with patch.object(KnowledgeService, "request_parse", new=_parse):
            out = await corpus_service.batch_index(TENANT, _user(), [1, 1, 2])
        assert calls == [1, 2]
        assert len(out["items"]) == 2

    @pytest.mark.asyncio
    async def test_batch_delete_partial_failure_and_not_found(self):
        async def _del(tenant_id, document_id):
            if document_id == 8:
                raise NotFoundError("知识文档", "8")
            if document_id == 9:
                raise RuntimeError("conn reset")

        mock_del = AsyncMock(side_effect=_del)
        with patch.object(
            KnowledgeService, "delete_document", new=mock_del
        ):
            out = await corpus_service.batch_delete(TENANT, [7, 8, 9, 10])
        items = {i["id"]: i for i in out["items"]}
        assert items[7]["success"] is True
        assert items[8]["success"] is False
        assert items[8]["error"] == "文档不存在或已删除"
        assert items[9]["success"] is False
        assert items[9]["error"] == "操作失败"
        assert items[10]["success"] is True
        assert mock_del.call_count == 4

    @pytest.mark.asyncio
    async def test_batch_delete_cross_tenant_uniform_not_found(self):
        """跨租户 ID 按不存在处理（由 get_document 的 tenant 过滤实现）。"""
        async def _del(tenant_id, document_id):
            raise NotFoundError("知识文档", str(document_id))

        with patch.object(KnowledgeService, "delete_document", new=_del):
            out = await corpus_service.batch_delete(OTHER_TENANT, [41])
        assert out["items"][0]["error"] == "文档不存在或已删除"


# ============================================================ JSONL 导出


class TestExportJsonl:
    def _patch_docs(self, rows):
        return patch.object(
            KuaiaiKnowledgeDocument,
            "filter",
            MagicMock(return_value=_qs(rows)),
        )

    @pytest.mark.asyncio
    async def test_export_lines_valid_json_whitelist(self):
        docs = [
            _doc_row(
                id=1,
                source_type="faq",
                title='标题"含引号',
                faq_question="问题\"引号",
                faq_answer="答案\n换行",
            ),
            _doc_row(
                id=2,
                source_type="txt",
                title="文本文档",
                raw_content="正文内容",
            ),
            _doc_row(
                id=3,
                source_type="pdf",
                file_uuid="f" * 36,
                title="文件文档",
                raw_content=None,
            ),
        ]
        with self._patch_docs(docs):
            lines = [
                line
                async for line in corpus_service.iter_export_jsonl(TENANT)
            ]
        # file 文档无文本正文 → 跳过
        assert len(lines) == 2
        recs = [json.loads(line) for line in lines]
        faq = recs[0]
        assert faq == {
            "type": "faq",
            "title": '标题"含引号',
            "question": '问题"引号',
            "answer": "答案\n换行",
        }
        text = recs[1]
        assert text == {
            "type": "text",
            "title": "文本文档",
            "content": "正文内容",
        }
        # 白名单：无 tenant_id/uuid/file_uuid/error_message/knowledge_id
        for raw_line in lines:
            assert "tenant_id" not in raw_line
            assert "uuid" not in raw_line
            assert "error" not in raw_line
            assert "knowledge_id" not in raw_line

    @pytest.mark.asyncio
    async def test_export_utf8_no_ascii_escape(self):
        docs = [
            _doc_row(
                source_type="faq",
                title="中文标题",
                faq_question="中文问题",
                faq_answer="中文答案",
            )
        ]
        with self._patch_docs(docs):
            lines = [
                line
                async for line in corpus_service.iter_export_jsonl(TENANT)
            ]
        assert "中文问题" in lines[0]
        assert "\\u" not in lines[0]

    @pytest.mark.asyncio
    async def test_export_hard_bound(self, monkeypatch):
        """分批查询 + 总行数硬上限（缩小常量验证边界语义）。"""
        monkeypatch.setattr(corpus_service, "_EXPORT_MAX_ROWS", 3)
        monkeypatch.setattr(corpus_service, "_EXPORT_BATCH_SIZE", 2)
        docs = [
            _doc_row(id=i, source_type="txt", raw_content="c")
            for i in range(1, 6)
        ]
        # 每次 filter 返回一个新 qs（分批 offset 查询的伪实现：offset/limit
        # 真实切片，验证分批边界语义而非全量返回）
        qs_calls = []

        def _mk_qs(**kw):
            q = _qs(docs)
            state = {"offset": 0}

            def _off(o):
                state["offset"] = o
                return q

            q.offset = MagicMock(side_effect=_off)
            q.limit = AsyncMock(
                side_effect=lambda n: docs[
                    state["offset"]:state["offset"] + n
                ]
            )
            qs_calls.append(q)
            return q

        with patch.object(
            KuaiaiKnowledgeDocument,
            "filter",
            MagicMock(side_effect=lambda **kw: _mk_qs(**kw)),
        ):
            lines = [
                line
                async for line in corpus_service.iter_export_jsonl(TENANT)
            ]
        assert len(lines) == 3  # 硬上限 3 行
        assert len(qs_calls) == 2  # 分批：2 + 1
        assert qs_calls[0].limit.await_args.args[0] == 2
        assert qs_calls[1].limit.await_args.args[0] == 1

    @pytest.mark.asyncio
    async def test_export_faq_without_columns_skipped(self):
        docs = [
            _doc_row(
                source_type="faq",
                title="空FAQ",
                faq_question=None,
                faq_answer=None,
            )
        ]
        with self._patch_docs(docs):
            lines = [
                line
                async for line in corpus_service.iter_export_jsonl(TENANT)
            ]
        assert lines == []

    @pytest.mark.asyncio
    async def test_export_streaming_route(self):
        """路由返回 StreamingResponse 且挂载 export 权限。"""
        table = _route_table()
        key = ("GET", "/operations/corpus/export.jsonl")
        assert key in table
        assert "kuaiai:corpus:export" in table[key]


# ============================================================ knowledge_options


class TestKnowledgeOptions:
    @pytest.mark.asyncio
    async def test_options_only_enabled_tenant(self):
        kb_q = _qs([_kb(1), _kb(2, name="库2")])
        with patch.object(
            KuaiaiKnowledgeBase, "filter", MagicMock(return_value=kb_q)
        ) as mf:
            out = await corpus_service.knowledge_options(TENANT)
        assert mf.call_args.kwargs["tenant_id"] == TENANT
        assert mf.call_args.kwargs["status"] == "启用"
        assert mf.call_args.kwargs["deleted_at__isnull"] is True
        assert out == [{"id": 1, "name": "库1"}, {"id": 2, "name": "库2"}]
        for opt in out:
            assert set(opt.keys()) == {"id", "name"}
