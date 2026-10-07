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
