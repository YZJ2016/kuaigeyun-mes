"""入站状态护栏：未知值保持未知，不可覆盖的设备态不改台账。"""

from datetime import timedelta
from decimal import Decimal

import pytest

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaizhizao.models.equipment_fault import EquipmentFault, EquipmentRepair
from apps.kuaizhizao.models.equipment_status_monitor import EquipmentStatusMonitor
from apps.kuaiiot.schemas.control import ConnectionCreate, DeviceCreate, TagCreate
from apps.kuaiiot.schemas.ingest import IngestBody
from apps.kuaiiot.services import control_service
from apps.kuaiiot.services.ingest_service import IngestService
from apps.kuaiiot.services.status_mapper import normalize_equipment_status
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import set_current_tenant_id


def test_unknown_and_aliases_remain_unknown():
    assert normalize_equipment_status("运行中") == "运行中"
    assert normalize_equipment_status("待机") == "待机"
    assert normalize_equipment_status("running") == "未知"
    assert normalize_equipment_status("idle") == "未知"
    assert normalize_equipment_status("fault") == "未知"
    assert normalize_equipment_status("unknown_state") == "未知"
    assert normalize_equipment_status("") == "未知"
    assert normalize_equipment_status(None) == "未知"


async def _device(equipment_uuid: str, suffix: str):
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
    await control_service.create_tag(
        1,
        device.id,
        TagCreate(tag_key="online", name="在线", value_type="boolean", map_target="is_online"),
    )
    return device


async def _previous_sensor(equipment: Equipment, *, status: str, is_online: bool):
    row = await EquipmentStatusMonitor.create(
        tenant_id=1,
        equipment_id=equipment.id,
        equipment_uuid=equipment.uuid,
        equipment_code=equipment.code,
        equipment_name=equipment.name,
        status=status,
        is_online=is_online,
        data_source="sensor",
        monitored_at=resolve_business_datetime() - timedelta(seconds=30),
    )
    await EquipmentStatusMonitor.filter(id=row.id).update(
        created_at=resolve_business_datetime() - timedelta(seconds=30)
    )
    return row


@pytest.mark.asyncio
async def test_guard_copies_previous_sensor_status_and_online(db):
    set_current_tenant_id(1)
    equipment = await Equipment.create(tenant_id=1, code="EQ-HOLD", name="停用机床", status="停用")
    await _previous_sensor(equipment, status="故障", is_online=True)
    device = await _device(equipment.uuid, "copy")
    result = await IngestService.ingest(
        device.device_token,
        IngestBody(tags={"temp": "36.5", "run": "运行中", "online": False}),
    )
    assert result["monitor_written"] is True
    rows = await EquipmentStatusMonitor.filter(equipment_uuid=equipment.uuid, data_source="sensor").order_by("id")
    assert len(rows) == 2
    assert rows[1].status == "故障"
    assert rows[1].is_online is True
    assert rows[1].temperature == Decimal("36.50")
    await equipment.refresh_from_db()
    assert equipment.status == "停用"


@pytest.mark.asyncio
async def test_guard_without_previous_sensor_does_not_insert(db):
    set_current_tenant_id(1)
    equipment = await Equipment.create(tenant_id=1, code="EQ-NEW", name="报废机床", status="报废")
    device = await _device(equipment.uuid, "none")
    result = await IngestService.ingest(
        device.device_token,
        IngestBody(tags={"temp": "10", "run": "运行中", "online": True}),
    )
    assert result["monitor_written"] is False
    assert await EquipmentStatusMonitor.filter(equipment_uuid=equipment.uuid).count() == 0
    await equipment.refresh_from_db()
    assert equipment.status == "报废"


@pytest.mark.asyncio
async def test_open_fault_blocks_and_repaired_fault_does_not(db):
    set_current_tenant_id(1)
    equipment = await Equipment.create(tenant_id=1, code="EQ-FAULT", name="故障机床")
    await _previous_sensor(equipment, status="待机", is_online=True)
    device = await _device(equipment.uuid, "fault")
    now = resolve_business_datetime()
    fault = await EquipmentFault.create(
        tenant_id=1,
        fault_no="F-1",
        equipment_id=equipment.id,
        equipment_uuid=equipment.uuid,
        equipment_name=equipment.name,
        fault_date=now,
        fault_type="机械故障",
        fault_description="异响",
        fault_level="一般",
        status="待处理",
    )
    blocked = await IngestService.ingest(device.device_token, IngestBody(tags={"temp": "1", "run": "运行中"}))
    assert blocked["monitor_written"] is True
    latest = await EquipmentStatusMonitor.filter(data_source="sensor").order_by("-id").first()
    assert latest is not None
    assert latest.status == "待机"
    await equipment.refresh_from_db()
    assert equipment.status == "正常"

    fault.status = "已修复"
    await fault.save(update_fields=["status", "updated_at"])
    await EquipmentStatusMonitor.filter(data_source="sensor").update(
        created_at=resolve_business_datetime() - timedelta(seconds=30)
    )
    opened = await IngestService.ingest(device.device_token, IngestBody(tags={"temp": "2", "run": "运行中"}))
    assert opened["monitor_written"] is True
    written = await EquipmentStatusMonitor.filter(data_source="sensor").order_by("-id").first()
    assert written is not None
    assert written.status == "运行中"
    await equipment.refresh_from_db()
    assert equipment.status == "正常"


@pytest.mark.asyncio
async def test_repair_in_progress_blocks_writeback(db):
    set_current_tenant_id(1)
    equipment = await Equipment.create(tenant_id=1, code="EQ-REPAIR", name="维修机床")
    await _previous_sensor(equipment, status="维修中", is_online=False)
    device = await _device(equipment.uuid, "repair")
    await EquipmentRepair.create(
        tenant_id=1,
        repair_no="R-1",
        equipment_id=equipment.id,
        equipment_uuid=equipment.uuid,
        equipment_name=equipment.name,
        repair_date=resolve_business_datetime(),
        repair_type="现场维修",
        repair_description="更换轴承",
        status="进行中",
    )
    result = await IngestService.ingest(
        device.device_token,
        IngestBody(tags={"temp": "3", "run": "运行中", "online": True}),
    )
    assert result["monitor_written"] is True
    latest = await EquipmentStatusMonitor.filter(data_source="sensor").order_by("-id").first()
    assert latest is not None
    assert latest.status == "维修中"
    assert latest.is_online is False
    await equipment.refresh_from_db()
    assert equipment.status == "正常"


@pytest.mark.asyncio
async def test_unknown_alias_and_missing_status_preserve_unknown(db):
    set_current_tenant_id(1)
    equipment = await Equipment.create(tenant_id=1, code="EQ-NORM", name="普通机床")
    device = await _device(equipment.uuid, "alias")
    aliased = await IngestService.ingest(device.device_token, IngestBody(tags={"temp": "1", "run": "running"}))
    assert aliased["monitor_written"] is True
    row = await EquipmentStatusMonitor.get(data_source="sensor")
    assert row.status == "未知"

    await EquipmentStatusMonitor.filter(id=row.id).update(
        created_at=resolve_business_datetime() - timedelta(seconds=30)
    )
    bare = await _device(equipment.uuid, "bare")
    missing = await IngestService.ingest(bare.device_token, IngestBody(tags={"temp": "8"}))
    assert missing["monitor_written"] is True
    latest = await EquipmentStatusMonitor.filter(data_source="sensor").order_by("-id").first()
    assert latest is not None
    assert latest.status == "未知"
    assert latest.status != "运行中"
