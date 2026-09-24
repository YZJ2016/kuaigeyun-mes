"""KU-AI S2 单测：Tool 五值闭集 handler + 页上下文摘要 + manifest ai_tools。

全部 mock Tortoise / 业务 service，不需要真实数据库。覆盖：
- handler 经 tool_bridge 端到端：有 ctx 调到底层 service；无 ctx → 错误 ToolMessage
- build_tool_guard_middleware：无权限回 ToolMessage(status="error")
- search_knowledge 闭包文案（无档案绑定不检索，S3 真实现见 test_s3_wiring）
- page_context：白名单 screen / 未知 screen / 未知 resource / 无权限 / label 不进返回值
- manifest ai_tools 五名与 ENABLED_TOOL_NAMES 一致、handler 可 import
"""

from __future__ import annotations

import importlib
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import ToolMessage

import apps.kuaiai.services.chat_tools as chat_tools
import apps.kuaiai.services.page_context as page_context
from apps.kuaiai.constants import ENABLED_TOOL_NAMES
from core.ai.runtime.context import AiRuntimeContext, reset_ai_context, set_ai_context
from core.ai.runtime.tool_bridge import (
    build_tool_guard_middleware,
    registry_to_lc_tools,
)
from core.ai.tool_registry import ToolRegistry

TENANT = 7
USER_ID = 5

_EXPECTED_PERMISSIONS = {
    "search_knowledge": "kuaiai:act:execute",
    "query_workorder": "kuaizhizao:work-order:read",
    "list_workorder_tasks": "kuaizhizao:work-order:read",
    "submit_production_feedback": "kuaizhizao:production-execution-reporting:create",
    "update_workorder_status": "kuaizhizao:work-order:update",
}


def _user(uid: int = USER_ID):
    return SimpleNamespace(
        id=uid,
        full_name="测试用户",
        username="tester",
        is_infra_admin=False,
        is_tenant_admin=False,
    )


def _ctx(uid: int = USER_ID, **kw):
    return AiRuntimeContext(tenant_id=TENANT, user=_user(uid), **kw)


