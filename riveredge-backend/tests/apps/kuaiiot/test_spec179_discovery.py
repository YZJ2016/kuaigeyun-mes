from unittest.mock import AsyncMock
import json

import httpx
import pytest

from apps.kuaiiot.models.connection import KuaiiotConnection
from apps.kuaiiot.services import control_service
from core.models.integration_config import IntegrationConfig
from core.services.integration.iot_platform_client import PlatformClient
from infra.domain.tenant_context import set_current_tenant_id
from infra.exceptions.exceptions import NotFoundError, ValidationError


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["thingsboard", "jetlinks"])
async def test_platform_device_page_scrubs_response_and_uses_pagination(kind):
    def handler(request):
        assert request.method == ("GET" if kind == "thingsboard" else "POST")
        page_key = "page" if kind == "thingsboard" else "pageIndex"
        params = request.url.params if kind == "thingsboard" else json.loads(request.content)
        assert str(params[page_key]) == "2"
        assert str(params["pageSize"]) == "100"
        row = {"id": {"id": "d-1"} if kind == "thingsboard" else "d-1", "name": "Line 1", "password": "secret"}
        result = {"data": [row], "hasNext": True} if kind == "thingsboard" else {"data": [row], "total": 301}
        return httpx.Response(200, json=result if kind == "thingsboard" else {"status": 200, "result": result})
    client = PlatformClient(kind, {"base_url": "https://platform.test", "token": "test-only"})
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with client:
        assert await client.device_page(2) == {"items": [{"external_device_id": "d-1", "name": "Line 1"}], "has_more": True}


@pytest.mark.asyncio
async def test_device_page_failure_is_generic():
    client = PlatformClient("jetlinks", {"base_url": "https://platform.test", "token": "test-only"})
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"status": 200, "result": {"password": "secret"}})))
    async with client:
        with pytest.raises(ValidationError) as exc:
            await client.device_page()
        assert "secret" not in str(exc.value)


@pytest.mark.asyncio
async def test_discovery_uses_exact_tenant_connection_and_blocks_inactive(db, monkeypatch):
    set_current_tenant_id(1)
    core = await IntegrationConfig.create(tenant_id=1, code="core", name="Core", type="jetlinks", config={"base_url": "https://platform.test", "token": "test-only"})
    conn = await KuaiiotConnection.create(tenant_id=1, code="c", name="C", connection_type="jetlinks", integration_id=core.id)
    mock_page = AsyncMock(return_value={"items": [{"external_device_id": "remote", "name": "Remote"}], "has_more": False})
    # Use a local context manager without any external I/O.
    class FakeClient:
        def __init__(self, kind, config):
            assert kind == "jetlinks" and config["token"] == "test-only"
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        device_page = mock_page
    monkeypatch.setattr(control_service, "PlatformClient", FakeClient, raising=False)
    assert (await control_service.discover_external_devices(1, conn.id, page=0))["items"][0]["external_device_id"] == "remote"
    core.is_active = False
    await core.save()
    with pytest.raises(ValidationError):
        await control_service.discover_external_devices(1, conn.id)
    assert mock_page.await_count == 1
    set_current_tenant_id(2)
    with pytest.raises(NotFoundError):
        await control_service.discover_external_devices(2, conn.id)


@pytest.mark.asyncio
async def test_http_and_mqtt_discovery_remains_manual(db):
    set_current_tenant_id(1)
    conn = await KuaiiotConnection.create(tenant_id=1, code="c", name="C", connection_type="http")
    with pytest.raises(ValidationError):
        await control_service.discover_external_devices(1, conn.id)
