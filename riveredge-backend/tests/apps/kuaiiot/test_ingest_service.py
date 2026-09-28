"""spec 150：入站认设备、幂等、快照与按星制造设备 5 秒节流。"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaizhizao.models.equipment_status_monitor import EquipmentStatusHistory, EquipmentStatusMonitor
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.tag import KuaiiotTagHistory, KuaiiotTagSnapshot
from apps.kuaiiot.schemas.control import ConnectionCreate, DeviceCreate, TagCreate
from apps.kuaiiot.schemas.ingest import IngestBody
from apps.kuaiiot.services import control_service
from apps.kuaiiot.services.ingest_service import IngestService
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import set_current_tenant_id
from infra.exceptions.exceptions import AuthenticationError, ValidationError

TOKEN = "ingest-credential-not-for-logs"


async def _register_pair(equipment_uuid: str | None, suffix: str) -> KuaiiotDevice:
    connection = await control_service.create_connection(
        1,
        ConnectionCreate(code=f"conn-{suffix}", name="线边", connection_type="http"),
    )
    device = await control_service.create_device(
        1,
        DeviceCreate(
            connection_id=connection.id,
            external_device_id=f"ext-{suffix}",
            code=f"dev-{suffix}",
            name=f"采集{suffix}",
            equipment_uuid=equipment_uuid,
        ),
    )
    await control_service.create_tag(
        1,
        device.id,
        TagCreate(tag_key="temp", name="温度", value_type="number", map_target="temperature"),
    )
    await control_service.create_tag(
        1,
        device.id,
        TagCreate(tag_key="run", name="状态", value_type="text", map_target="status"),
    )
    return device


@pytest.mark.asyncio
async def test_token_miss_and_multi_match_write_nothing(db):
    set_current_tenant_id(1)
    device = await _register_pair(None, "a")
    other = await _register_pair(None, "b")
    other.device_token = device.device_token
    await other.save(update_fields=["device_token", "updated_at"])

    with pytest.raises(AuthenticationError) as missing:
        await IngestService.ingest(TOKEN, IngestBody(tags={"temp": 1}))
    assert TOKEN not in str(missing.value)

    with pytest.raises(AuthenticationError) as collided:
        await IngestService.ingest(device.device_token, IngestBody(tags={"temp": 1}))
    assert device.device_token not in str(collided.value)

    assert await KuaiiotTagSnapshot.all().count() == 0
    assert await EquipmentStatusMonitor.all().count() == 0
    assert await KuaiiotTagHistory.all().count() == 0
    await device.refresh_from_db()
    assert device.is_online is False
    assert device.last_seen_at is None


@pytest.mark.asyncio
async def test_ingest_snapshot_idempotency_and_history_stays_empty(db):
    set_current_tenant_id(1)
    equipment = await Equipment.create(tenant_id=1, code="EQ-1", name="机床")
    status_before = equipment.status
    device = await _register_pair(equipment.uuid, "ok")
    body = IngestBody(
        tags={"temp": "25.5", "run": "运行中", "ghost": 9},
        idempotency_key="same-key",
    )
    first = await IngestService.ingest(device.device_token, body)
    second = await IngestService.ingest(
        device.device_token,
        IngestBody(tags={"temp": "99", "run": "待机"}, idempotency_key="same-key"),
    )
    assert first == second
    assert first["monitor_written"] is True
    assert first["snapshot_keys"] == ["run", "temp"]
    assert device.device_token not in str(first)

    snapshots = await KuaiiotTagSnapshot.filter(device_id=device.id).order_by("tag_key")
    assert [row.tag_key for row in snapshots] == ["run", "temp"]
    assert snapshots[1].value_number == Decimal("25.5")
    monitors = await EquipmentStatusMonitor.filter(equipment_uuid=equipment.uuid)
    assert len(monitors) == 1
    assert monitors[0].data_source == "sensor"
    assert monitors[0].status == "运行中"
    assert monitors[0].temperature == Decimal("25.50")
    assert monitors[0].equipment_id == equipment.id
    assert monitors[0].equipment_code == equipment.code
    assert await KuaiiotTagHistory.all().count() == 0
    await equipment.refresh_from_db()
    assert equipment.status == status_before
    assert await EquipmentStatusHistory.filter(equipment_uuid=equipment.uuid).count() == 0
    await device.refresh_from_db()
    assert device.is_online is True
    assert device.last_seen_at is not None
    assert device.last_mes_sync_at is None


@pytest.mark.asyncio
async def test_shared_equipment_throttle_and_unbound_device(db):
    set_current_tenant_id(1)
    equipment = await Equipment.create(tenant_id=1, code="EQ-2", name="共用机床")
    first = await _register_pair(equipment.uuid, "one")
    second = await _register_pair(equipment.uuid, "two")
    unbound = await _register_pair(None, "free")

    opened = await IngestService.ingest(first.device_token, IngestBody(tags={"temp": 1, "run": "运行中"}))
    shared = await IngestService.ingest(second.device_token, IngestBody(tags={"temp": 2, "run": "待机"}))
    assert opened["monitor_written"] is True
    assert shared["monitor_written"] is False
    assert await EquipmentStatusMonitor.filter(data_source="sensor").count() == 1
    second_snap = await KuaiiotTagSnapshot.get(device_id=second.id, tag_key="temp")
    assert second_snap.value_number == Decimal("2")

    recent = await EquipmentStatusMonitor.filter(data_source="sensor").first()
    assert recent is not None
    await EquipmentStatusMonitor.filter(id=recent.id).update(
        created_at=resolve_business_datetime() - timedelta(seconds=4)
    )
    held = await IngestService.ingest(second.device_token, IngestBody(tags={"temp": 3, "run": "运行中"}))
    assert held["monitor_written"] is False
    assert await EquipmentStatusMonitor.filter(data_source="sensor").count() == 1

    await EquipmentStatusMonitor.filter(id=recent.id).update(
        created_at=resolve_business_datetime() - timedelta(seconds=6)
    )
    released = await IngestService.ingest(first.device_token, IngestBody(tags={"temp": 4, "run": "运行中"}))
    assert released["monitor_written"] is True
    assert await EquipmentStatusMonitor.filter(data_source="sensor").count() == 2

    free = await IngestService.ingest(unbound.device_token, IngestBody(tags={"temp": 8, "run": "运行中"}))
    assert free["monitor_written"] is False
    assert await KuaiiotTagSnapshot.filter(device_id=unbound.id).count() == 2
    assert await EquipmentStatusMonitor.filter(data_source="sensor").count() == 2
    await first.refresh_from_db()
    await second.refresh_from_db()
    assert first.last_mes_sync_at is None
    assert second.last_mes_sync_at is None
    await equipment.refresh_from_db()
    assert equipment.status == "正常"
    assert await EquipmentStatusHistory.all().count() == 0


@pytest.mark.asyncio
async def test_foreign_equipment_uuid_writes_nothing(db):
    set_current_tenant_id(2)
    foreign = await Equipment.create(tenant_id=2, code="EQ-X", name="其他租户")
    set_current_tenant_id(1)
    device = await _register_pair(None, "stale")
    device.equipment_uuid = foreign.uuid
    await device.save(update_fields=["equipment_uuid", "updated_at"])

    with pytest.raises(ValidationError, match="不属于当前租户"):
        await IngestService.ingest(device.device_token, IngestBody(tags={"temp": 1, "run": "运行中"}))
    assert await KuaiiotTagSnapshot.all().count() == 0
    assert await EquipmentStatusMonitor.all().count() == 0
    await device.refresh_from_db()
    assert device.is_online is False


@pytest.mark.asyncio
async def test_missing_timestamp_uses_server_time(db):
    set_current_tenant_id(1)
    device = await _register_pair(None, "clock")
    before = resolve_business_datetime()
    await IngestService.ingest(device.device_token, IngestBody(tags={"temp": 1}))
    snapshot = await KuaiiotTagSnapshot.get(device_id=device.id, tag_key="temp")
    assert snapshot.sampled_at >= before
