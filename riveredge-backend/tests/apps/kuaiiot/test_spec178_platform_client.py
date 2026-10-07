import httpx
import pytest
from core.services.integration.iot_platform_client import PlatformClient
from infra.exceptions.exceptions import ValidationError


@pytest.mark.asyncio
async def test_thingsboard_auth_telemetry_and_rpc_use_core_credentials():
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path == '/api/auth/login':
            return httpx.Response(200, json={'token': 'test-token'})
        assert request.headers['X-Authorization'] == 'Bearer test-token'
        if request.method == 'GET':
            return httpx.Response(200, json={'temperature': [{'ts': 1791331200123, 'value': '20'}]})
        return httpx.Response(200, json={'accepted': True})
    client = PlatformClient('thingsboard', {'base_url': 'https://platform.test', 'username': 'test', 'password': 'test-only'})
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with client:
        assert (await client.telemetry('device-id'))[0]['timestamp'] == 1791331200123
        assert await client.command('device-id', 'set_speed', {'value': 8}, 'request-id') == {'accepted': True}
    assert calls[-1].url.path == '/api/rpc/twoway/device-id'


@pytest.mark.asyncio
async def test_jetlinks_http_success_is_not_device_execution_success():
    def handler(request):
        assert request.headers['X-Access-Token'] == 'test-only'
        return httpx.Response(200, json={'status': 200, 'result': [{'success': False, 'message': 'secret-diagnostic'}]})
    client = PlatformClient('jetlinks', {'base_url': 'https://platform.test', 'token': 'test-only'})
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with client:
        with pytest.raises(ValidationError) as error:
            await client.command('device-id', 'reboot', {}, 'request-id')
        assert 'secret-diagnostic' not in str(error.value)
