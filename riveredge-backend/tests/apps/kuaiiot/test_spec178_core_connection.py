"""方案 A：公共连接唯一来源、租户隔离和生命周期。"""

from unittest.mock import AsyncMock

import pytest

from apps.kuaiiot.models.connection import KuaiiotConnection
from apps.kuaiiot.models.tag import KuaiiotTagSnapshot
from apps.kuaiiot.schemas.control import ConnectionCreate, ConnectionOut, DeviceCreate
from apps.kuaiiot.schemas.ingest import IngestBody
from apps.kuaiiot.services import control_service, platform_telemetry
from apps.kuaiiot.services.ingest_service import IngestService
from apps.kuaiiot.services.mqtt_subscriber_service import MqttSubscriberService
from core.models.integration_config import IntegrationConfig
from core.schemas.integration_config import IntegrationConfigCreate, IntegrationConfigUpdate
from core.services.integration.integration_config_service import IntegrationConfigService, build_integration_response
from infra.domain.tenant_context import set_current_tenant_id
from infra.exceptions.exceptions import ValidationError


async def _core(tenant=1, kind="mqtt", code="broker", active=True):
    set_current_tenant_id(tenant)
    return await IntegrationConfig.create(
        tenant_id=tenant, code=code, name="公共连接", type=kind,
        config={"host": "broker.invalid", "password": "synthetic-password"}, is_active=active,
    )


async def _connection(core, kind="mqtt", code="collector"):
    return await control_service.create_connection(1, ConnectionCreate(
        code=code, name="数采", connection_type=kind, integration_uuid=str(core.uuid),
        config={"topic": "plant/+", "device_token_path": "device.token", "tags_path": "tags"},
    ))


def test_core_accepts_mqtt_type():
    assert IntegrationConfigCreate(name="Broker", code="mqtt", type="mqtt").type == "mqtt"


@pytest.mark.asyncio
async def test_association_keeps_credentials_only_in_core(db):
    core = await _core()
    connection = await _connection(core)
    assert connection.integration_id == core.id
    assert "password" not in connection.config and "host" not in connection.config
    assert ConnectionOut.model_validate(connection).integration_id == core.id
    assert build_integration_response(core)["config"]["password"] == "****"
    await IntegrationConfigService.update_integration(1, str(core.uuid), IntegrationConfigUpdate(config={"password": "****"}))
    await core.refresh_from_db()
    assert core.get_config()["password"] == "synthetic-password"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["mqtt", "thingsboard", "jetlinks"])
async def test_external_connection_requires_core(db, kind):
    set_current_tenant_id(1)
    with pytest.raises(ValidationError, match="公共连接"):
        await control_service.create_connection(1, ConnectionCreate(code="missing", name="采集", connection_type=kind))
    assert await KuaiiotConnection.all().count() == 0


@pytest.mark.asyncio
async def test_cross_tenant_and_type_mismatch_are_rejected(db):
    foreign = await _core(2)
    set_current_tenant_id(1)
    with pytest.raises(ValidationError, match="公共连接"):
        await _connection(foreign)
    own = await _core(kind="jetlinks")
    with pytest.raises(ValidationError, match="类型"):
        await _connection(own)


@pytest.mark.asyncio
async def test_mapping_cannot_duplicate_core_credentials(db):
    core = await _core()
    with pytest.raises(ValidationError, match="映射"):
        await control_service.create_connection(1, ConnectionCreate(
            code="duplicate", name="采集", connection_type="mqtt", integration_uuid=str(core.uuid),
            config={"password": "synthetic-duplicate"},
        ))


@pytest.mark.asyncio
async def test_disable_stops_ingest_normalization_and_mqtt_alignment(db, monkeypatch):
    core = await _core()
    connection = await _connection(core)
    device = await control_service.create_device(1, DeviceCreate(
        code="plc", name="PLC", external_device_id="plc", connection_id=connection.id,
    ))
    assert (await MqttSubscriberService.reload())["subscriptions_aligned"] == 1
    await IntegrationConfigService.update_integration(1, str(core.uuid), IntegrationConfigUpdate(is_active=False))
    with pytest.raises(ValidationError, match="停用"):
        await IngestService.ingest(device.device_token, IngestBody(tags={}))
    assert (await MqttSubscriberService.reload())["subscriptions_aligned"] == 0
    spy = AsyncMock()
    monkeypatch.setattr(IngestService, "ingest", spy)
    assert await platform_telemetry.normalize_mqtt(connection, "plant/plc", {"device": {"token": device.device_token}}) == {"stored": False}
    spy.assert_not_awaited()
    assert await KuaiiotTagSnapshot.all().count() == 0


@pytest.mark.asyncio
async def test_referenced_core_cannot_be_deleted_even_when_disabled(db):
    core = await _core()
    await _connection(core)
    await IntegrationConfigService.update_integration(1, str(core.uuid), IntegrationConfigUpdate(is_active=False))
    with pytest.raises(ValidationError, match="数采"):
        await IntegrationConfigService.delete_integration(1, str(core.uuid))
    await core.refresh_from_db()
    assert core.deleted_at is None


@pytest.mark.asyncio
async def test_unused_core_can_be_deleted(db):
    core = await _core()
    await IntegrationConfigService.delete_integration(1, str(core.uuid))
    await core.refresh_from_db()
    assert core.deleted_at is not None


@pytest.mark.asyncio
async def test_mqtt_test_only_validates_configuration(db):
    core = await _core()
    result = await IntegrationConfigService.test_connection(1, str(core.uuid))
    assert result["success"] is True
    assert result["data"]["verification_level"] == "config_only"
    await core.refresh_from_db()
    assert core.is_connected is False


@pytest.mark.parametrize("port", [0, 65536, True, "1883"])
def test_mqtt_rejects_invalid_port(port):
    with pytest.raises(ValueError, match="port"):
        IntegrationConfigService._validate_mqtt_config({"host": "broker.invalid", "port": port})
