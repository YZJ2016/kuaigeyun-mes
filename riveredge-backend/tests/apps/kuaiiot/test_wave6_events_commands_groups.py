"""spec 154：产品事件与指令、入站事件告警、心跳下发、分组与消息追踪。"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaiiot.models.alert import KuaiiotAlert
from apps.kuaiiot.models.command import KuaiiotDeviceCommand
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.message_log import KuaiiotMessageLog
from apps.kuaiiot.models.tag import KuaiiotTagHistory
from apps.kuaiiot.schemas.control import ConnectionCreate, DeviceCreate, TagCreate
from apps.kuaiiot.schemas.ingest import IngestBody
from apps.kuaiiot.schemas.product import (
    ProductCreate,
    ProductEdgeActionIn,
    ProductEventIn,
    ProductFunctionIn,
    ProductFunctionParamIn,
    ProductTagIn,
    ProductUpdate,
)
from apps.kuaiiot.services import control_service, group_service, product_service
from apps.kuaiiot.services.command_service import (
    claim_pending_commands,
    create_command,
    list_commands,
    submit_command_result,
)
from apps.kuaiiot.services.edge_config_service import EdgeConfigService
from apps.kuaiiot.services.ingest_service import IngestService
from apps.kuaiiot.services.message_log_service import MessageLogService
from apps.kuaiiot.workflows.functions.command_timeout_workflow import run_kuaiiot_command_timeout_check
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import TenantContextError, clear_tenant_context, set_current_tenant_id
from infra.exceptions.exceptions import NotFoundError, ValidationError


def _tag() -> ProductTagIn:
    return ProductTagIn(tag_key="temp", name="温度", value_type="number", map_target="temperature")


def _function() -> ProductFunctionIn:
    return ProductFunctionIn(
        function_key="set_speed",
        name="设置转速",
        timeout_seconds=30,
        params=[ProductFunctionParamIn(key="value", name="转速", value_type="number", required=True)],
        edge_action=ProductEdgeActionIn(
            type="modbus_write",
            address=100,
            data_type="uint16",
            param_key="value",
            scale=1,
        ),
    )


def _modbus() -> dict:
    return {
        "host": "127.0.0.1",
        "port": 502,
        "unit_id": 1,
        "registers": [{"tag_key": "temp", "address": 0, "data_type": "float32"}],
        "publish": {"mode": "http_ingest"},
    }


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


@pytest.mark.asyncio
async def test_product_saves_events_and_functions(db):
    set_current_tenant_id(1)
    created = await product_service.create_product(
        1,
        ProductCreate(
            code="press",
            name="压力机",
            tags=[_tag()],
            events=[
                ProductEventIn(event_key="fault", name="故障", severity="critical", message="设备故障"),
                ProductEventIn(event_key="mold_change", name="换模", severity="info"),
            ],
            functions=[_function()],
        ),
    )
    assert created.events[0]["event_key"] == "fault"
    assert created.events[0]["severity"] == "critical"
    assert created.events[1]["event_key"] == "mold_change"
    assert created.functions[0]["function_key"] == "set_speed"
    assert created.functions[0]["edge_action"]["address"] == 100

    updated = await product_service.update_product(
        1,
        created.id,
        ProductUpdate(events=[ProductEventIn(event_key="fault", name="故障", level="warning")]),
    )
    assert updated.events[0]["severity"] == "warning"
    assert updated.functions[0]["function_key"] == "set_speed"

    with pytest.raises(ValidationError, match="event_key 重复"):
        await product_service.update_product(
            1,
            created.id,
            ProductUpdate(
                events=[
                    ProductEventIn(event_key="fault", name="故障", severity="warning"),
                    ProductEventIn(event_key="fault", name="故障2", severity="info"),
                ]
            ),
        )


@pytest.mark.asyncio
async def test_ingest_events_alerts_and_message_rows_omit_secrets(db):
    set_current_tenant_id(1)
    product = await product_service.create_product(
        1,
        ProductCreate(
            code="line",
            name="产线",
            tags=[
                _tag(),
                ProductTagIn(tag_key="run", name="状态", value_type="text", map_target="status"),
            ],
            events=[
                ProductEventIn(event_key="fault", name="故障", severity="critical", message="设备故障"),
                ProductEventIn(event_key="mold_change", name="换模", severity="info"),
                ProductEventIn(event_key="heat", name="过热", severity="warning"),
            ],
            functions=[_function()],
        ),
    )
    equipment = await Equipment.create(tenant_id=1, code="EQ-W6", name="机床")
    status_before = equipment.status
    device = await _device("evt", equipment.uuid)
    device.product_id = product.id
    await device.save(update_fields=["product_id", "updated_at"])
    await control_service.create_tag(
        1, device.id, TagCreate(tag_key="temp", name="温度", value_type="number", map_target="temperature")
    )
    await control_service.create_tag(
        1, device.id, TagCreate(tag_key="run", name="状态", value_type="text", map_target="status")
    )
    influx_token = "influx-token-must-stay-out"
    body = IngestBody(
        tags={"temp": "21.5", "run": "运行中", "device_token": device.device_token},
        events=[
            {"event_key": "not-defined", "severity": "critical", "message": device.device_token},
            {
                "event_key": "fault",
                "message": f"停机 {device.device_token}",
                "influx_token": influx_token,
            },
            {"event_key": "mold_change"},
            {"event_key": "heat", "severity": "info"},
        ],
    )
    clear_tenant_context()
    result = await IngestService.ingest(device.device_token, body)
    assert result["monitor_written"] is True
    assert device.device_token not in str(result)

    set_current_tenant_id(1)
    alerts = await KuaiiotAlert.filter(device_id=device.id).order_by("tag_key")
    assert [row.tag_key for row in alerts] == ["fault", "heat"]
    assert all(row.rule_id is None for row in alerts)
    assert {row.severity for row in alerts} == {"critical", "warning"}
    assert alerts[0].device_id == device.id
    assert device.device_token not in alerts[0].message
    assert await KuaiiotTagHistory.all().count() == 0
    await equipment.refresh_from_db()
    assert equipment.status == status_before

    logs = await KuaiiotMessageLog.filter(device_id=device.id).order_by("id")
    kinds = [row.msg_type for row in logs]
    assert kinds.count("ingest") == 1
    assert kinds.count("event") == 3
    assert "not-defined" not in json.dumps([row.payload for row in logs], ensure_ascii=False)
    assert kinds.count("monitor_writeback") == 1
    for row in logs:
        text = json.dumps(row.payload, ensure_ascii=False)
        assert device.device_token not in text
        assert influx_token not in text
        assert "device_token" not in (row.payload or {})

    again = await IngestService.ingest(
        device.device_token,
        IngestBody(tags={"temp": "99"}, events=[{"event_key": "fault"}], idempotency_key="once"),
    )
    first = await IngestService.ingest(
        device.device_token,
        IngestBody(tags={"temp": "1"}, events=[{"event_key": "fault"}], idempotency_key="once"),
    )
    assert first == again
    set_current_tenant_id(1)
    keyed = await KuaiiotMessageLog.filter(device_id=device.id, msg_type="ingest")
    assert len(keyed) == 2


@pytest.mark.asyncio
async def test_command_heartbeat_receipt_timeout_and_foreign_device(db):
    set_current_tenant_id(1)
    product = await product_service.create_product(
        1,
        ProductCreate(code="cmd", name="指令产品", tags=[_tag()], functions=[_function()]),
    )
    device = await _device("cmd")
    device.product_id = product.id
    await device.save(update_fields=["product_id", "updated_at"])
    other = await _device("other")
    other.product_id = product.id
    await other.save(update_fields=["product_id", "updated_at"])
    await EdgeConfigService.save_config(
        1,
        code="line1",
        name="线边",
        device_id=device.id,
        protocol="modbus_tcp",
        config=_modbus(),
    )

    with pytest.raises(ValidationError, match="function_key"):
        await create_command(1, device.id, function_key="missing", params={"value": 1})
    assert await KuaiiotDeviceCommand.filter(device_id=device.id).count() == 0

    bare = await product_service.create_product(
        1,
        ProductCreate(
            code="bare",
            name="无地址",
            tags=[_tag()],
            functions=[
                ProductFunctionIn(function_key="set_speed", name="设置转速"),
            ],
        ),
    )
    bare_device = await _device("bare")
    bare_device.product_id = bare.id
    await bare_device.save(update_fields=["product_id", "updated_at"])
    with pytest.raises(ValidationError, match="写寄存器地址"):
        await create_command(1, bare_device.id, function_key="set_speed", params={"value": 1})
    assert await KuaiiotDeviceCommand.filter(device_id=bare_device.id).count() == 0
    leftover = await KuaiiotDeviceCommand.create(
        tenant_id=1,
        device_id=bare_device.id,
        function_key="set_speed",
        params={"value": 1},
        dispatch_channel="edge_heartbeat",
        status="pending",
    )
    assert await claim_pending_commands(1, bare_device.id) == []
    await leftover.refresh_from_db()
    assert leftover.status == "pending"

    command = await create_command(1, device.id, function_key="set_speed", params={"value": 80}, user_id=7)
    assert command.status == "pending"
    assert command.dispatch_channel == "edge_heartbeat"
    assert command.expires_at is not None

    clear_tenant_context()
    pulled = await EdgeConfigService.pull_runtime_config(device.device_token, "line1")
    assert pulled["command_result_path"] == (
        f"/api/v1/apps/kuaiiot/edge-runtime/{device.device_token}/command-result"
    )
    heartbeat = await EdgeConfigService.record_heartbeat(
        device.device_token,
        edge_config_code="line1",
        config_version=1,
        agent_version="1.0.0",
        buffer_pending_count=0,
        status="online",
    )
    assert heartbeat["config_changed"] is False
    assert len(heartbeat["pending_commands"]) == 1
    item = heartbeat["pending_commands"][0]
    assert item["command_uuid"] == command.uuid
    assert item["edge_action"]["type"] == "modbus_write"
    assert item["edge_action"]["param_key"] == "value"
    assert item["edge_action"]["address"] == 100
    assert item["edge_action"]["data_type"] == "uint16"
    assert item["edge_action"]["scale"] == 1.0
    assert item["params"]["value"] == 80
    assert device.device_token not in json.dumps(heartbeat["pending_commands"])

    done = await submit_command_result(
        device.device_token,
        command_uuid=command.uuid,
        success=True,
        result={"address": 100, "value": 80},
    )
    assert done["status"] == "success"
    with pytest.raises(NotFoundError):
        await submit_command_result(
            other.device_token,
            command_uuid=command.uuid,
            success=False,
            error_message="nope",
        )
    set_current_tenant_id(1)
    await command.refresh_from_db()
    assert command.status == "success"
    clear_tenant_context()

    set_current_tenant_id(1)
    failed = await create_command(1, device.id, function_key="set_speed", params={"value": 1})
    clear_tenant_context()
    await EdgeConfigService.record_heartbeat(
        device.device_token,
        edge_config_code="line1",
        config_version=1,
        agent_version="1.0.0",
        buffer_pending_count=0,
        status="online",
    )
    failed_body = await submit_command_result(
        device.device_token,
        command_uuid=failed.uuid,
        success=False,
        error_message=f"写失败 {device.device_token}",
    )
    assert failed_body["status"] == "failed"

    set_current_tenant_id(1)
    now = resolve_business_datetime()
    expired = await KuaiiotDeviceCommand.create(
        tenant_id=1,
        device_id=device.id,
        function_key="set_speed",
        params={"value": 1},
        dispatch_channel="edge_heartbeat",
        status="sent",
        expires_at=now - timedelta(seconds=5),
    )
    kept_success = await KuaiiotDeviceCommand.get(uuid=command.uuid)
    kept_success.expires_at = now - timedelta(seconds=5)
    await kept_success.save(update_fields=["expires_at", "updated_at"])
    kept_failed = await KuaiiotDeviceCommand.get(uuid=failed.uuid)
    kept_failed.expires_at = now - timedelta(seconds=5)
    await kept_failed.save(update_fields=["expires_at", "updated_at"])
    still_pending = await KuaiiotDeviceCommand.create(
        tenant_id=1,
        device_id=device.id,
        function_key="set_speed",
        params={"value": 2},
        dispatch_channel="edge_heartbeat",
        status="pending",
        expires_at=now - timedelta(seconds=5),
    )
    still_sent = await KuaiiotDeviceCommand.create(
        tenant_id=1,
        device_id=device.id,
        function_key="set_speed",
        params={"value": 3},
        dispatch_channel="edge_heartbeat",
        status="sent",
        expires_at=now + timedelta(minutes=5),
    )
    clear_tenant_context()
    timeout = await run_kuaiiot_command_timeout_check()
    # 过期 pending（未下发即超时）与过期 sent 一并置 timeout
    assert timeout["commands_timed_out"] == 2
    set_current_tenant_id(1)
    await expired.refresh_from_db()
    await kept_success.refresh_from_db()
    await kept_failed.refresh_from_db()
    await still_pending.refresh_from_db()
    await still_sent.refresh_from_db()
    assert expired.status == "timeout"
    assert expired.completed_at is not None
    assert kept_success.status == "success"
    assert kept_failed.status == "failed"
    assert still_pending.status == "timeout"
    assert still_sent.status == "sent"

    kinds = [row.msg_type for row in await KuaiiotMessageLog.filter(device_id=device.id)]
    assert "command" in kinds
    clear_tenant_context()
    with pytest.raises(TenantContextError):
        await list_commands(1, device.id)


@pytest.mark.asyncio
async def test_group_assignment_rejects_other_tenant_and_skips_equipment(db):
    set_current_tenant_id(1)
    equipment = await Equipment.create(tenant_id=1, code="EQ-G", name="分组机床")
    status_before = equipment.status
    device = await _device("grp", equipment.uuid)
    own = await group_service.create_group(1, code="line-a", name="A线", sort_order=1)
    child = await group_service.create_group(1, code="cell-1", name="单元1", parent_id=own.id)
    assert child.parent_id == own.id

    set_current_tenant_id(2)
    foreign = await group_service.create_group(2, code="line-a", name="别人的线")

    set_current_tenant_id(1)
    with pytest.raises(ValidationError, match="不属于当前租户"):
        await group_service.assign_device_group(1, device.id, foreign.id)
    await device.refresh_from_db()
    assert device.group_id is None

    assigned = await group_service.assign_device_group(1, device.id, own.id)
    assert assigned.group_id == own.id
    await equipment.refresh_from_db()
    assert equipment.status == status_before
    assert equipment.name == "分组机床"

    clear_tenant_context()
    with pytest.raises(TenantContextError):
        await group_service.list_groups(1)
    with pytest.raises(TenantContextError):
        await MessageLogService.list_messages(1)