def _wo(**kw):
    base = dict(
        id=11,
        code="WO-2026-001",
        name="测试工单",
        product_name="产品A",
        status="in_progress",
        quantity=Decimal("100"),
        completed_quantity=Decimal("40"),
        qualified_quantity=Decimal("38"),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _op(**kw):
    base = dict(
        id=501,
        operation_id=88,
        operation_code="OP10",
        operation_name=" CNC加工",
        sequence=1,
        status="in_progress",
        completed_quantity=Decimal("10"),
        qualified_quantity=Decimal("10"),
        unqualified_quantity=Decimal("0"),
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def ai_ctx():
    token = set_ai_context(_ctx())
    try:
        yield
    finally:
        reset_ai_context(token)


class _FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _patch_tx():
    """update_workorder_status 的状态更新+取消副作用包在同一事务内。"""
    return patch.object(
        chat_tools, "in_transaction", MagicMock(return_value=_FakeTx())
    )


class TestManifestAiTools:
    def test_manifest_names_match_closed_set(self):
        manifest_path = (
            Path(chat_tools.__file__).resolve().parents[1] / "manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tools = manifest.get("ai_tools")
        assert isinstance(tools, list)
        assert {t["name"] for t in tools} == set(ENABLED_TOOL_NAMES)

    def test_manifest_handlers_importable(self):
        manifest_path = (
            Path(chat_tools.__file__).resolve().parents[1] / "manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in manifest["ai_tools"]:
            module_path, attr = item["handler"].rsplit(":", 1)
            handler = getattr(importlib.import_module(module_path), attr)
            assert callable(handler)
            assert item["permission"] == _EXPECTED_PERMISSIONS[item["name"]]

    def test_registry_has_handlers_and_permissions(self):
        ToolRegistry.ensure_defaults()
        for name, perm in _EXPECTED_PERMISSIONS.items():
            registered = ToolRegistry._tools.get(name)
            assert registered is not None, name
            assert registered.handler is not None, name
            assert registered.permission == perm, name


class TestToolBridgeEndToEnd:
    @pytest.mark.asyncio
    async def test_query_workorder_calls_service(self, ai_ctx):
        service = MagicMock()
        service.list_work_orders = AsyncMock(return_value=([_wo()], 1))
        with patch(
            "apps.kuaizhizao.services.work_order_service.WorkOrderService",
            return_value=service,
        ):
            tools = registry_to_lc_tools(["query_workorder"])
            result = await tools[0].ainvoke({"keyword": "WO"})
        assert isinstance(result, str)
        assert "WO-2026-001" in result
        assert "进行中" in result
        service.list_work_orders.assert_awaited_once()
        kw = service.list_work_orders.await_args.kwargs
        assert kw.get("current_user").id == USER_ID
        assert service.list_work_orders.await_args.args[0] == TENANT

    @pytest.mark.asyncio
    async def test_query_workorder_detail_by_id(self, ai_ctx):
        service = MagicMock()
        service.get_work_order_by_id = AsyncMock(return_value=_wo())
        with patch(
            "apps.kuaizhizao.services.work_order_service.WorkOrderService",
            return_value=service,
        ):
            tools = registry_to_lc_tools(["query_workorder"])
            result = await tools[0].ainvoke({"work_order_id": 11})
        assert "WO-2026-001" in result
        service.get_work_order_by_id.assert_awaited_once_with(TENANT, 11)

    @pytest.mark.asyncio
    async def test_no_context_returns_error_toolmessage(self):
        tools = registry_to_lc_tools(["query_workorder"])
        result = await tools[0].ainvoke({"keyword": "WO"})
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        assert "上下文" in result.content

    @pytest.mark.asyncio
    async def test_service_exception_returns_error_text(self, ai_ctx):
        service = MagicMock()
        service.list_work_orders = AsyncMock(side_effect=RuntimeError("db down"))
        with patch(
            "apps.kuaizhizao.services.work_order_service.WorkOrderService",
            return_value=service,
        ):
            tools = registry_to_lc_tools(["query_workorder"])
            result = await tools[0].ainvoke({"keyword": "WO"})
        assert isinstance(result, str)
        assert "失败" in result
        assert "db down" not in result

    @pytest.mark.asyncio
    async def test_list_workorder_tasks(self, ai_ctx):
        service = MagicMock()
        service.get_work_order_operations = AsyncMock(return_value=[_op()])
        with patch(
            "apps.kuaizhizao.services.work_order_service.WorkOrderService",
            return_value=service,
        ):
            tools = registry_to_lc_tools(["list_workorder_tasks"])
            result = await tools[0].ainvoke({"work_order_id": 11})
        assert "CNC" in result
        assert "operation_id=88" in result

    @pytest.mark.asyncio
    async def test_update_workorder_status(self, ai_ctx):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=_wo(status="released"))
        service.update_work_order_status = AsyncMock(
            return_value=_wo(status="in_progress")
        )
        with (
            patch(
                "apps.kuaizhizao.services.work_order_service.WorkOrderService",
                return_value=service,
            ),
            _patch_tx(),
        ):
            tools = registry_to_lc_tools(["update_workorder_status"])
            result = await tools[0].ainvoke(
                {"work_order_id": 11, "status": "in_progress"}
            )
        assert "进行中" in result
        service.get_by_id.assert_awaited_once_with(TENANT, 11)
        service.update_work_order_status.assert_awaited_once_with(
            TENANT, 11, status="in_progress", updated_by=USER_ID
        )

    @pytest.mark.asyncio
    async def test_update_workorder_status_rejects_split(self, ai_ctx):
        tools = registry_to_lc_tools(["update_workorder_status"])
        result = await tools[0].ainvoke({"work_order_id": 11, "status": "split"})
        assert "不支持" in result

    @pytest.mark.asyncio
    async def test_submit_production_feedback(self, ai_ctx):
        wo_service = MagicMock()
        wo_service.get_work_order_by_id = AsyncMock(return_value=_wo())
        wo_service.get_work_order_operations = AsyncMock(return_value=[_op()])
        reporting_service = MagicMock()
        reporting_service.create_reporting_record = AsyncMock(
            return_value=SimpleNamespace(id=77, status="pending")
        )
        with (
            patch(
                "apps.kuaizhizao.services.work_order_service.WorkOrderService",
                return_value=wo_service,
            ),
            patch(
                "apps.kuaizhizao.services.reporting_service.ReportingService",
                return_value=reporting_service,
            ),
        ):
            tools = registry_to_lc_tools(["submit_production_feedback"])
            result = await tools[0].ainvoke(
                {
                    "work_order_id": 11,
                    "operation_id": 88,
                    "reported_quantity": 5,
                }
            )
        assert "报工已提交" in result
        assert "id=77" in result
        call = reporting_service.create_reporting_record.await_args
        payload = call.kwargs["reporting_data"]
        assert call.kwargs["tenant_id"] == TENANT
        assert call.kwargs["reported_by"] == USER_ID
        assert payload.work_order_code == "WO-2026-001"
        assert payload.operation_code == "OP10"
        assert payload.worker_id == USER_ID
        assert payload.qualified_quantity == Decimal("5")

    @pytest.mark.asyncio
    async def test_search_knowledge_no_agent_profile(self, ai_ctx):
        """S3 起接真检索：ctx 无 agent_id → 未绑定档案文案（不假检索）。"""
        tools = registry_to_lc_tools(["search_knowledge"])
        result = await tools[0].ainvoke({"query": "如何报工"})
        assert result == chat_tools._ERR_NO_AGENT_PROFILE
        assert "档案" in result

    @pytest.mark.asyncio
    async def test_search_knowledge_no_ctx_error_text(self):
        result = await chat_tools.search_knowledge("q")
        assert "上下文" in result


class TestUpdateWorkorderStatusTransitions:
    """M2：迁移白名单 + 冻结拒绝 + cancel 作废备料单副作用。"""

    def _service(self, current, target=None):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=_wo(status=current))
        service.update_work_order_status = AsyncMock(
            return_value=_wo(status=target or current)
        )
        return service

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "current,target",
        [
            ("released", "in_progress"),
            ("in_progress", "paused"),
            ("paused", "in_progress"),
        ],
    )
    async def test_allowed_transitions(self, ai_ctx, current, target):
        service = self._service(current, target)
        with (
            patch(
                "apps.kuaizhizao.services.work_order_service.WorkOrderService",
                return_value=service,
            ),
            _patch_tx(),
        ):
            result = await chat_tools.update_workorder_status(
                11, target, ctx=_ctx()
            )
        assert "已更新为" in result
        service.update_work_order_status.assert_awaited_once_with(
            TENANT, 11, status=target, updated_by=USER_ID
        )

    @pytest.mark.asyncio
    async def test_cancel_voids_open_batching_orders(self, ai_ctx):
        """in_progress→cancelled：同事务作废进行中线边备料单。"""
        service = self._service("in_progress", "cancelled")
        batching = MagicMock()
        batching.void_open_batching_orders_for_work_order = AsyncMock(
            return_value=2
        )
        with (
            patch(
                "apps.kuaizhizao.services.work_order_service.WorkOrderService",
                return_value=service,
            ),
            patch(
                "apps.kuaizhizao.services.batching_order_service.BatchingOrderService",
                return_value=batching,
            ),
            _patch_tx(),
        ):
            result = await chat_tools.update_workorder_status(
                11, "cancelled", ctx=_ctx()
            )
        assert "已取消" in result
        batching.void_open_batching_orders_for_work_order.assert_awaited_once_with(
            TENANT, 11
        )

    @pytest.mark.asyncio
    async def test_non_cancel_does_not_void_batching(self, ai_ctx):
        service = self._service("in_progress", "paused")
        batching = MagicMock()
        batching.void_open_batching_orders_for_work_order = AsyncMock()
        with (
            patch(
                "apps.kuaizhizao.services.work_order_service.WorkOrderService",
                return_value=service,
            ),
            patch(
                "apps.kuaizhizao.services.batching_order_service.BatchingOrderService",
                return_value=batching,
            ),
            _patch_tx(),
        ):
            result = await chat_tools.update_workorder_status(
                11, "paused", ctx=_ctx()
            )
        assert "已暂停" in result
        batching.void_open_batching_orders_for_work_order.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "current,target",
        [
            ("completed", "in_progress"),
            ("draft", "completed"),
            ("cancelled", "in_progress"),
            ("in_progress", "completed"),
            ("released", "cancelled"),
        ],
    )
    async def test_illegal_transitions_rejected(self, ai_ctx, current, target):
        """白名单外迁移一律拒绝，不触达 update_work_order_status。"""
        service = self._service(current)
        with (
            patch(
                "apps.kuaizhizao.services.work_order_service.WorkOrderService",
                return_value=service,
            ),
            _patch_tx(),
        ):
            result = await chat_tools.update_workorder_status(
                11, target, ctx=_ctx()
            )
        assert "不允许变更" in result
        assert current in result and target in result
        service.update_work_order_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_frozen_work_order_rejected(self, ai_ctx):
        """冻结单任何迁移均拒绝。"""
        service = MagicMock()
        service.get_by_id = AsyncMock(
            return_value=_wo(status="released", is_frozen=True)
        )
        service.update_work_order_status = AsyncMock()
        with (
            patch(
                "apps.kuaizhizao.services.work_order_service.WorkOrderService",
                return_value=service,
            ),
            _patch_tx(),
        ):
            result = await chat_tools.update_workorder_status(
                11, "in_progress", ctx=_ctx()
            )
        assert "已冻结" in result
        service.update_work_order_status.assert_not_called()


