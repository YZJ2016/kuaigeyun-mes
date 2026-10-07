"""现有 control_service 设备绑定：租户隔离与共享设备传感器。"""
import pytest
from apps.kuaizhizao.models.equipment import Equipment
from infra.domain.tenant_context import set_current_tenant_id
from infra.exceptions.exceptions import ValidationError
from tests.apps.kuaiiot.test_ingest_service import _register_pair


@pytest.mark.asyncio
async def test_binding_accepts_equipment_in_same_tenant(db):
    set_current_tenant_id(1)
    equipment = await Equipment.create(tenant_id=1, code='BIND', name='绑定设备')
    device = await _register_pair(equipment.uuid, 'binding')
    assert device.equipment_uuid == equipment.uuid


@pytest.mark.asyncio
async def test_binding_rejects_other_tenant_equipment(db):
    set_current_tenant_id(2)
    equipment = await Equipment.create(tenant_id=2, code='FOREIGN', name='其他租户')
    set_current_tenant_id(1)
    with pytest.raises(ValidationError):
        await _register_pair(equipment.uuid, 'foreign-binding')


@pytest.mark.asyncio
async def test_multiple_sensor_devices_can_share_equipment(db):
    set_current_tenant_id(1)
    equipment = await Equipment.create(tenant_id=1, code='SHARED', name='多传感器设备')
    first = await _register_pair(equipment.uuid, 'sensor-first')
    second = await _register_pair(equipment.uuid, 'sensor-second')
    assert first.id != second.id
    assert first.equipment_uuid == second.equipment_uuid == equipment.uuid
