"""评审缺陷回归：token 一次性、改绑、按设备冷却、事件上限去重、指令闭环。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError as RequestValidationError

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaizhizao.models.equipment_status_monitor import EquipmentStatusMonitor
from apps.kuaiiot.api.router import router
from apps.kuaiiot.models.alert import KuaiiotAlert
from apps.kuaiiot.models.command import KuaiiotDeviceCommand
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.group import KuaiiotDeviceGroup
from apps.kuaiiot.models.message_log import KuaiiotMessageLog
from apps.kuaiiot.models.product import KuaiiotProduct
from apps.kuaiiot.schemas.control import (
    ConnectionCreate,
    DeviceCreate,
    DeviceOut,
    DeviceTokenOut,
    DeviceUpdate,
    TagCreate,
)
from apps.kuaiiot.schemas.ingest import IngestBody
from apps.kuaiiot.schemas.prefill import AlertRuleCreate
from apps.kuaiiot.schemas.product import (
    ProductCreate,
    ProductEdgeActionIn,
    ProductEventIn,
    ProductFunctionIn,
    ProductFunctionParamIn,
)
from apps.kuaiiot.services import alert_service, control_service, group_service, product_service
from apps.kuaiiot.services.command_service import (
    claim_pending_commands,
    submit_command_result,
    timeout_sent_commands,
)
from apps.kuaiiot.services.ingest_service import IngestService, _parse_sampled_at
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import clear_tenant_context, set_current_tenant_id
from infra.exceptions.exceptions import NotFoundError, ValidationError


def _route(path: str, method: str):
    for route in router.routes:
        if getattr(route, "path", "") == path and method in getattr(route, "methods", set()):
            return route
    raise AssertionError(f"路由未挂载 {method} {path}")


async def _device(suffix: str, equipment_uuid: str | None = None) -> KuaiiotDevice:
    connection = await control_service.create_connection(
        1,
        ConnectionCreate(code=f"conn-{suffix}", name="线边", connection_type="http"),
    )
    return await control_service.create_device(
        1,
        DeviceCreate(
            connection_id=connection.id,
            external_device_id=f"ext-{suffix}",
            code=f"dev-{suffix}",
            name=f"采集{suffix}",
            equipment_uuid=equipment_uuid,
        ),
    )


def test_device_token_only_returned_on_create_and_rotate():
    assert _route("/registry/devices", "POST").response_model is DeviceTokenOut
    assert _route("/registry/devices/{device_id}/rotate-token", "POST").response_model is DeviceTokenOut
    assert _route("/registry/devices/{device_id}", "PUT").response_model is DeviceOut
    assert _route("/registry/devices", "GET").response_model == list[DeviceOut]


@pytest.mark.asyncio
async def test_token_out_schema_carries_token_once(db):
    set_current_tenant_id(1)
    device = await _device("token")
    dumped = DeviceTokenOut.model_validate(device).model_dump()
    assert dumped["device_token"] == device.device_token
    assert "device_token" not in DeviceOut.model_validate(device).model_dump()

    previous = device.device_token
    rotated = await control_service.rotate_device_token(1, device.id)
    rotated_dump = DeviceTokenOut.model_validate(rotated).model_dump()
    assert rotated_dump["device_token"] == rotated.device_token != previous
    listed = await control_service.list_devices(1)
    assert all("device_token" not in DeviceOut.model_validate(row).model_dump() for row in listed)


@pytest.mark.asyncio
async def test_update_device_rebind_clear_and_foreign_rejects(db):
    set_current_tenant_id(1)
    device = await _device("upd")
    first = await Equipment.create(tenant_id=1, code="EQ-U1", name="一号")
    second = await Equipment.create(tenant_id=1, code="EQ-U2", name="二号")
    foreign_equipment = await Equipment.create(tenant_id=2, code="EQ-UF", name="外租户")
    foreign_group = await KuaiiotDeviceGroup.create(tenant_id=2, code="g-foreign", name="外分组")
    foreign_product = await KuaiiotProduct.create(tenant_id=2, code="p-foreign", name="外产品")
    group = await group_service.create_group(1, code="g-own", name="本组")
    product = await product_service.create_product(1, ProductCreate(code="p-own", name="本产品"))

    missing = await KuaiiotDeviceGroup.filter(tenant_id=1).count() + 10**6
    with pytest.raises(NotFoundError):
        await control_service.update_device(1, 10**8, DeviceUpdate(name="不存在"))

    with pytest.raises(ValidationError, match="不属于当前租户"):
        await control_service.update_device(1, device.id, DeviceUpdate(equipment_uuid=foreign_equipment.uuid))
    with pytest.raises(ValidationError, match="不属于当前租户"):
        await control_service.update_device(1, device.id, DeviceUpdate(group_id=foreign_group.id))
    with pytest.raises(ValidationError, match="不属于当前租户"):
        await control_service.update_device(1, device.id, DeviceUpdate(product_id=foreign_product.id))
    with pytest.raises(ValidationError, match="不属于当前租户"):
        await control_service.update_device(1, device.id, DeviceUpdate(group_id=missing))

    updated = await control_service.update_device(
        1,
        device.id,
        DeviceUpdate(
            name="新名字",
            equipment_uuid=first.uuid,
            group_id=group.id,
            product_id=product.id,
            remark="备注",
        ),
    )
    assert updated.name == "新名字"
    assert updated.equipment_uuid == first.uuid
    assert updated.group_id == group.id
    assert updated.product_id == product.id
    assert updated.remark == "备注"

    rebound = await control_service.update_device(1, device.id, DeviceUpdate(equipment_uuid=second.uuid))
    assert rebound.equipment_uuid == second.uuid
    assert rebound.group_id == group.id

    cleared = await control_service.update_device(1, device.id, DeviceUpdate(clear_equipment=True))
    assert cleared.equipment_uuid is None

    unbound = await control_service.update_device(1, device.id, DeviceUpdate(equipment_uuid=first.uuid))
    assert unbound.equipment_uuid == first.uuid
    emptied = await control_service.update_device(1, device.id, DeviceUpdate(equipment_uuid=""))
    assert emptied.equipment_uuid is None

    untouched = await control_service.update_device(1, device.id, DeviceUpdate(group_id=None))
    assert untouched.group_id is None
    assert untouched.name == "新名字"


@pytest.mark.asyncio
async def test_monitor_row_defaults_online_and_numeric_range_rejected(db):
    set_current_tenant_id(1)
    equipment = await Equipment.create(tenant_id=1, code="EQ-ON", name="在线机床")
    device = await _device("on", equipment.uuid)
    await control_service.create_tag(
        1, device.id, TagCreate(tag_key="temp", name="温度", value_type="number", map_target="temperature")
    )
    result = await IngestService.ingest(device.device_token, IngestBody(tags={"temp": "1"}))
    assert result["monitor_written"] is True
    monitor = await EquipmentStatusMonitor.get(equipment_uuid=equipment.uuid, data_source="sensor")
    assert monitor.is_online is True

    for bad in ("NaN", "inf", "1e16", -10**16):
        with pytest.raises(ValidationError):
            await IngestService.ingest(device.device_token, IngestBody(tags={"temp": bad}))
    assert await KuaiiotAlert.all().count() == 0


def test_parse_sampled_at_naive_is_utc():
    now = resolve_business_datetime()
    naive = _parse_sampled_at("2024-05-01T12:00:00", now)
    assert naive == datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)
    aware = _parse_sampled_at("2024-05-01T12:00:00+08:00", now)
    assert aware == datetime(2024, 5, 1, 4, 0, tzinfo=timezone.utc)
    assert _parse_sampled_at("2024-05-01T12:00:00Z", now) == naive
    assert _parse_sampled_at(None, now) == now


def test_ingest_body_caps_events_and_tags():
    with pytest.raises(RequestValidationError):
        IngestBody(events=[{"event_key": "e"}] * 51)
    with pytest.raises(RequestValidationError):
        IngestBody(tags={f"k{i}": 1 for i in range(201)})
    ok = IngestBody(events=[{"event_key": "e"}] * 50, tags={f"k{i}": 1 for i in range(200)})
    assert len(ok.events) == 50 and len(ok.tags) == 200


@pytest.mark.asyncio
async def test_events_dedupe_and_message_secret_mask(db):
    set_current_tenant_id(1)
    product = await product_service.create_product(
        1,
        ProductCreate(
            code="evt-mask",
            name="事件产品",
            events=[ProductEventIn(event_key="fault", name="故障", severity="critical")],
        ),
    )
    device = await _device("mask")
    device.product_id = product.id
    await device.save(update_fields=["product_id", "updated_at"])

    await IngestService.ingest(
        device.device_token,
        IngestBody(
            events=[
                {"event_key": "fault", "message": "停机 password=abc123 token=tok99"},
                {"event_key": "fault", "message": "重复不应再写"},
            ]
        ),
    )
    alerts = await KuaiiotAlert.filter(device_id=device.id, tag_key="fault")
    assert len(alerts) == 1
    assert "abc123" not in alerts[0].message
    assert "tok99" not in alerts[0].message
    assert "password=***" in alerts[0].message
    assert "token=***" in alerts[0].message
    event_logs = await KuaiiotMessageLog.filter(device_id=device.id, msg_type="event")
    assert len(event_logs) == 1
    assert "abc123" not in json.dumps(event_logs[0].payload, ensure_ascii=False)


@pytest.mark.asyncio
async def test_cooldown_is_scoped_per_device(db):
    set_current_tenant_id(1)
    rule = await alert_service.create_rule(
        1,
        AlertRuleCreate(
            code="wild-hot",
            name="通配过热",
            tag_key="temp",
            operator="gt",
            threshold_number=Decimal("10"),
            cooldown_seconds=300,
        ),
    )
    first = await _device("cool-a")
    second = await _device("cool-b")
    for device in (first, second):
        await control_service.create_tag(
            1, device.id, TagCreate(tag_key="temp", name="温度", value_type="number", map_target="temperature")
        )
    await IngestService.ingest(first.device_token, IngestBody(tags={"temp": 50}))
    await IngestService.ingest(second.device_token, IngestBody(tags={"temp": 50}))
    await IngestService.ingest(first.device_token, IngestBody(tags={"temp": 60}))
    alerts = await KuaiiotAlert.filter(rule_id=rule.id).order_by("id")
    assert len(alerts) == 2
    assert {row.device_id for row in alerts} == {first.id, second.id}


@pytest.mark.asyncio
async def test_expired_pending_not_claimed_and_times_out(db):
    set_current_tenant_id(1)
    product = await product_service.create_product(
        1,
        ProductCreate(
            code="cmd-expire",
            name="指令产品",
            functions=[
                ProductFunctionIn(
                    function_key="set_speed",
                    name="设置转速",
                    params=[ProductFunctionParamIn(key="value", name="转速", required=True)],
                    edge_action=ProductEdgeActionIn(type="modbus_write", address=100, data_type="uint16"),
                )
            ],
        ),
    )
    device = await _device("expired")
    device.product_id = product.id
    await device.save(update_fields=["product_id", "updated_at"])
    now = resolve_business_datetime()
    expired_pending = await KuaiiotDeviceCommand.create(
        tenant_id=1,
        device_id=device.id,
        function_key="set_speed",
        params={"value": 1},
        dispatch_channel="edge_heartbeat",
        status="pending",
        expires_at=now - timedelta(seconds=5),
    )
    alive = await KuaiiotDeviceCommand.create(
        tenant_id=1,
        device_id=device.id,
        function_key="set_speed",
        params={"value": 2},
        dispatch_channel="edge_heartbeat",
        status="pending",
        expires_at=now + timedelta(minutes=5),
    )
    claimed = await claim_pending_commands(1, device.id)
    assert [item["command_uuid"] for item in claimed] == [alive.uuid]
    await expired_pending.refresh_from_db()
    assert expired_pending.status == "pending"

    clear_tenant_context()
    count = await timeout_sent_commands()
    assert count == 1
    set_current_tenant_id(1)
    await expired_pending.refresh_from_db()
    await alive.refresh_from_db()
    assert expired_pending.status == "timeout"
    assert expired_pending.completed_at is not None
    assert alive.status == "sent"


@pytest.mark.asyncio
async def test_submit_result_after_timeout_does_not_overwrite(db):
    set_current_tenant_id(1)
    device = await _device("cas")
    command = await KuaiiotDeviceCommand.create(
        tenant_id=1,
        device_id=device.id,
        function_key="set_speed",
        params={"value": 1},
        dispatch_channel="edge_heartbeat",
        status="sent",
        expires_at=resolve_business_datetime() - timedelta(seconds=5),
    )
    logs_before = await KuaiiotMessageLog.filter(device_id=device.id).count()
    clear_tenant_context()
    assert await timeout_sent_commands() == 1
    reply = await submit_command_result(
        device.device_token,
        command_uuid=command.uuid,
        success=True,
        result={"value": 1},
    )
    assert reply == {"status": "timeout"}
    set_current_tenant_id(1)
    await command.refresh_from_db()
    assert command.status == "timeout"
    assert command.result is None
    assert await KuaiiotMessageLog.filter(device_id=device.id).count() == logs_before + 1


@pytest.mark.asyncio
async def test_create_rule_rejects_dead_or_invalid_rules(db):
    set_current_tenant_id(1)
    foreign_equipment = await Equipment.create(tenant_id=2, code="EQ-RF", name="外租户")
    with pytest.raises(ValidationError, match="严重级别"):
        await alert_service.create_rule(
            1,
            AlertRuleCreate(
                code="bad-sev",
                name="非法级别",
                tag_key="temp",
                operator="gt",
                threshold_number=Decimal("1"),
                severity="fatal",
            ),
        )
    with pytest.raises(ValidationError, match="至少填写其一"):
        await alert_service.create_rule(
            1,
            AlertRuleCreate(
                code="dead",
                name="死规则",
                tag_key="temp",
                operator="gt",
            ),
        )
    with pytest.raises(ValidationError, match="不属于当前租户"):
        await alert_service.create_rule(
            1,
            AlertRuleCreate(
                code="foreign",
                name="外租户设备",
                tag_key="temp",
                operator="gt",
                threshold_number=Decimal("1"),
                equipment_uuid=foreign_equipment.uuid,
            ),
        )
    assert await KuaiiotAlert.all().count() == 0
