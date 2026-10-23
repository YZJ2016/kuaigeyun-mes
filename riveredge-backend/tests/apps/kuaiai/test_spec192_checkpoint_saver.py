"""spec 192：TortoiseCheckpointSaver 契约/隔离/中断续跑测试。

sqlite 内存库跑真实 Tortoise 读写；langgraph 小版本升级时本文件为
saver 接口回归项（契约语义与 InMemorySaver 对照、真实小图中断续跑）。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from tortoise import Tortoise
from typing_extensions import TypedDict

from apps.kuaiai.models.checkpoint import (
    KuaiaiAgentCheckpoint,
    KuaiaiAgentCheckpointWrite,
)
from apps.kuaiai.services.checkpoint_saver import TortoiseCheckpointSaver
from infra.domain.tenant_context import clear_tenant_context, with_tenant
from infra.exceptions.exceptions import ValidationError

TENANT_A = 1
TENANT_B = 2


@pytest_asyncio.fixture
async def db():
    clear_tenant_context()
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["apps.kuaiai.models.checkpoint"]},
    )
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        clear_tenant_context()
        await Tortoise.close_connections()


def _cfg(
    tenant: int = TENANT_A,
    thread: str = "1:5:9",
    ns: str = "",
    checkpoint_id: str | None = None,
):
    configurable = {"tenant_id": tenant, "thread_id": thread, "checkpoint_ns": ns}
    if checkpoint_id is not None:
        configurable["checkpoint_id"] = checkpoint_id
    return {"configurable": configurable}


async def _write(saver: TortoiseCheckpointSaver, config, task_id="task-1",
                 writes=(("ch", "v"),), task_path=""):
    await saver.aput_writes(config, writes, task_id=task_id, task_path=task_path)


class TestPutGetContract:
    @pytest.mark.asyncio
    async def test_put_get_roundtrip(self, db):
        saver = TortoiseCheckpointSaver()
        cfg = _cfg()
        cp = empty_checkpoint()
        meta = {"source": "input", "step": -1}
        new_cfg = await saver.aput(cfg, cp, meta, {})
        assert new_cfg["configurable"]["checkpoint_id"] == cp["id"]
        assert new_cfg["configurable"]["tenant_id"] == TENANT_A

        got = await saver.aget_tuple(new_cfg)
        assert got is not None
        assert got.checkpoint["id"] == cp["id"]
        assert got.checkpoint["v"] == cp["v"]
        assert got.metadata["step"] == -1
        assert got.metadata["source"] == "input"
        assert got.parent_config is None
        assert got.pending_writes == []

    @pytest.mark.asyncio
    async def test_parent_chain_and_latest(self, db):
        saver = TortoiseCheckpointSaver()
        cfg = _cfg()
        cp1 = empty_checkpoint()
        cfg1 = await saver.aput(cfg, cp1, {"source": "input", "step": -1}, {})
        cp2 = empty_checkpoint()
        await saver.aput(cfg1, cp2, {"source": "loop", "step": 0}, {})

        # 不带 checkpoint_id → 取最新
        latest = await saver.aget_tuple(_cfg())
        assert latest is not None
        assert latest.checkpoint["id"] == cp2["id"]
        assert latest.parent_config["configurable"]["checkpoint_id"] == cp1["id"]
        # 父链回走仍带 tenant_id（aget_delta_channel_history 依赖）
        assert latest.parent_config["configurable"]["tenant_id"] == TENANT_A
        parent = await saver.aget_tuple(latest.parent_config)
        assert parent is not None and parent.checkpoint["id"] == cp1["id"]

    @pytest.mark.asyncio
    async def test_aget_returns_checkpoint(self, db):
        saver = TortoiseCheckpointSaver()
        cp = empty_checkpoint()
        cfg = await saver.aput(_cfg(), cp, {"step": -1}, {})
        got = await saver.aget(cfg)
        assert got is not None and got["id"] == cp["id"]

    @pytest.mark.asyncio
    async def test_missing_checkpoint_returns_none(self, db):
        saver = TortoiseCheckpointSaver()
        assert await saver.aget_tuple(_cfg(checkpoint_id="nonexistent")) is None
        assert await saver.aget_tuple(_cfg(thread="1:5:404")) is None


class TestListContract:
    @pytest.mark.asyncio
    async def test_list_desc_order_before_limit(self, db):
        saver = TortoiseCheckpointSaver()
        cfg = _cfg()
        ids = []
        current = cfg
        for step in range(3):
            cp = empty_checkpoint()
            current = await saver.aput(current, cp, {"source": "loop", "step": step}, {})
            ids.append(cp["id"])

        tuples = [t async for t in saver.alist(_cfg())]
        assert [t.checkpoint["id"] for t in tuples] == list(reversed(ids))
        assert all(
            t.config["configurable"]["tenant_id"] == TENANT_A for t in tuples
        )

        before_cfg = _cfg(checkpoint_id=ids[2])
        tuples = [t async for t in saver.alist(_cfg(), before=before_cfg)]
        assert [t.checkpoint["id"] for t in tuples] == list(reversed(ids[:2]))

        tuples = [t async for t in saver.alist(_cfg(), limit=1)]
        assert [t.checkpoint["id"] for t in tuples] == [ids[2]]

    @pytest.mark.asyncio
    async def test_list_filter_by_metadata(self, db):
        saver = TortoiseCheckpointSaver()
        cfg = _cfg()
        current = cfg
        for step in range(2):
            cp = empty_checkpoint()
            current = await saver.aput(current, cp, {"source": "loop", "step": step}, {})
        tuples = [t async for t in saver.alist(_cfg(), filter={"step": 0})]
        assert len(tuples) == 1 and tuples[0].metadata["step"] == 0

    @pytest.mark.asyncio
    async def test_list_namespaces_isolated(self, db):
        saver = TortoiseCheckpointSaver()
        cp = empty_checkpoint()
        await saver.aput(_cfg(ns="sub"), cp, {"step": 0}, {})
        assert [t async for t in saver.alist(_cfg())] == []
        assert [t async for t in saver.alist(_cfg(ns="sub"))]
        # config 不带 checkpoint_ns 键 → 不过滤 ns，全部列出
        bare = {"configurable": {"tenant_id": TENANT_A, "thread_id": "1:5:9"}}
        assert len([t async for t in saver.alist(bare)]) == 1


class TestWritesContract:
    @pytest.mark.asyncio
    async def test_pending_writes_roundtrip(self, db):
        saver = TortoiseCheckpointSaver()
        cp = empty_checkpoint()
        cfg = await saver.aput(_cfg(), cp, {"step": 0}, {})
        await _write(saver, cfg, writes=[("ch_a", "v1"), ("ch_b", {"n": 2})])
        got = await saver.aget_tuple(cfg)
        assert got.pending_writes == [("task-1", "ch_a", "v1"), ("task-1", "ch_b", {"n": 2})]

    @pytest.mark.asyncio
    async def test_same_task_regular_writes_idempotent(self, db):
        """同 (task_id, idx) 常规写入重复提交不覆盖、不重复（与 InMemorySaver 一致）。"""
        saver = TortoiseCheckpointSaver()
        cp = empty_checkpoint()
        cfg = await saver.aput(_cfg(), cp, {"step": 0}, {})
        await _write(saver, cfg, writes=[("ch", "first")])
        await _write(saver, cfg, writes=[("ch", "second")])
        got = await saver.aget_tuple(cfg)
        assert got.pending_writes == [("task-1", "ch", "first")]

    @pytest.mark.asyncio
    async def test_special_write_overwrites(self, db):
        """WRITES_IDX_MAP 特殊 channel（idx<0）同 task 重写以最新为准。"""
        from langgraph.checkpoint.serde.types import INTERRUPT

        saver = TortoiseCheckpointSaver()
        cp = empty_checkpoint()
        cfg = await saver.aput(_cfg(), cp, {"step": 0}, {})
        await _write(saver, cfg, writes=[(INTERRUPT, "first")])
        await _write(saver, cfg, writes=[(INTERRUPT, "second")])
        got = await saver.aget_tuple(cfg)
        assert got.pending_writes == [("task-1", INTERRUPT, "second")]
        with with_tenant(TENANT_A):
            count = await KuaiaiAgentCheckpointWrite.filter(tenant_id=TENANT_A).count()
        assert count == 1


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_cross_tenant_invisible(self, db):
        saver = TortoiseCheckpointSaver()
        cp = empty_checkpoint()
        cfg_a = await saver.aput(_cfg(tenant=TENANT_A), cp, {"step": 0}, {})
        await _write(saver, cfg_a)

        # B 租户 config 取同一 thread_id → 不可见（checkpoint 与 writes 均不可见）
        cfg_b = _cfg(tenant=TENANT_B)
        assert await saver.aget_tuple(cfg_b) is None
        cfg_b_id = _cfg(tenant=TENANT_B, checkpoint_id=cp["id"])
        assert await saver.aget_tuple(cfg_b_id) is None
        assert [t async for t in saver.alist(cfg_b)] == []

    @pytest.mark.asyncio
    async def test_missing_keys_raise_and_no_write(self, db):
        saver = TortoiseCheckpointSaver()
        cp = empty_checkpoint()
        with pytest.raises(ValidationError):
            await saver.aput(
                {"configurable": {"thread_id": "1:5:9"}}, cp, {"step": -1}, {}
            )
        with pytest.raises(ValidationError):
            await saver.aput(
                {"configurable": {"tenant_id": TENANT_A}}, cp, {"step": -1}, {}
            )
        with pytest.raises(ValidationError):
            await saver.aget_tuple({"configurable": {"tenant_id": TENANT_A}})
        with pytest.raises(ValidationError):
            await saver.aput_writes(
                {"configurable": {"tenant_id": TENANT_A, "thread_id": "1:5:9"}},
                [("ch", "v")],
                task_id="t",
            )
        with with_tenant(TENANT_A):
            assert await KuaiaiAgentCheckpoint.filter(tenant_id=TENANT_A).count() == 0
            assert await KuaiaiAgentCheckpointWrite.filter(tenant_id=TENANT_A).count() == 0


class TestDeleteAndPurge:
    @pytest.mark.asyncio
    async def test_adelete_thread_clears_both_tables(self, db):
        saver = TortoiseCheckpointSaver()
        cp = empty_checkpoint()
        cfg = await saver.aput(_cfg(), cp, {"step": 0}, {})
        await _write(saver, cfg)
        await saver.adelete_thread("1:5:9", tenant_id=TENANT_A)
        assert await saver.aget_tuple(_cfg()) is None
        with with_tenant(TENANT_A):
            assert await KuaiaiAgentCheckpoint.filter(tenant_id=TENANT_A).count() == 0
            assert await KuaiaiAgentCheckpointWrite.filter(tenant_id=TENANT_A).count() == 0

    @pytest.mark.asyncio
    async def test_purge_tenant_scoped(self, db):
        saver = TortoiseCheckpointSaver()
        await saver.aput(_cfg(tenant=TENANT_A, thread="1:5:9"), empty_checkpoint(), {"step": 0}, {})
        await saver.aput(_cfg(tenant=TENANT_B, thread="2:5:9"), empty_checkpoint(), {"step": 0}, {})
        deleted = await saver.purge_older_than(
            TENANT_A, datetime.now(UTC) + timedelta(seconds=1)
        )
        assert deleted == 1
        assert await saver.aget_tuple(_cfg(tenant=TENANT_A, thread="1:5:9")) is None
        assert await saver.aget_tuple(_cfg(tenant=TENANT_B, thread="2:5:9")) is not None

    @pytest.mark.asyncio
    async def test_purge_all_tenants(self, db):
        saver = TortoiseCheckpointSaver()
        await saver.aput(_cfg(tenant=TENANT_A), empty_checkpoint(), {"step": 0}, {})
        await saver.aput(_cfg(tenant=TENANT_B, thread="2:5:9"), empty_checkpoint(), {"step": 0}, {})
        deleted = await saver.purge_older_than(
            None, datetime.now(UTC) + timedelta(seconds=1)
        )
        assert deleted == 2
        await asyncio.sleep(0)  # 让 unscoped 审计 task 落地（写入失败已降级为日志）


class TestInMemoryParity:
    @pytest.mark.asyncio
    async def test_same_ops_same_results_as_inmemory(self, db):
        """契约对照：同一组操作在 InMemorySaver 与本 saver 结果一致。"""
        tortoise_saver = TortoiseCheckpointSaver()
        memory_saver = InMemorySaver()
        cfg = _cfg()
        current_t = cfg
        current_m = cfg
        checkpoints = []
        for step in range(3):
            cp = empty_checkpoint()
            meta = {"source": "loop" if step else "input", "step": step - 1}
            current_t = await tortoise_saver.aput(current_t, cp, meta, {})
            current_m = memory_saver.put(current_m, cp, meta, {})
            checkpoints.append(cp)

        # get_tuple 对照（本 saver 返回 config 保留 tenant_id，故其存入 metadata
        # 的 configurable 标量比 InMemorySaver 多 tenant_id——属预期的租户强化；
        # 对照输入 metadata 键一致即可）
        t_tuple = await tortoise_saver.aget_tuple(current_t)
        m_tuple = memory_saver.get_tuple(current_m)
        assert t_tuple.checkpoint == m_tuple.checkpoint
        assert {k: t_tuple.metadata[k] for k in m_tuple.metadata} == m_tuple.metadata
        assert t_tuple.metadata["tenant_id"] == TENANT_A
        assert (
            t_tuple.parent_config["configurable"]["checkpoint_id"]
            == m_tuple.parent_config["configurable"]["checkpoint_id"]
        )
        # list 顺序对照
        t_ids = [t.checkpoint["id"] async for t in tortoise_saver.alist(_cfg())]
        m_ids = [t.checkpoint["id"] for t in memory_saver.list(_cfg())]
        assert t_ids == m_ids
        # before + limit 对照
        t_before = [
            t.checkpoint["id"]
            async for t in tortoise_saver.alist(
                _cfg(),
                before={"configurable": {"checkpoint_id": checkpoints[2]["id"]}},
                limit=1,
            )
        ]
        m_before = [
            t.checkpoint["id"]
            for t in memory_saver.list(
                _cfg(),
                before={"configurable": {"checkpoint_id": checkpoints[2]["id"]}},
                limit=1,
            )
        ]
        assert t_before == m_before

        # writes 对照
        await tortoise_saver.aput_writes(current_t, [("ch", "v")], task_id="t1")
        memory_saver.put_writes(current_m, [("ch", "v")], "t1")
        t_tuple = await tortoise_saver.aget_tuple(current_t)
        m_tuple = memory_saver.get_tuple(current_m)
        assert t_tuple.pending_writes == m_tuple.pending_writes


class TestRealGraphInterruptResume:
    """真实小图（一个 interrupt 节点）：中断 → 新 saver 实例（模拟重启）→ resume 续跑。"""

    class _State(TypedDict):
        text: str

    @staticmethod
    def _build_graph(saver):
        def ask(state: TestRealGraphInterruptResume._State):
            answer = interrupt("confirm?")
            return {"text": state["text"] + answer}

        builder = StateGraph(TestRealGraphInterruptResume._State)
        builder.add_node("ask", ask)
        builder.add_edge(START, "ask")
        builder.add_edge("ask", END)
        return builder.compile(checkpointer=saver)

    @pytest.mark.asyncio
    async def test_interrupt_then_resume_after_restart(self, db):
        cfg = _cfg()
        graph1 = self._build_graph(TortoiseCheckpointSaver())
        result = await graph1.ainvoke({"text": "go:"}, cfg)
        assert "__interrupt__" in result

        # 模拟服务重启：全新 saver 实例 + 重新编译，执行现场从 DB 取回
        graph2 = self._build_graph(TortoiseCheckpointSaver())
        resumed = await graph2.ainvoke(Command(resume="yes"), cfg)
        assert resumed["text"] == "go:yes"
        assert "__interrupt__" not in resumed

    @pytest.mark.asyncio
    async def test_interrupt_state_not_cross_tenant(self, db):
        cfg_a = _cfg(tenant=TENANT_A)
        graph = self._build_graph(TortoiseCheckpointSaver())
        result_a = await graph.ainvoke({"text": "go:"}, cfg_a)
        assert "__interrupt__" in result_a
        # B 租户同 thread_id 下无执行现场：新输入从头跑，重新命中 interrupt
        cfg_b = _cfg(tenant=TENANT_B)
        result_b = await graph.ainvoke({"text": "b:"}, cfg_b)
        assert "__interrupt__" in result_b
        # A 仍可正常续跑
        resumed = await graph.ainvoke(Command(resume="yes"), cfg_a)
        assert resumed["text"] == "go:yes"


class TestUnsupportedInterfaces:
    def test_sync_interfaces_raise(self):
        # 不需要 db：同步接口先抛 NotImplementedError，不触库
        saver = TortoiseCheckpointSaver()
        with pytest.raises(NotImplementedError):
            saver.get_tuple(_cfg())
        with pytest.raises(NotImplementedError):
            saver.put(_cfg(), empty_checkpoint(), {}, {})
        with pytest.raises(NotImplementedError):
            saver.put_writes(_cfg(), [("ch", "v")], "t")
        with pytest.raises(NotImplementedError):
            list(saver.list(_cfg()))
        with pytest.raises(NotImplementedError):
            saver.delete_thread("1:5:9")

    @pytest.mark.asyncio
    async def test_unimplemented_async_extensions_raise(self, db):
        saver = TortoiseCheckpointSaver()
        with pytest.raises(NotImplementedError):
            await saver.aprune(["1:5:9"])
        with pytest.raises(NotImplementedError):
            await saver.acopy_thread("1:5:9", "1:5:10")
        with pytest.raises(NotImplementedError):
            await saver.adelete_for_runs(["run-1"])
