"""Spec 187：运行时就绪、Hub 只读 Tool 与知识入口回归测试。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.services import agent_scene_service as scene_svc
from apps.kuaiai.services import operations_service as ops_svc


TENANT = 7


@pytest.mark.asyncio
async def test_chat_ready_only_uses_current_runtime_connection():
    catalog_filter = MagicMock()
    with patch(
        "core.ai.runtime_config.AiRuntimeConfig.public_status",
        AsyncMock(return_value={"configured": False, "enabled": False}),
    ), patch(
        "apps.kuaiai.models.catalog.KuaiaiLlmModel.filter",
        catalog_filter,
    ):
        assert await scene_svc.is_chat_ready(TENANT) is False
    catalog_filter.assert_not_called()


@pytest.mark.asyncio
async def test_chat_ready_runtime_failure_is_fail_closed():
    with patch(
        "core.ai.runtime_config.AiRuntimeConfig.public_status",
        AsyncMock(side_effect=RuntimeError("unavailable")),
    ):
        assert await scene_svc.is_chat_ready(TENANT) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chat_ready", "tools_enabled", "readonly_registered", "expected"),
    (
        (True, True, True, "ready"),
        (False, True, True, "not_ready"),
        (True, False, True, "not_ready"),
        (True, True, False, "not_ready"),
    ),
)
async def test_hub_data_query_requires_chat_switch_and_registered_readonly_tool(
    chat_ready, tools_enabled, readonly_registered, expected
):
    with patch.object(
        scene_svc,
        "_site_kuaiai_integration",
        AsyncMock(
            return_value={"tools_enabled": tools_enabled, "rag_enabled": True}
        ),
    ), patch.object(
        ops_svc, "_enabled_knowledge_base_count", AsyncMock(return_value=1)
    ), patch.object(
        ops_svc, "_vision_configured", AsyncMock(return_value=False)
    ), patch.object(
        ops_svc,
        "_has_registered_scene_readonly_tool",
        return_value=readonly_registered,
        create=True,
    ):
        caps = await ops_svc._build_capabilities(
            TENANT, {"configured": chat_ready, "enabled": chat_ready}
        )

    data_query = next(c for c in caps if c["key"] == "data_query")
    assert data_query["status"] == expected


@pytest.mark.asyncio
async def test_hub_knowledge_capability_routes_to_corpus():
    with patch.object(
        scene_svc,
        "_site_kuaiai_integration",
        AsyncMock(return_value={"tools_enabled": True, "rag_enabled": True}),
    ), patch.object(
        ops_svc, "_enabled_knowledge_base_count", AsyncMock(return_value=1)
    ), patch.object(
        ops_svc, "_vision_configured", AsyncMock(return_value=False)
    ), patch.object(
        ops_svc,
        "_has_registered_scene_readonly_tool",
        return_value=True,
        create=True,
    ):
        caps = await ops_svc._build_capabilities(
            TENANT, {"configured": True, "enabled": True}
        )

    knowledge = next(c for c in caps if c["key"] == "knowledge")
    assert knowledge["route"] == "/apps/kuaiai/corpus"


def test_registered_readonly_tool_uses_explicit_scene_closed_set():
    from core.ai.tool_registry import RegisteredTool, ToolRegistry

    write_only = {
        "submit_production_feedback": RegisteredTool(
            name="submit_production_feedback", definition={}
        )
    }
    readonly = {
        "query_inventory_balance": RegisteredTool(
            name="query_inventory_balance", definition={}
        )
    }
    with patch.object(ToolRegistry, "ensure_defaults"), patch.object(
        ToolRegistry, "_tools", write_only
    ):
        assert ops_svc._has_registered_scene_readonly_tool() is False
    with patch.object(ToolRegistry, "ensure_defaults"), patch.object(
        ToolRegistry, "_tools", readonly
    ):
        assert ops_svc._has_registered_scene_readonly_tool() is True
