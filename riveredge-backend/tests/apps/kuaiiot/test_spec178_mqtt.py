from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.kuaiiot.services import mqtt_subscriber_service as service


@pytest.mark.asyncio
async def test_subscribe_and_consume_using_raw_core_config(monkeypatch):
    async def messages():
        yield SimpleNamespace(topic="plant/plc", payload=b'{"tags":{"temp":20}}')
    client = SimpleNamespace(subscribe=AsyncMock(), messages=messages())
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=client)
    manager.__aexit__ = AsyncMock(return_value=None)
    import aiomqtt
    factory = MagicMock(return_value=manager)
    monkeypatch.setattr(aiomqtt, "Client", factory)
    normalizer = AsyncMock(return_value={"stored": True})
    monkeypatch.setattr(service, "normalize_mqtt", normalizer)
    connection = SimpleNamespace(id=1, tenant_id=1, config={"topic": "plant/+"})
    await service.MqttSubscriberService.consume(connection, {"host": "broker.invalid", "password": "synthetic-raw"})
    assert factory.call_args.kwargs["password"] == "synthetic-raw"
    client.subscribe.assert_awaited_once_with("plant/+", qos=1)
    normalizer.assert_awaited_once_with(connection, "plant/plc", {"tags": {"temp": 20}})


@pytest.mark.asyncio
async def test_renewal_failure_closes_consumer_and_releases_lease(db, monkeypatch):
    import asyncio
    from apps.kuaiiot.models.connection import KuaiiotConnection
    from infra.domain.tenant_context import set_current_tenant_id
    set_current_tenant_id(1)
    row = await KuaiiotConnection.create(tenant_id=1, code="renew", name="MQTT", connection_type="mqtt", subscriber_owner=service.MqttSubscriberService._owner)
    closed = asyncio.Event()
    async def listen(*args):
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()
    async def fail_renew(*args):
        await asyncio.sleep(0)
        raise RuntimeError("database unavailable")
    monkeypatch.setattr(service.MqttSubscriberService, '_listen', listen)
    monkeypatch.setattr(service.MqttSubscriberService, '_renew', fail_renew)
    with pytest.raises(RuntimeError, match='database unavailable'):
        await asyncio.wait_for(service.MqttSubscriberService._owned_listen(row, {}), timeout=0.5)
    assert closed.is_set()
    await row.refresh_from_db()
    assert row.subscriber_owner is None
