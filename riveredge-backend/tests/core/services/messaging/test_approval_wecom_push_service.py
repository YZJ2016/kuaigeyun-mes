"""审批消息企微推送配置解析与链接变量。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.services.messaging import approval_wecom_push_service as svc


@pytest.mark.asyncio
async def test_ensure_approval_document_url_prefers_connector_base_url():
    variables: dict = {
        "detail_path": "/personal/tasks?highlight=9",
        "approval_instance_uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "mobile_path": "/(tabs)/approval/detail?uuid=a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    }

    with patch(
        "core.services.integration.wecom_public_base_url.resolve_wecom_public_base_url",
        new=AsyncMock(return_value="https://erp.example.com:16666"),
    ):
        await svc.ensure_approval_document_url(1, variables)

    assert (
        variables["document_url"]
        == "https://erp.example.com:16666/mobile/approval/detail"
        "?uuid=a1b2c3d4-e5f6-7890-abcd-ef1234567890&tenant_id=1"
    )


@pytest.mark.asyncio
async def test_ensure_approval_document_url_falls_back_to_mobile_home():
    variables: dict = {"detail_path": "/personal/tasks"}

    with patch(
        "core.services.integration.wecom_public_base_url.resolve_wecom_public_base_url",
        new=AsyncMock(return_value="https://erp.example.com:16666"),
    ):
        await svc.ensure_approval_document_url(7, variables)

    assert variables["document_url"] == "https://erp.example.com:16666/mobile/?tenant_id=7"


@pytest.mark.asyncio
async def test_ensure_approval_document_url_skips_when_no_origin():
    variables: dict = {"detail_path": "/personal/tasks"}
    with patch(
        "core.services.integration.wecom_public_base_url.resolve_wecom_public_base_url",
        new=AsyncMock(return_value=""),
    ):
        await svc.ensure_approval_document_url(1, variables)
    assert "document_url" not in variables
