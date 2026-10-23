"""Spec 187：运行时就绪回归测试。

hub 能力卡相关用例已由 spec 191 场景卡实现接管：
``data_query`` 泛卡与 ``_has_registered_scene_readonly_tool`` 判就绪口径移除
（``knowledge``/``pulse`` 等固定卡同批退场），状态级联与「档案含业务 Tool」
用例见 ``test_spec191_hub_binding.py``。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.services import agent_scene_service as scene_svc


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