class TestToolGuardMiddleware:
    @pytest.mark.asyncio
    async def test_denied_permission_returns_error(self, ai_ctx):
        guard = build_tool_guard_middleware()
        request = SimpleNamespace(
            tool_call={"name": "update_workorder_status", "id": "call-1"}
        )
        handler = AsyncMock(return_value="ok")
        with patch(
            "core.ai.runtime.tool_bridge.UserPermissionService.has_permission",
            new=AsyncMock(return_value=False),
        ):
            result = await guard.awrap_tool_call(request, handler)
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        assert "无权限" in result.content
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_allowed_permission_calls_handler(self, ai_ctx):
        guard = build_tool_guard_middleware()
        request = SimpleNamespace(
            tool_call={"name": "query_workorder", "id": "call-2"}
        )
        handler = AsyncMock(return_value="ok")
        with patch(
            "core.ai.runtime.tool_bridge.UserPermissionService.has_permission",
            new=AsyncMock(return_value=True),
        ):
            result = await guard.awrap_tool_call(request, handler)
        assert result == "ok"
        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_context_error(self):
        guard = build_tool_guard_middleware()
        request = SimpleNamespace(
            tool_call={"name": "query_workorder", "id": "call-3"}
        )
        handler = AsyncMock(return_value="ok")
        result = await guard.awrap_tool_call(request, handler)
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        handler.assert_not_called()


