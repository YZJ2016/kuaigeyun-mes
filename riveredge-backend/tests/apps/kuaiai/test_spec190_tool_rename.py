"""KU-AI spec 190 单测：11→9 Tool 合并改名 + enabled_tools 数据迁移。

全部 mock / 假 DB，不需要真实数据库。覆盖：
- 新闭集 / 场景只读闭集（ENABLED−写 Tool）；旧名不再出现于闭集与 manifest；
- query_work_orders 的 view 闭集 summary|operations 与缺 work_order_id 文案；
- query_purchase_orders 承接 supplier_id 过滤（合并 supplier_orders）；
- _normalize_tools 对旧名 400（不保留运行时别名）；
- aerich 迁移 upgrade/downgrade 逐行改写（多租户、去重保序、无旧名不改）；
- 历史 tool 行（旧名）经 to_lc_messages 回放不报错。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import ToolMessage

import apps.kuaiai.services.chat_tools as chat_tools
from apps.kuaiai.constants import ENABLED_TOOL_NAMES, SCENE_READONLY_TOOL_NAMES
from apps.kuaiai.services import agent_service
from core.ai.runtime import memory
from core.ai.runtime.context import AiRuntimeContext
from infra.exceptions.exceptions import BusinessLogicError

TENANT = 7
USER_ID = 5

_OLD_NAMES = {
    "query_workorder",
    "list_workorder_tasks",
    "query_purchase_followup",
    "query_supplier_orders",
    "query_inventory_balance",
    "query_delivery_risk",
    "query_published_schedule",
    "query_quality_anomalies",
}

# spec 190 钉死 9 值；spec 195–200 按其单元追加场景只读 Tool（同步维护）
_EXPECTED_CLOSED_SET = {
    "search_knowledge",
    "query_work_orders",
    "submit_production_feedback",
    "update_workorder_status",
    "query_inventory",
    "analyze_delivery_risk",
    "query_purchase_orders",
    "query_schedule",
    "analyze_quality",
    # spec 195
    "query_sales_orders",
    "query_purchase_arrival_warnings",
    # spec 196
    "query_inventory_alerts",
    "query_replenishment_suggestions",
    "query_slow_moving_inventory",
    # spec 197
    "analyze_kitting",
    "query_material_shortages",
    "query_delivery_delays",
    "query_quality_exceptions",
    # spec 198
    "analyze_first_pass_yield",
    "analyze_defect_pareto",
    # spec 199
    "query_production_daily",
    "query_pulse_signals",
    # spec 200
    "query_process_routes",
}

# spec 201：预置档案只读 Tool 闭集 = ENABLED − 写 Tool
# {submit_production_feedback, update_workorder_status}
_EXPECTED_SCENE_READONLY = _EXPECTED_CLOSED_SET - {
    "submit_production_feedback",
    "update_workorder_status",
}


def _ctx():
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
    )


def _load_migration():
    path = (
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "models"
        / "20261023150000_kuaiai_tool_catalog_rename.py"
    )
    spec = importlib.util.spec_from_file_location(
        "kuaiai_tool_catalog_rename", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeDb:
    """execute_query_dict 返回给定行；execute_query 记录 UPDATE 参数。"""

    def __init__(self, rows):
        self._rows = rows
        self.updates = []

    async def execute_query_dict(self, sql, params=None):
        return [dict(r) for r in self._rows]

    async def execute_query(self, sql, params=None):
        self.updates.append((sql, params))


def _updated_tools(fake_db: _FakeDb, row_id: int):
    for sql, params in fake_db.updates:
        if params[1] == row_id:
            return json.loads(params[0])
    return None


class TestClosedSets:
    def test_enabled_tool_names_closed_set(self):
        assert set(ENABLED_TOOL_NAMES) == _EXPECTED_CLOSED_SET
        assert len(ENABLED_TOOL_NAMES) == len(_EXPECTED_CLOSED_SET)

    def test_scene_readonly_closed_set(self):
        assert set(SCENE_READONLY_TOOL_NAMES) == _EXPECTED_SCENE_READONLY
        assert not SCENE_READONLY_TOOL_NAMES & _OLD_NAMES

    def test_no_old_names_in_manifest(self):
        path = (
            Path(chat_tools.__file__).resolve().parents[1] / "manifest.json"
        )
        manifest = json.loads(path.read_text(encoding="utf-8"))
        names = {t["name"] for t in manifest["ai_tools"]}
        assert names == _EXPECTED_CLOSED_SET
        assert not names & _OLD_NAMES
        handlers = {t["handler"] for t in manifest["ai_tools"]}
        for old in _OLD_NAMES:
            assert not any(old in h for h in handlers), old

    def test_normalize_tools_rejects_old_names(self):
        for old in _OLD_NAMES:
            with pytest.raises(BusinessLogicError):
                agent_service._normalize_tools([old])
        assert agent_service._normalize_tools(
            ["query_work_orders", "analyze_quality"]
        ) == ["query_work_orders", "analyze_quality"]


class TestQueryWorkOrdersView:
    @pytest.mark.asyncio
    async def test_invalid_view_rejected(self):
        out = await chat_tools.query_work_orders(view="evil", ctx=_ctx())
        assert "summary" in out and "operations" in out

    @pytest.mark.asyncio
    async def test_operations_requires_work_order_id(self):
        out = await chat_tools.query_work_orders(
            view="operations", ctx=_ctx()
        )
        assert "work_order_id" in out

    @pytest.mark.asyncio
    async def test_operations_view_dispatches(self):
        service = MagicMock()
        service.get_work_order_operations = AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=1,
                    operation_id=88,
                    operation_code="OP10",
                    operation_name="CNC加工",
                    sequence=1,
                    status="in_progress",
                    completed_quantity=0,
                    qualified_quantity=0,
                    unqualified_quantity=0,
                )
            ]
        )
        with (
            patch(
                "apps.kuaizhizao.services.work_order_service.WorkOrderService",
                return_value=service,
            ),
            patch.object(
                chat_tools,
                "_work_order_in_scope",
                AsyncMock(return_value=True),
            ),
        ):
            out = await chat_tools.query_work_orders(
                view="operations", work_order_id=11, ctx=_ctx()
            )
        assert "operation_id=88" in out

    @pytest.mark.asyncio
    async def test_summary_default_view_dispatches(self):
        service = MagicMock()
        service.list_work_orders = AsyncMock(return_value=([], 0))
        with patch(
            "apps.kuaizhizao.services.work_order_service.WorkOrderService",
            return_value=service,
        ):
            out = await chat_tools.query_work_orders(
                keyword="x", ctx=_ctx()
            )
        assert "未查询到" in out
        service.list_work_orders.assert_awaited_once()


class TestQueryPurchaseOrdersMerge:
    @pytest.mark.asyncio
    async def test_supplier_id_filter_passed_through(self):
        """合并 query_supplier_orders：supplier_id 过滤进同一参数集。"""
        captured = {}

        class _FakePurchaseService:
            async def list_purchase_orders(self, tenant_id, params, current_user=None):
                captured["tenant_id"] = tenant_id
                captured["supplier_id"] = params.supplier_id
                return {"data": [], "total": 0}

        with patch(
            "apps.kuaizhizao.services.purchase_service.PurchaseService",
            return_value=_FakePurchaseService(),
        ):
            from apps.kuaiai.services import scene_tools

            out = await scene_tools.query_purchase_orders(
                supplier_id=9, ctx=_ctx()
            )
        assert captured["tenant_id"] == TENANT
        assert captured["supplier_id"] == 9
        assert "未查询到" in out


@pytest.mark.asyncio
class TestMigration:
    async def test_upgrade_remaps_merges_and_dedupes(self):
        module = _load_migration()
        rows = [
            # 合并：两个旧名 → 同一新名，去重保序
            {
                "id": 1,
                "enabled_tools": [
                    "query_workorder",
                    "list_workorder_tasks",
                    "search_knowledge",
                ],
            },
            # 采购两个旧名合并 + 已含新名去重
            {
                "id": 2,
                "enabled_tools": [
                    "query_supplier_orders",
                    "query_purchase_followup",
                    "query_purchase_orders",
                ],
            },
            # 无旧名：不改写
            {"id": 3, "enabled_tools": ["search_knowledge"]},
            # 空数组：不改写
            {"id": 4, "enabled_tools": []},
            # 其余旧名改名（跨租户同改）
            {
                "id": 5,
                "enabled_tools": [
                    "query_inventory_balance",
                    "query_delivery_risk",
                    "query_published_schedule",
                    "query_quality_anomalies",
                ],
            },
            # 非 list 脏数据：跳过不崩
            {"id": 6, "enabled_tools": None},
        ]
        db = _FakeDb(rows)
        assert await module.upgrade(db) == "SELECT 1;"

        assert _updated_tools(db, 1) == [
            "query_work_orders",
            "search_knowledge",
        ]
        assert _updated_tools(db, 2) == ["query_purchase_orders"]
        assert _updated_tools(db, 5) == [
            "query_inventory",
            "analyze_delivery_risk",
            "query_schedule",
            "analyze_quality",
        ]
        updated_ids = {params[1] for _sql, params in db.updates}
        assert updated_ids == {1, 2, 5}
        # 只改 enabled_tools 列，不动 updated_at/updated_by/tenant_id
        for sql, _params in db.updates:
            assert "updated_at" not in sql
            assert "updated_by" not in sql
            assert "tenant_id" not in sql
            assert '"enabled_tools" = $1::jsonb' in sql

    async def test_downgrade_restores_first_old_name(self):
        """有损回退：合并组还原为各组第一个旧名。"""
        module = _load_migration()
        rows = [
            {
                "id": 1,
                "enabled_tools": [
                    "query_work_orders",
                    "query_purchase_orders",
                    "query_inventory",
                    "analyze_delivery_risk",
                    "query_schedule",
                    "analyze_quality",
                    "search_knowledge",
                ],
            },
        ]
        db = _FakeDb(rows)
        assert await module.downgrade(db) == "SELECT 1;"
        assert _updated_tools(db, 1) == [
            "query_workorder",
            "query_purchase_followup",
            "query_inventory_balance",
            "query_delivery_risk",
            "query_published_schedule",
            "query_quality_anomalies",
            "search_knowledge",
        ]


class TestOldNameReplay:
    def test_legacy_tool_message_replay_no_error(self):
        """历史 tool 行保存旧名：回放仅用于展示/上下文，不触发调用。"""
        rows = [
            SimpleNamespace(
                role="assistant",
                content="",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "query_workorder",
                            "arguments": '{"work_order_id": 9}',
                        },
                    }
                ],
                tool_call_id=None,
                tool_name=None,
            ),
            SimpleNamespace(
                role="tool",
                content="工单 WO-9 状态：进行中",
                tool_calls=None,
                tool_call_id="call_1",
                tool_name="query_workorder",
            ),
        ]
        msgs = memory.to_lc_messages(rows)
        assert isinstance(msgs[1], ToolMessage)
        assert msgs[1].name == "query_workorder"
        assert "WO-9" in msgs[1].content
