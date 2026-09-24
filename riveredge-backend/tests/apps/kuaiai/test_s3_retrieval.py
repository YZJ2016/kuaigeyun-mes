"""KU-AI S3 单测：retrieval.retrieve 七步流水线。

全部 mock chat/embed/SQL/ORM 层，不需要真实端点与数据库。覆盖：
- 空 knowledge_ids/query → []；越权/停用库行被过滤（非报错）
- 压缩失败回退原句；展开可关（租户参数）；展开失败只留压缩句
- 分库检索参数化 SQL；无 embed 行 → [] 而非炸
- RRF 融合去重；打分失败保留 RRF 顺序；±1 扩窗不整篇
- 整体失败关闭返回 []

m10 修正：展开相关用例显式 patch ``_param_bool``/``_param_int``（见
``_patch_common`` 默认 True/2），不依赖 SystemParameterService 真实调用
失败来回落默认值。
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import apps.kuaiai.services.retrieval as rt
from apps.kuaiai.models.catalog import KuaiaiLlmModel
from apps.kuaiai.models.knowledge import (
    KuaiaiKnowledgeBase,
    KuaiaiKnowledgeChunk,
)

TENANT = 7


def _kb(**kw):
    base = dict(
        id=9,
        tenant_id=TENANT,
        name="kb",
        embedding_model_id=33,
        expand_enabled=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _row(chunk_id, document_id=10, chunk_index=0, distance=0.1,
         content=None, file_name="文档A"):
    return {
        "id": chunk_id,
        "document_id": document_id,
        "chunk_index": chunk_index,
        "content": content if content is not None else f"片段{chunk_id}",
        "file_name": file_name,
        "distance": distance,
    }


class _FakeQS:
    def __init__(self, items=None):
        self._items = list(items or [])
        self.filter_kwargs = None
        self.order_by_calls = []
        # m4：.values(...) await 后返回 dict 行（测试侧直接放 dict）
        self.values = AsyncMock(return_value=list(self._items))

    def filter(self, **kw):
        self.filter_kwargs = kw
        return self

    def order_by(self, *a):
        self.order_by_calls.append(a)
        return self

    async def first(self):
        return self._items[0] if self._items else None

    async def all(self):
        return list(self._items)

    def __await__(self):
        async def _it():
            return list(self._items)

        return _it().__await__()


def _chat(script=None, default="压缩句"):
    """fake chat 模型：ainvoke 按 prompt 关键词分流。

    script: {"compress": str|Exception, "expand": str|Exception,
             "rerank": str|Exception}
    """
    script = script or {}
    chat = MagicMock()

    async def _ainvoke(messages):
        prompt = str(messages[-1].content)
        if "候选片段" in prompt:
            key = "rerank"
        elif "检索变体" in prompt:
            key = "expand"
        else:
            key = "compress"
        value = script.get(key, default if key == "compress" else "")
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(content=value)

    chat.ainvoke = AsyncMock(side_effect=_ainvoke)
    return chat


def _emb(dim=768, fail=False):
    emb = MagicMock()
    if fail:
        emb.aembed_query = AsyncMock(side_effect=RuntimeError("embed down"))
    else:
        emb.aembed_query = AsyncMock(return_value=[0.1] * dim)
    return emb


def _conn(rows_by_call):
    """execute_query_dict 按调用序返回各变体检索结果。"""
    conn = MagicMock()
    conn.execute_query_dict = AsyncMock(side_effect=list(rows_by_call))
    return conn


def _patch_common(kbs=None, conn=None, *, emb=None, chat=None, embed_row=None,
                  param_bool=True, param_int=2, kb_qs=None, chunk_filter=None):
    """统一 patch：KB 复核 / chat / embed / SQL 连接 / 扩窗 ORM / 展开参数。

    返回已进入的 ``contextlib.ExitStack``：``with _patch_common(...):`` 使用，
    退出时统一 undo。

    - ``param_bool``/``param_int``：显式 patch ``rt._param_bool`` /
      ``rt._param_int``（默认 True/2），展开用例不再依赖
      SystemParameterService 真实调用失败回落；
    - ``kb_qs``：传入自备 ``_FakeQS`` 以断言 KB 复核查询的 order_by（m5）；
    - ``chunk_filter``：传入自备 filter mock 以断言 ``_expand_window``
      邻居查询的 filter kwargs。
    """
    kb_qs = kb_qs if kb_qs is not None else _FakeQS(kbs)
    model_qs = _FakeQS([embed_row] if embed_row is not None else [])
    chunk_qs = _FakeQS([])
    stack = contextlib.ExitStack()
    for cm in (
        patch.object(
            KuaiaiKnowledgeBase, "filter", MagicMock(return_value=kb_qs)
        ),
        patch.object(
            KuaiaiLlmModel, "filter", MagicMock(return_value=model_qs)
        ),
        patch.object(
            KuaiaiKnowledgeChunk,
            "filter",
            chunk_filter or MagicMock(return_value=chunk_qs),
        ),
        patch.object(
            rt, "build_chat_model", AsyncMock(return_value=chat or _chat())
        ),
        patch.object(
            rt, "build_embeddings", AsyncMock(return_value=emb or _emb())
        ),
        patch.object(
            rt.Tortoise, "get_connection", MagicMock(return_value=conn)
        ),
        patch.object(rt, "_param_bool", AsyncMock(return_value=param_bool)),
        patch.object(rt, "_param_int", AsyncMock(return_value=param_int)),
    ):
        stack.enter_context(cm)
    return stack


class TestEntryGuard:
    @pytest.mark.asyncio
    async def test_empty_inputs(self):
        assert await rt.retrieve(TENANT, "问题", []) == []
        assert await rt.retrieve(TENANT, "", [9]) == []
        assert await rt.retrieve(TENANT, None, [9]) == []
        assert await rt.retrieve(TENANT, "问题", None) == []

    @pytest.mark.asyncio
    async def test_no_enabled_kb_returns_empty(self):
        """knowledge_ids 复核后无本租户启用库 → []（过滤非报错）。"""
        conn = _conn([])
        with _patch_common([], conn):
            result = await rt.retrieve(TENANT, "问题", [9, 10])
        assert result == []
        conn.execute_query_dict.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_overall_failure_returns_empty(self):
        kb_qs = MagicMock()
        kb_qs.all = AsyncMock(side_effect=RuntimeError("db down"))
        with patch.object(
            KuaiaiKnowledgeBase, "filter", MagicMock(return_value=kb_qs)
        ):
            result = await rt.retrieve(TENANT, "问题", [9])
        assert result == []

    @pytest.mark.asyncio
    async def test_kb_query_ordered_by_id(self):
        """m5：knowledge_ids 复核查询带 order_by("id") 稳定排序。"""
        conn = _conn([[_row(1)]])
        kb_qs = _FakeQS([_kb()])
        with _patch_common(conn=conn, kb_qs=kb_qs):
            await rt.retrieve(TENANT, "问题", [9])
        assert ("id",) in kb_qs.order_by_calls


class TestCompressAndExpand:
    @pytest.mark.asyncio
    async def test_compress_failure_falls_back_to_original(self):
        """压缩异常 → 用原句 embed 检索。"""
        emb = _emb()
        conn = _conn([[_row(1)], [], []])
        chat = _chat(script={"compress": RuntimeError("llm down"),
                             "expand": RuntimeError("llm down")})
        with _patch_common([_kb()], conn, emb=emb, chat=chat):
            result = await rt.retrieve(TENANT, "原始问题", [9])
        assert result and result[0]["document_id"] == 10
        # 变体仅压缩句（展开也失败），embed 收到的是原句
        assert emb.aembed_query.await_count == 1
        assert emb.aembed_query.await_args.args[0] == "原始问题"

    @pytest.mark.asyncio
    async def test_expand_disabled_by_param(self):
        """kuaiai_rag_expand_enabled=false → 只检索压缩句一个变体。"""
        emb = _emb()
        conn = _conn([[_row(1)]])
        chat = _chat(script={"expand": "变体1\n变体2"})
        with _patch_common([_kb()], conn, emb=emb, chat=chat,
                           param_bool=False):
            result = await rt.retrieve(TENANT, "问题", [9])
        assert emb.aembed_query.await_count == 1
        assert emb.aembed_query.await_args.args[0] == "压缩句"
        assert result

    @pytest.mark.asyncio
    async def test_expand_enabled_kb_level_override(self):
        """库级 expand_enabled=False 优先于租户默认开。"""
        emb = _emb()
        conn = _conn([[_row(1)]])
        with _patch_common([_kb(expand_enabled=False)], conn, emb=emb):
            await rt.retrieve(TENANT, "问题", [9])
        assert emb.aembed_query.await_count == 1

    @pytest.mark.asyncio
    async def test_expand_adds_variants(self):
        """展开默认开：压缩句 + ≤count 条变体均参与检索。"""
        emb = _emb()
        conn = _conn([[_row(1)], [_row(2)], [_row(3)]])
        chat = _chat(script={"expand": "变体A\n变体B"})
        with _patch_common([_kb()], conn, emb=emb, chat=chat):
            result = await rt.retrieve(TENANT, "问题", [9])
        queries = [c.args[0] for c in emb.aembed_query.await_args_list]
        assert queries == ["压缩句", "变体A", "变体B"]
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_expand_strips_numbering_keeps_digits(self):
        """nit：剥行首「N.」「N、」编号，但不剥数字本身（变体可含数字）。"""
        emb = _emb()
        conn = _conn([[_row(1)], [_row(2)], [_row(3)], [_row(4)]])
        chat = _chat(
            script={"expand": "1. 变体甲\n2、变体乙\n3变体丙"}
        )
        with _patch_common([_kb()], conn, emb=emb, chat=chat, param_int=4):
            await rt.retrieve(TENANT, "问题", [9])
        queries = [c.args[0] for c in emb.aembed_query.await_args_list]
        assert queries == ["压缩句", "变体甲", "变体乙", "3变体丙"]


class TestPerKbSearch:
    @pytest.mark.asyncio
    async def test_sql_is_parameterized_with_tenant_and_kb(self):
        conn = _conn([[_row(1)], [], []])
        chat = _chat(script={"expand": ""})
        with _patch_common([_kb()], conn, chat=chat):
            await rt.retrieve(TENANT, "问题", [9])
        sql, params = conn.execute_query_dict.await_args_list[0].args
        assert "tenant_id" in sql
        assert "knowledge_id" in sql
        assert "deleted_at" in sql
        assert "embedding_vector" in sql and "IS NOT NULL" in sql
        assert "<=>" in sql and "::vector" in sql
        assert params[0] == TENANT
        assert params[1] == 9
        assert params[2].startswith("[") and params[2].endswith("]")

    @pytest.mark.asyncio
    async def test_no_embed_row_returns_empty_not_crash(self):
        """本租户无 embed 行（库未绑且回落无果）→ 检索 [] 而非炸。"""
        conn = _conn([])
        with _patch_common(
            [_kb(embedding_model_id=None)], conn, embed_row=None
        ):
            result = await rt.retrieve(TENANT, "问题", [9])
        assert result == []
        conn.execute_query_dict.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_embed_query_failure_skips_kb(self):
        conn = _conn([])
        with _patch_common([_kb()], conn, emb=_emb(fail=True)):
            result = await rt.retrieve(TENANT, "问题", [9])
        assert result == []

    @pytest.mark.asyncio
    async def test_wrong_dim_vector_skipped(self):
        conn = _conn([])
        with _patch_common([_kb()], conn, emb=_emb(dim=512)):
            result = await rt.retrieve(TENANT, "问题", [9])
        assert result == []
        conn.execute_query_dict.assert_not_awaited()


class TestRrfAndRerank:
    @pytest.mark.asyncio
    async def test_rrf_fuses_and_dedupes_variants(self):
        """同一 chunk 出现在两个变体结果中 → 融合去重后只出一条。"""
        conn = _conn(
            [[_row(1, chunk_index=1), _row(2, chunk_index=2)],
             [_row(2, chunk_index=2, distance=0.05)]]
        )
        chat = _chat(script={"expand": "变体A",
                             "rerank": RuntimeError("rerank down")})
        with _patch_common([_kb()], conn, chat=chat):
            result = await rt.retrieve(TENANT, "问题", [9])
        # chunk 2 在两个变体榜均出现，去重后仅一条；chunk1 首位得分最高
        assert [r["chunk_index"] for r in result] == [2, 1]

    @pytest.mark.asyncio
    async def test_rerank_failure_keeps_rrf_order(self):
        """打分异常 → 保留 RRF 顺序（chunk1 两榜首位，应排第一）。"""
        conn = _conn(
            [[_row(1, chunk_index=1), _row(2, chunk_index=2)],
             [_row(1, chunk_index=1), _row(3, chunk_index=3)]]
        )
        chat = _chat(script={"expand": "变体A",
                             "rerank": RuntimeError("timeout")})
        with _patch_common([_kb()], conn, chat=chat):
            result = await rt.retrieve(TENANT, "问题", [9])
        assert result[0]["chunk_index"] == 1
        assert [r["chunk_index"] for r in result] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_rerank_success_reorders(self):
        """打分成功 → 按分数重排。"""
        conn = _conn([[_row(1, chunk_index=1), _row(2, chunk_index=2)]])
        chat = _chat(script={"expand": "", "rerank": "0.1, 9.9"})
        with _patch_common([_kb()], conn, chat=chat):
            result = await rt.retrieve(TENANT, "问题", [9])
        assert result[0]["chunk_index"] == 2


class TestWindowExpand:
    @pytest.mark.asyncio
    async def test_window_fetches_only_pm1(self):
        """±1 扩窗：只查同文档 chunk_index±1，不整篇。

        m4：邻居查询走 ``.values(...)`` 返回 dict 行；断言 filter 带
        ``deleted_at__isnull`` / ``document_id`` / ``chunk_index__in``。
        """
        conn = _conn([[_row(5, document_id=10, chunk_index=2, content="命中")]])
        chat = _chat(script={"expand": ""})
        neighbors = [
            {"content": "上一块", "chunk_index": 1},
            {"content": "命中", "chunk_index": 2},
            {"content": "下一块", "chunk_index": 3},
        ]
        chunk_qs = _FakeQS(neighbors)
        filter_mock = MagicMock(return_value=chunk_qs)
        with _patch_common(
            [_kb()], conn, chat=chat, chunk_filter=filter_mock
        ):
            result = await rt.retrieve(TENANT, "问题", [9])
        kw = filter_mock.call_args.kwargs
        assert kw["document_id"] == 10
        assert kw["chunk_index__in"] == [1, 2, 3]
        assert kw["tenant_id"] == TENANT
        assert kw["deleted_at__isnull"] is True
        assert result[0]["content"] == "上一块\n命中\n下一块"
        assert result[0]["file_name"] == "文档A"
        assert result[0]["document_id"] == 10
        assert result[0]["chunk_index"] == 2

    @pytest.mark.asyncio
    async def test_window_missing_neighbor_uses_hit_only(self):
        conn = _conn([[_row(5, document_id=10, chunk_index=0, content="命中")]])
        chat = _chat(script={"expand": ""})
        chunk_qs = _FakeQS([{"content": "命中", "chunk_index": 0}])
        filter_mock = MagicMock(return_value=chunk_qs)
        with _patch_common(
            [_kb()], conn, chat=chat, chunk_filter=filter_mock
        ):
            result = await rt.retrieve(TENANT, "问题", [9])
        kw = filter_mock.call_args.kwargs
        assert kw["chunk_index__in"] == [-1, 0, 1]
        assert kw["deleted_at__isnull"] is True
        assert result[0]["content"] == "命中"
