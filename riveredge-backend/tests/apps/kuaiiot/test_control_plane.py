"""spec 150：控制面登记与最新快照读取。"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError as RequestValidationError

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaiiot.api.control import api_list_snapshots
from apps.kuaiiot.api.router import router
from apps.kuaiiot.models.connection import KuaiiotConnection
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.schemas.control import ConnectionCreate, DeviceCreate, DeviceOut, TagCreate
from apps.kuaiiot.schemas.ingest import IngestBody
from apps.kuaiiot.services import control_service
from apps.kuaiiot.services.ingest_service import IngestService
from infra.domain.tenant_context import TenantContextError, clear_tenant_context, set_current_tenant_id
from infra.exceptions.exceptions import ValidationError


def test_ingest_route_is_mounted_without_user_tenant():
    paths = {getattr(route, "path", "") for route in router.routes}
    assert "/ingest/{device_token}" in paths
    assert "/registry/devices/{device_id}/snapshots" in paths
    assert "device_token" not in DeviceOut.model_fields


@pytest.mark.asyncio
async def test_missing_external_device_id_is_rejected(db):
    set_current_tenant_id(1)
    with pytest.raises(RequestValidationError):
        DeviceCreate(code="d1", name="设备")
    with pytest.raises(ValidationError, match="外部设备标识"):
        await control_service.create_device(
            1,
            DeviceCreate(external_device_id="  ", code="d1", name="设备"),
        )
    assert await KuaiiotDevice.all().count() == 0


@pytest.mark.asyncio
async def test_no_tenant_context_rejects_before_query(db, monkeypatch):
    clear_tenant_context()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("无租户上下文不应查询数采表")

    monkeypatch.setattr(KuaiiotConnection, "filter", forbidden)
    monkeypatch.setattr(KuaiiotConnection, "create", forbidden)
    with pytest.raises(TenantContextError):
        await control_service.create_connection(
            1,
            ConnectionCreate(code="c1", name="连接", connection_type="http"),
        )


@pytest.mark.asyncio
async def test_register_bind_and_read_snapshots_through_api(db):
    set_current_tenant_id(1)
    equipment = await Equipment.create(tenant_id=1, code="EQ-REG", name="登记机床")
    connection = await control_service.create_connection(
        1,
        ConnectionCreate(code="line", name="一线", connection_type="http"),
    )
    device = await control_service.create_device(
        1,
        DeviceCreate(
            connection_id=connection.id,
            external_device_id="plc-01",
            code="plc-01",
            name="一线 PLC",
            equipment_uuid=equipment.uuid,
        ),
    )
    assert device.equipment_uuid == equipment.uuid
    assert device.external_device_id == "plc-01"
    dumped = DeviceOut.model_validate(device).model_dump()
    assert "device_token" not in dumped

    previous = device.device_token
    rotated = await control_service.rotate_device_token(1, device.id)
    assert rotated.device_token != previous
    assert "device_token" not in DeviceOut.model_validate(rotated).model_dump()

    await control_service.create_tag(
        1,
        device.id,
        TagCreate(tag_key="temp", name="温度", value_type="number", map_target="temperature"),
    )
    await IngestService.ingest(rotated.device_token, IngestBody(tags={"temp": "12.5"}))
    rows = await api_list_snapshots(device.id, tenant_id=1)
    assert len(rows) == 1
    assert rows[0].tag_key == "temp"
    assert rows[0].value_number == Decimal("12.5")


@pytest.mark.asyncio
async def test_bind_rejects_equipment_from_another_tenant(db):
    set_current_tenant_id(2)
    foreign = await Equipment.create(tenant_id=2, code="EQ-OTHER", name="外租户")
    set_current_tenant_id(1)
    with pytest.raises(ValidationError, match="不属于当前租户"):
        await control_service.create_device(
            1,
            DeviceCreate(
                external_device_id="ext",
                code="d-foreign",
                name="设备",
                equipment_uuid=foreign.uuid,
            ),
        )
    assert await KuaiiotDevice.all().count() == 0