class TestPageContextSummary:
    @pytest.mark.asyncio
    async def test_whitelisted_screen_with_record(self):
        wo_service = MagicMock()
        wo_service.get_work_order_by_id = AsyncMock(return_value=_wo())
        context = {
            "screen": "/apps/kuaizhizao/production-execution/work-orders",
            "screen_label": "伪造页名",
            "resource_key": "kuaizhizao:work_order",
            "record_id": 11,
            "record_label": "伪造单号",
        }
        with (
            patch(
                "apps.kuaizhizao.services.work_order_service.WorkOrderService",
                return_value=wo_service,
            ),
            patch.object(
                page_context.UserPermissionService,
                "has_permission",
                new=AsyncMock(return_value=True),
            ) as has_perm,
        ):
            result = await page_context.build_page_context_summary(
                context, tenant_id=TENANT, user=_user()
            )
        assert result is not None
        assert "工单管理" in result
        assert "WO-2026-001" in result
        assert "伪造页名" not in result
        assert "伪造单号" not in result
        has_perm.assert_awaited_once_with(
            USER_ID, TENANT, "kuaizhizao:work-order:read"
        )

    @pytest.mark.asyncio
    async def test_screen_only(self):
        result = await page_context.build_page_context_summary(
            {"screen": "/apps/kuaizhizao/production-execution/work-orders"},
            tenant_id=TENANT,
            user=_user(),
        )
        assert result == "用户当前位于「工单管理」页面。"

    @pytest.mark.asyncio
    async def test_unknown_screen_returns_none(self):
        result = await page_context.build_page_context_summary(
            {
                "screen": "/apps/evil/page",
                "resource_key": "kuaizhizao:work_order",
                "record_id": 11,
            },
            tenant_id=TENANT,
            user=_user(),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_unknown_resource_returns_none(self):
        result = await page_context.build_page_context_summary(
            {
                "screen": "/apps/kuaizhizao/production-execution/work-orders",
                "resource_key": "kuaizhizao:secret_table",
                "record_id": 1,
            },
            tenant_id=TENANT,
            user=_user(),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_no_permission_returns_none(self):
        with patch.object(
            page_context.UserPermissionService,
            "has_permission",
            new=AsyncMock(return_value=False),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/production-execution/work-orders",
                    "resource_key": "kuaizhizao:work_order",
                    "record_id": 11,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_exception_returns_none(self):
        wo_service = MagicMock()
        wo_service.get_work_order_by_id = AsyncMock(
            side_effect=RuntimeError("db down")
        )
        with (
            patch(
                "apps.kuaizhizao.services.work_order_service.WorkOrderService",
                return_value=wo_service,
            ),
            patch.object(
                page_context.UserPermissionService,
                "has_permission",
                new=AsyncMock(return_value=True),
            ),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/production-execution/work-orders",
                    "resource_key": "kuaizhizao:work_order",
                    "record_id": 11,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_or_invalid_context(self):
        assert (
            await page_context.build_page_context_summary(
                None, tenant_id=TENANT, user=_user()
            )
            is None
        )
        assert (
            await page_context.build_page_context_summary(
                {"screen": "/apps/kuaizhizao/production-execution/work-orders"},
                tenant_id=0,
                user=_user(),
            )
            is None
        )
        assert (
            await page_context.build_page_context_summary(
                {"screen": "/apps/kuaizhizao/production-execution/work-orders"},
                tenant_id=TENANT,
                user=SimpleNamespace(id=None),
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_chat_service_gate_descends_into_extra(self):
        """n1：白名单键嵌在 context.extra 时同样触发摘要，且摊平后传入
        page_context（与 _context_value 同口径）。"""
        import apps.kuaiai.services.chat_service as cs

        captured = {}

        async def _fake_summary(context, *, tenant_id, user):
            captured["context"] = context
            captured["tenant_id"] = tenant_id
            return "用户当前位于「工单管理」页面。"

        with patch.object(
            page_context,
            "build_page_context_summary",
            new=_fake_summary,
        ):
            out = await cs._page_context_summary(
                {
                    "extra": {
                        "screen": "/apps/kuaizhizao/production-execution/work-orders"
                    }
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert out == "用户当前位于「工单管理」页面。"
        # extra 嵌套键摊平为顶层后再交给摘要服务
        assert (
            captured["context"]["screen"]
            == "/apps/kuaizhizao/production-execution/work-orders"
        )
        assert captured["tenant_id"] == TENANT

    @pytest.mark.asyncio
    async def test_chat_service_gate_extra_without_keys_skips(self):
        """extra 存在但无白名单键 → 不触发摘要服务。"""
        import apps.kuaiai.services.chat_service as cs

        mock_summary = AsyncMock(return_value="不应到达")
        with patch.object(
            page_context,
            "build_page_context_summary",
            new=mock_summary,
        ):
            assert (
                await cs._page_context_summary(
                    {"extra": {"unrelated": 1}},
                    tenant_id=TENANT,
                    user=_user(),
                )
                is None
            )
        mock_summary.assert_not_called()
