"""spec 152：边缘配置下发、心跳、离线标记与批量续传。"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaizhizao.models.equipment_status_monitor import EquipmentStatusMonitor
from apps.kuaiiot.models.alert import KuaiiotAlert, KuaiiotAlertRule
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.edge_config import KuaiiotEdgeConfig
from apps.kuaiiot.models.tag import KuaiiotTagSnapshot
from apps.kuaiiot.schemas.control import ConnectionCreate, DeviceCreate, TagCreate
from apps.kuaiiot.schemas.ingest import IngestBody
from apps.kuaiiot.services import control_service
from apps.kuaiiot.services.edge_config_service import EdgeConfigService
from apps.kuaiiot.workflows.functions.device_lifecycle_workflow import run_kuaiiot_offline_check
from apps.kuaiiot.workflows.functions.edge_agent_lifecycle_workflow import run_kuaiiot_edge_agent_offline_check
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import TenantContextError, clear_tenant_context, set_current_tenant_id
from infra.exceptions.exceptions import AuthenticationError, NotFoundError, ValidationError


def _modbus(host: str = "127.0.0.1", mode: str = "http_ingest") -> dict:
    return {
        "host": host,
        "port": 502,
        "unit_id": 1,
        "registers": [{"tag_key": "temp", "address": 0, "data_type": "float32"}],
        "publish": {"mode": mode},
    }


async def _device(suffix: str, equipment_uuid: str | None = None) -> KuaiiotDevice:
    connection = await control_service.create_connection(
        _tenant(),
        ConnectionCreate(code=f"conn-{suffix}", name="线边", connection_type="http"),
    )
    return await control_service.create_device(
        _tenant(),
        DeviceCreate(
            connection_id=connection.id,
            external_device_id=f"ext-{suffix}",
            code=f"dev-{suffix}",
            name=f"采集{suffix}",
            equipment_uuid=equipment_uuid,
        ),
    )


def _tenant() -> int:
    from infra.domain.tenant_context import get_current_tenant_id

    current = get_current_tenant_id()
    if current is None:
        raise RuntimeError("测试未设置租户")
    return int(current)


async def _tagged_device(suffix: str, equipment_uuid: str | None = None) -> KuaiiotDevice:
    device = await _device(suffix, equipment_uuid)
    await control_service.create_tag(
        _tenant(),
        device.id,
        TagCreate(tag_key="temp", name="温度", value_type="number", map_target="temperature"),
    )
    await control_service.create_tag(
        _tenant(),
        device.id,
        TagCreate(tag_key="run", name="状态", value_type="text", map_target="status"),
    )
    return device


async def _save(device: KuaiiotDevice, code: str, config: dict | None = None, protocol: str = "modbus_tcp") -> dict:
    return await EdgeConfigService.save_config(
        _tenant(),
        code=code,
        name=code,
        device_id=device.id,
        protocol=protocol,
        config=config or _modbus(),
    )


@pytest.mark.asyncio
async def test_pull_paths_heartbeat_and_tenant_isolation(db):
    set_current_tenant_id(1)
    own = await _tagged_device("own")
    other_device = await _device("peer")
    saved = await _save(own, "line1")
    await _save(other_device, "peer-line")
    assert saved["config_version"] == 1

    set_current_tenant_id(2)
    foreign = await _device("foreign")
    await _save(foreign, "line1", _modbus(host="10.9.9.9"))
    await _save(foreign, "only-foreign", _modbus(host="10.8.8.8"))

    clear_tenant_context()
    with pytest.raises(TenantContextError):
        await EdgeConfigService.list_configs(1)

    pulled = await EdgeConfigService.pull_runtime_config(own.device_token, "line1")
    assert pulled["config_version"] == 1
    assert pulled["protocol"] == "modbus_tcp"
    assert pulled["config"]["host"] == "127.0.0.1"
    assert pulled["ingest_path"] == f"/api/v1/apps/kuaiiot/ingest/{own.device_token}"
    assert pulled["batch_ingest_path"] == f"/api/v1/apps/kuaiiot/ingest/{own.device_token}/batch"
    assert pulled["heartbeat_path"] == f"/api/v1/apps/kuaiiot/edge-runtime/{own.device_token}/heartbeat"
    assert pulled["command_result_path"] == (
        f"/api/v1/apps/kuaiiot/edge-runtime/{own.device_token}/command-result"
    )
    assert "pending_commands" not in pulled
    assert "device_token" not in pulled

    with pytest.raises(NotFoundError) as missing_foreign:
        await EdgeConfigService.pull_runtime_config(own.device_token, "only-foreign")
    assert own.device_token not in str(missing_foreign.value)

    with pytest.raises(NotFoundError):
        await EdgeConfigService.pull_runtime_config(own.device_token, "peer-line")

    with pytest.raises(AuthenticationError) as bad_token:
        await EdgeConfigService.pull_runtime_config("not-a-device-token", "line1")
    assert "not-a-device-token" not in str(bad_token.value)

    same = await EdgeConfigService.record_heartbeat(
        own.device_token,
        edge_config_code="line1",
        config_version=1,
        agent_version="1.0.0",
        buffer_pending_count=2,
        status="online",
    )
    assert same["config_changed"] is False
    assert same["pending_commands"] == []

    set_current_tenant_id(1)
    changed_save = await _save(own, "line1", _modbus(host="10.0.0.8"))
    assert changed_save["config_version"] == 2
    clear_tenant_context()
    changed = await EdgeConfigService.record_heartbeat(
        own.device_token,
        edge_config_code="line1",
        config_version=1,
        agent_version="1.0.0",
        buffer_pending_count=4,
        status="online",
    )
    assert changed["config_changed"] is True
    assert changed["pending_commands"] == []

    set_current_tenant_id(1)
    row = await KuaiiotEdgeConfig.get(code="line1", device_id=own.id)
    assert row.agent_version == "1.0.0"
    assert row.agent_status == "online"
    assert row.buffer_pending_count == 4
    assert row.last_agent_heartbeat_at is not None
    assert own.device_token not in str(changed)


@pytest.mark.asyncio
async def test_disabled_config_and_secret_are_rejected(db):
    set_current_tenant_id(1)
    device = await _device("off")
    await EdgeConfigService.save_config(
        1,
        code="paused",
        name="暂停",
        device_id=device.id,
        protocol="modbus_tcp",
        config=_modbus(),
        is_enabled=False,
    )
    clear_tenant_context()
    with pytest.raises(NotFoundError):
        await EdgeConfigService.pull_runtime_config(device.device_token, "paused")

    set_current_tenant_id(1)
    with pytest.raises(ValidationError, match="口令"):
        await _save(device, "secret", {**_modbus(), "password": "hide-me"})


@pytest.mark.asyncio
async def test_mqtt_and_non_modbus_tcp_save_without_collector(db):
    set_current_tenant_id(1)
    device = await _device("proto")
    mqtt = await _save(device, "mqtt-line", _modbus(mode="mqtt"))
    assert mqtt["config"]["publish"]["mode"] == "mqtt"
    opc = {
        "endpoint": "opc.tcp://127.0.0.1:4840",
        "nodes": [{"tag_key": "temp", "node_id": "ns=2;s=Temp"}],
        "publish": {"mode": "http_ingest"},
    }
    saved_opc = await _save(device, "opc-line", opc, protocol="opc_ua")
    assert saved_opc["protocol"] == "opc_ua"
    with pytest.raises(ValidationError, match="endpoint"):
        await _save(device, "opc-bad", {"nodes": [{"tag_key": "temp"}], "publish": {"mode": "http_ingest"}}, protocol="opc_ua")
    with pytest.raises(ValidationError, match="db_blocks"):
        await _save(
            device,
            "s7-bad",
            {"host": "192.168.1.20", "rack": 0, "slot": 1, "publish": {"mode": "mqtt"}},
            protocol="s7",
        )
    rtu = await _save(device, "rtu-line", _modbus(), protocol="modbus_rtu")
    assert rtu["protocol"] == "modbus_rtu"


@pytest.mark.asyncio
async def test_offline_marks_do_not_insert_alerts(db):
    set_current_tenant_id(1)
    stale = await _device("stale")
    fresh = await _device("fresh")
    never = await _device("never")
    inconsistent = await _device("null-seen")
    now = resolve_business_datetime()
    stale.is_online = True
    stale.last_seen_at = now - timedelta(minutes=6)
    await stale.save(update_fields=["is_online", "last_seen_at", "updated_at"])
    fresh.is_online = True
    fresh.last_seen_at = now - timedelta(minutes=1)
    await fresh.save(update_fields=["is_online", "last_seen_at", "updated_at"])
    inconsistent.is_online = True
    inconsistent.last_seen_at = None
    await inconsistent.save(update_fields=["is_online", "last_seen_at", "updated_at"])

    await _save(stale, "edge-stale")
    await _save(fresh, "edge-fresh")
    old = await KuaiiotEdgeConfig.get(code="edge-stale")
    old.last_agent_heartbeat_at = now - timedelta(minutes=4)
    old.agent_status = "online"
    await old.save(update_fields=["last_agent_heartbeat_at", "agent_status", "updated_at"])
    recent = await KuaiiotEdgeConfig.get(code="edge-fresh")
    recent.last_agent_heartbeat_at = now - timedelta(minutes=1)
    recent.agent_status = "online"
    await recent.save(update_fields=["last_agent_heartbeat_at", "agent_status", "updated_at"])

    clear_tenant_context()
    device_result = await run_kuaiiot_offline_check()
    agent_result = await run_kuaiiot_edge_agent_offline_check()
    assert device_result["devices_marked_offline"] == 1
    assert agent_result["agents_marked_offline"] == 1

    set_current_tenant_id(1)
    await stale.refresh_from_db()
    await fresh.refresh_from_db()
    await never.refresh_from_db()
    await inconsistent.refresh_from_db()
    await old.refresh_from_db()
    await recent.refresh_from_db()
    assert stale.is_online is False
    assert fresh.is_online is True
    assert never.is_online is False
    assert inconsistent.is_online is True
    assert old.agent_status == "offline"
    assert recent.agent_status == "online"
    assert await KuaiiotAlert.all().count() == 0
    assert await KuaiiotAlertRule.filter(rule_type="offline").count() == 0


@pytest.mark.asyncio
async def test_batch_uses_single_ingest_and_rejects_101(db):
    set_current_tenant_id(1)
    equipment = await Equipment.create(tenant_id=1, code="EQ-EDGE", name="停用机床", status="停用")
    previous = await EquipmentStatusMonitor.create(
        tenant_id=1,
        equipment_id=equipment.id,
        equipment_uuid=equipment.uuid,
        equipment_code=equipment.code,
        equipment_name=equipment.name,
        status="故障",
        is_online=True,
        data_source="sensor",
        monitored_at=resolve_business_datetime() - timedelta(seconds=30),
    )
    await EquipmentStatusMonitor.filter(id=previous.id).update(
        created_at=resolve_business_datetime() - timedelta(seconds=30)
    )
    device = await _tagged_device("batch", equipment.uuid)

    with pytest.raises(ValidationError) as too_many:
        await EdgeConfigService.ingest_batch(
            device.device_token,
            [IngestBody(tags={"temp": 1}, idempotency_key=f"k-{index}") for index in range(101)],
        )
    assert device.device_token not in str(too_many.value)
    assert await KuaiiotTagSnapshot.all().count() == 0
    assert await EquipmentStatusMonitor.filter(equipment_uuid=equipment.uuid).count() == 1

    with pytest.raises(ValidationError):
        await EdgeConfigService.ingest_batch(device.device_token, [])
    assert await KuaiiotTagSnapshot.all().count() == 0

    first = await EdgeConfigService.ingest_batch(
        device.device_token,
        [IngestBody(tags={"temp": "21.5", "run": "运行中"}, idempotency_key="buf-001")],
    )
    second = await EdgeConfigService.ingest_batch(
        device.device_token,
        [IngestBody(tags={"temp": "99", "run": "待机"}, idempotency_key="buf-001")],
    )
    assert first == {"count": 1}
    assert second == {"count": 1}
    snapshots = await KuaiiotTagSnapshot.filter(device_id=device.id, tag_key="temp")
    assert len(snapshots) == 1
    assert snapshots[0].value_number == Decimal("21.5")
    monitors = await EquipmentStatusMonitor.filter(equipment_uuid=equipment.uuid, data_source="sensor").order_by("id")
    assert len(monitors) == 2
    assert monitors[1].status == "故障"
    assert monitors[1].temperature == Decimal("21.50")
