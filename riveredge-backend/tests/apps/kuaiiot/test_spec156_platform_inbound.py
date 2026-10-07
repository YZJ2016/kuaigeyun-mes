"""spec 156：平台遥测走现有入站；不新注册 cron，不编造平台 URL。"""

from __future__ import annotations

import inspect
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from apps.kuaiiot.models.alert import KuaiiotAlert
from apps.kuaiiot.models.command import KuaiiotDeviceCommand
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.message_log import KuaiiotMessageLog
from apps.kuaiiot.models.tag import KuaiiotTagSnapshot
from apps.kuaiiot.schemas.control import ConnectionCreate, ConnectionOut, DeviceCreate, TagCreate
from apps.kuaiiot.schemas.product import (
    ProductCreate,
    ProductEdgeActionIn,
    ProductEventIn,
    ProductFunctionIn,
    ProductFunctionParamIn,
    ProductTagIn,
)
from apps.kuaiiot.services import control_service, platform_telemetry, product_service
from apps.kuaiiot.services.command_service import (
    NOT_SENT,
    PLATFORM_DISPATCHERS,
    claim_pending_commands,
    create_command,
    dispatch_jetlinks,
    dispatch_thingsboard,
    submit_command_result,
)
from apps.kuaiiot.services.mqtt_subscriber_service import MqttSubscriberService
from apps.kuaiiot.workflows.functions.command_timeout_workflow import run_kuaiiot_command_timeout_check
from apps.kuaiiot.workflows.functions.mqtt_subscriber_workflow import run_kuaiiot_mqtt_reload
from apps.kuaiiot.workflows.functions.telemetry_sync_workflow import run_kuaiiot_telemetry_pull
from core.models.integration_config import IntegrationConfig
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import clear_tenant_context, set_current_tenant_id
from infra.exceptions.exceptions import ValidationError

_BACKEND = Path(__file__).resolve().parents[3]
_PATH_CONFIG = {
    "device_token_path": "device.token",
    "tags_path": "metrics",
    "events_path": "alarms",
    "timestamp_path": "ts",
    "idempotency_key_path": "id",
}


def _spec_156() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "docs" / "04.specs" / "156.kuaiiot-platform-inbound.md"
        if candidate.is_file():
            return candidate
    raise AssertionError("找不到 spec 156，无法核对地址空缺说明")


def _source_has_no_platform_url(text: str) -> None:
    assert "http://" not in text
    assert "https://" not in text


_NEW_FILES = (
    _BACKEND / "src" / "apps" / "kuaiiot" / "services" / "platform_telemetry.py",
    _BACKEND / "src" / "apps" / "kuaiiot" / "services" / "mqtt_subscriber_service.py",
    _BACKEND / "src" / "apps" / "kuaiiot" / "workflows" / "functions" / "mqtt_subscriber_workflow.py",
    _BACKEND / "src" / "apps" / "kuaiiot" / "workflows" / "functions" / "telemetry_sync_workflow.py",
)


async def _device(suffix: str) -> KuaiiotDevice:
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
        ),
    )
    await control_service.create_tag(
        1,
        device.id,
        TagCreate(tag_key="temp", name="温度", value_type="number", map_target="temperature"),
    )
    return device


@pytest.mark.asyncio
async def test_unregistered_topic_and_pull_write_nothing(db, monkeypatch):
    set_current_tenant_id(1)
    missed = await MqttSubscriberService.accept_topic_telemetry(
        "kuaiiot/ingest/not-registered",
        tags={"temp": "1"},
        idempotency_key="miss",
    )
    assert missed == {"stored": False}
    assert await MqttSubscriberService.accept_topic_telemetry("", tags={"temp": "1"}) == {"stored": False}

    def _unknown() -> list[dict]:
        return [{"device_token": "not-registered", "tags": {"temp": "9"}, "idempotency_key": "pull-miss"}]

    monkeypatch.setattr(platform_telemetry, "load_platform_records", _unknown)
    pulled = await run_kuaiiot_telemetry_pull()
    assert pulled == {"stored": 0, "skipped_unregistered": 1}
    assert await KuaiiotTagSnapshot.all().count() == 0


@pytest.mark.asyncio
async def test_mqtt_and_pull_call_ingest_once_per_idempotency_key(db, monkeypatch):
    set_current_tenant_id(1)
    product = await product_service.create_product(
        1,
        ProductCreate(
            code="line",
            name="产线",
            tags=[ProductTagIn(tag_key="temp", name="温度", value_type="number", map_target="temperature")],
            events=[ProductEventIn(event_key="fault", name="故障", severity="critical", message="设备故障")],
        ),
    )
    device = await _device("ok")
    device.product_id = product.id
    await device.save(update_fields=["product_id", "updated_at"])
    topic = f"plant/gateway/{device.device_token}"

    first = await MqttSubscriberService.accept_topic_telemetry(
        topic,
        tags={"temp": "25.5"},
        events=[{"event_key": "fault"}],
        idempotency_key="same-key",
    )
    second = await MqttSubscriberService.accept_topic_telemetry(
        topic,
        tags={"temp": "99"},
        events=[{"event_key": "fault"}],
        idempotency_key="same-key",
    )
    assert first == {"stored": True}
    assert second == {"stored": True}
    assert device.device_token not in str(first)

    snapshots = await KuaiiotTagSnapshot.filter(device_id=device.id)
    assert len(snapshots) == 1
    assert snapshots[0].tag_key == "temp"
    assert snapshots[0].value_number == Decimal("25.5")
    alerts = await KuaiiotAlert.filter(device_id=device.id)
    assert len(alerts) == 1
    assert alerts[0].tag_key == "fault"

    def _again() -> list[dict]:
        return [
            {
                "device_token": device.device_token,
                "tags": {"temp": "1"},
                "events": [{"event_key": "fault"}],
                "idempotency_key": "same-key",
            }
        ]

    monkeypatch.setattr(platform_telemetry, "load_platform_records", _again)
    pulled = await run_kuaiiot_telemetry_pull()
    assert pulled == {"stored": 1, "skipped_unregistered": 0}
    again = await KuaiiotTagSnapshot.filter(device_id=device.id)
    assert len(again) == 1
    assert again[0].value_number == Decimal("25.5")
    assert await KuaiiotAlert.filter(device_id=device.id).count() == 1


@pytest.mark.asyncio
async def test_ticks_do_not_open_broker_or_fetch(db):
    assert await run_kuaiiot_mqtt_reload() == {"subscriptions_aligned": 0}
    assert await run_kuaiiot_telemetry_pull() == {"stored": 0, "skipped_unregistered": 0}
    await MqttSubscriberService.start_all()
    await MqttSubscriberService.stop_all()


@pytest.mark.asyncio
async def test_edge_claim_receipt_and_timeout_stay(db):
    set_current_tenant_id(1)
    product = await product_service.create_product(
        1,
        ProductCreate(
            code="cmd",
            name="指令产品",
            tags=[ProductTagIn(tag_key="temp", name="温度", value_type="number", map_target="temperature")],
            functions=[
                ProductFunctionIn(
                    function_key="set_speed",
                    name="设置转速",
                    timeout_seconds=30,
                    params=[ProductFunctionParamIn(key="value", name="转速", value_type="number", required=True)],
                    edge_action=ProductEdgeActionIn(type="modbus_write", address=100, data_type="uint16"),
                )
            ],
        ),
    )
    device = await _device("edge")
    device.product_id = product.id
    await device.save(update_fields=["product_id", "updated_at"])
    command = await create_command(1, device.id, function_key="set_speed", params={"value": 80})
    claimed = await claim_pending_commands(1, device.id)
    assert len(claimed) == 1
    assert claimed[0]["command_uuid"] == command.uuid
    assert claimed[0]["edge_action"]["type"] == "modbus_write"
    clear_tenant_context()
    done = await submit_command_result(
        device.device_token,
        command_uuid=command.uuid,
        success=True,
        result={"address": 100},
    )
    assert done["status"] == "success"

    set_current_tenant_id(1)
    expired = await KuaiiotDeviceCommand.create(
        tenant_id=1,
        device_id=device.id,
        function_key="set_speed",
        params={"value": 1},
        dispatch_channel="edge_heartbeat",
        status="sent",
        expires_at=resolve_business_datetime() - timedelta(seconds=5),
    )
    clear_tenant_context()
    timed = await run_kuaiiot_command_timeout_check()
    assert timed["commands_timed_out"] == 1
    set_current_tenant_id(1)
    await expired.refresh_from_db()
    assert expired.status == "timeout"


def test_new_modules_do_not_invent_urls_or_grant_reads():
    taskiq = (_BACKEND / "src" / "core" / "tasks" / "taskiq_app.py").read_text(encoding="utf-8")
    assert 'cron": "*/2 * * * *"' in taskiq
    assert 'cron": "*/5 * * * *"' in taskiq
    assert "apps.kuaiiot.workflows.functions.mqtt_subscriber_workflow import run_kuaiiot_mqtt_reload" in taskiq
    assert "apps.kuaiiot.workflows.functions.telemetry_sync_workflow import run_kuaiiot_telemetry_pull" in taskiq
    for path in _NEW_FILES:
        text = path.read_text(encoding="utf-8")
        assert "http://" not in text
        assert "https://" not in text
        assert "KUAIOT_CONNECTION_CIPHER_KEY" not in text
        assert "TENANT_JDBC_CIPHER_KEY" not in text
        assert "AI_MODEL_CIPHER_KEY" not in text
        assert "kuaiiot:fill:read" not in text
        assert "kuaiiot:analytics:read" not in text
        assert "command_service" not in text
        assert "KuaiiotTagSnapshot" not in text
        assert "evaluate_thresholds" not in text


def _mapped_payload(device: KuaiiotDevice, idempotency_key: str) -> dict:
    return {
        "device": {"token": device.device_token},
        "metrics": {"temp": "25.5", "password": "tag-secret"},
        "alarms": [{"event_key": "fault", "mqtt_password": "evt-secret"}],
        "ts": "2026-09-29T10:00:00",
        "id": idempotency_key,
        "password": "body-secret",
    }


async def _core_uuid(kind: str, code: str) -> str:
    core = await IntegrationConfig.create(
        tenant_id=1, code=code, name="公共连接", type=kind.lower(),
        config={"password": "do-not-leak", "host": "broker.invalid"},
    )
    return str(core.uuid)


async def _mapped_device(suffix: str, connection_type: str, config: dict):
    product = await product_service.create_product(
        1,
        ProductCreate(
            code=f"prod-{suffix}",
            name="产线",
            tags=[ProductTagIn(tag_key="temp", name="温度", value_type="number", map_target="temperature")],
            events=[ProductEventIn(event_key="fault", name="故障", severity="critical", message="设备故障")],
            functions=[
                ProductFunctionIn(
                    function_key="set_speed",
                    name="设置转速",
                    timeout_seconds=30,
                    params=[ProductFunctionParamIn(key="value", name="转速", value_type="number", required=True)],
                    edge_action=ProductEdgeActionIn(type="modbus_write", address=100, data_type="uint16"),
                )
            ],
        ),
    )
    connection = await control_service.create_connection(
        1,
        ConnectionCreate(code=f"conn-{suffix}", name="线边", connection_type=connection_type, config=config,
                         integration_uuid=await _core_uuid(connection_type, f"core-{suffix}")),
    )
    device = await control_service.create_device(
        1,
        DeviceCreate(
            connection_id=connection.id,
            external_device_id=f"ext-{suffix}",
            code=f"dev-{suffix}",
            name=f"采集{suffix}",
        ),
    )
    await control_service.create_tag(
        1,
        device.id,
        TagCreate(tag_key="temp", name="温度", value_type="number", map_target="temperature"),
    )
    device.product_id = product.id
    await device.save(update_fields=["product_id", "updated_at"])
    return connection, device


def test_platform_pull_stays_empty_while_address_section_remains():
    spec = _spec_156().read_text(encoding="utf-8")
    assert "### 平台地址未进入仓库" in spec
    assert "地址未进入仓库与 spec，拉取因此为空" in spec
    assert "调试时看这一节，不要到代码里猜地址" in spec
    assert "不得发出猜测的 HTTP 请求" in spec
    assert platform_telemetry.load_platform_records() == []
    for fn in (
        platform_telemetry.load_platform_records,
        platform_telemetry.normalize_thingsboard,
        platform_telemetry.normalize_jetlinks,
        platform_telemetry.pull_registered_telemetry,
        dispatch_thingsboard,
        dispatch_jetlinks,
    ):
        text = inspect.getsource(fn)
        assert "平台地址未进入仓库" in (fn.__doc__ or "")
        _source_has_no_platform_url(text)
        assert "urlopen" not in text
        assert "httpx" not in text
    assert set(PLATFORM_DISPATCHERS) == {"thingsboard", "jetlinks"}
    assert dispatch_thingsboard() == NOT_SENT
    assert dispatch_jetlinks() == NOT_SENT


@pytest.mark.asyncio
async def test_pull_stays_empty_when_platform_connections_exist(db):
    set_current_tenant_id(1)
    for kind in ("thingsboard", "jetlinks"):
        await control_service.create_connection(
            1,
            ConnectionCreate(
                code=f"empty-{kind}",
                integration_uuid=await _core_uuid(kind, f"core-empty-{kind}"),
                name=kind,
                connection_type=kind,
                config=dict(_PATH_CONFIG),
            ),
        )
    assert platform_telemetry.load_platform_records() == []
    assert await run_kuaiiot_telemetry_pull() == {"stored": 0, "skipped_unregistered": 0}


@pytest.mark.asyncio
async def test_normalizers_ingest_from_config_and_hide_passwords(db):
    set_current_tenant_id(1)
    mqtt_config = {"topic": "plant/gateway/+", **_PATH_CONFIG}
    connection, device = await _mapped_device("mqtt", "mqtt", mqtt_config)
    dumped = ConnectionOut.model_validate(connection).model_dump()
    assert dumped["config"]["topic"] == "plant/gateway/+"
    assert "password" not in dumped["config"]
    assert "do-not-leak" not in str(dumped)
    assert "also-hidden" not in str(dumped)

    payload = _mapped_payload(device, "mqtt-once")
    first = await platform_telemetry.normalize_mqtt(connection, "plant/gateway/line-1", payload)
    second = await platform_telemetry.normalize_mqtt(connection, "plant/gateway/line-1", payload)
    assert first == {"stored": True}
    assert second == {"stored": True}
    assert "do-not-leak" not in str(first)
    missed = await platform_telemetry.normalize_mqtt(connection, "other/topic", payload)
    assert missed == {"stored": False}
    snapshots = await KuaiiotTagSnapshot.filter(device_id=device.id)
    assert len(snapshots) == 1
    assert snapshots[0].value_number == Decimal("25.5")
    assert await KuaiiotTagSnapshot.filter(device_id=device.id, tag_key="password").count() == 0
    logs = await KuaiiotMessageLog.filter(device_id=device.id)
    logged = str([row.payload for row in logs])
    assert "do-not-leak" not in logged
    assert "also-hidden" not in logged
    assert "tag-secret" not in logged
    assert "evt-secret" not in logged
    assert "body-secret" not in logged

    tb_connection, tb_device = await _mapped_device("tb", "thingsboard", dict(_PATH_CONFIG))
    stored = await platform_telemetry.normalize_thingsboard(tb_connection, _mapped_payload(tb_device, "tb-once"))
    assert stored == {"stored": True}
    assert await KuaiiotTagSnapshot.filter(device_id=tb_device.id).count() == 1
    wrong = await platform_telemetry.normalize_jetlinks(tb_connection, _mapped_payload(tb_device, "tb-once"))
    assert wrong == {"stored": False}

    jl_connection, jl_device = await _mapped_device("jl", "jetlinks", dict(_PATH_CONFIG))
    stored = await platform_telemetry.normalize_jetlinks(jl_connection, _mapped_payload(jl_device, "jl-once"))
    assert stored == {"stored": True}
    assert await run_kuaiiot_telemetry_pull() == {"stored": 0, "skipped_unregistered": 0}
    assert await run_kuaiiot_mqtt_reload() == {"subscriptions_aligned": 1}
    assert "do-not-leak" not in str(await run_kuaiiot_mqtt_reload())


@pytest.mark.asyncio
async def test_platform_commands_stay_not_sent_and_are_not_claimed(db):
    set_current_tenant_id(1)
    _connection, device = await _mapped_device("tb-cmd", "thingsboard", dict(_PATH_CONFIG))
    command = await create_command(1, device.id, function_key="set_speed", params={"value": 80})
    assert command.dispatch_channel == "thingsboard"
    assert command.status == NOT_SENT
    planted = await KuaiiotDeviceCommand.create(
        tenant_id=1,
        device_id=device.id,
        function_key="set_speed",
        params={"value": 1},
        dispatch_channel="thingsboard",
        status="pending",
    )
    claimed = await claim_pending_commands(1, device.id)
    assert claimed == []
    await command.refresh_from_db()
    await planted.refresh_from_db()
    assert command.status == NOT_SENT
    assert planted.status == "pending"
    clear_tenant_context()
    receipt = await submit_command_result(
        device.device_token,
        command_uuid=command.uuid,
        success=True,
        result={"address": 100},
    )
    assert receipt == {"status": NOT_SENT}
    set_current_tenant_id(1)
    await command.refresh_from_db()
    assert command.status == NOT_SENT
    assert command.sent_at is None

    _jl_connection, jl_device = await _mapped_device("jl-cmd", "jetlinks", dict(_PATH_CONFIG))
    jl_command = await create_command(1, jl_device.id, function_key="set_speed", params={"value": 1})
    assert jl_command.dispatch_channel == "jetlinks"
    assert jl_command.status == NOT_SENT
    assert await claim_pending_commands(1, jl_device.id) == []

    _mqtt_connection, mqtt_device = await _mapped_device(
        "mqtt-cmd",
        "mqtt",
        {"topic": "plant/gateway/+", **_PATH_CONFIG},
    )
    with pytest.raises(ValidationError, match="MQTT"):
        await create_command(1, mqtt_device.id, function_key="set_speed", params={"value": 1})
    assert await KuaiiotDeviceCommand.filter(device_id=mqtt_device.id).count() == 0


@pytest.mark.asyncio
async def test_platform_command_without_edge_action_stays_not_sent(db):
    set_current_tenant_id(1)
    product = await product_service.create_product(
        1,
        ProductCreate(
            code="no-edge",
            name="无边缘动作产品",
            functions=[
                ProductFunctionIn(
                    function_key="reboot",
                    name="平台重启",
                    params=[ProductFunctionParamIn(key="value", name="值", value_type="number", required=True)],
                )
            ],
        ),
    )
    connection = await control_service.create_connection(
        1,
        ConnectionCreate(
            code="conn-no-edge",
            integration_uuid=await _core_uuid("thingsboard", "core-no-edge"),
            name="平台",
            connection_type="thingsboard",
            config=dict(_PATH_CONFIG),
        ),
    )
    device = await control_service.create_device(
        1,
        DeviceCreate(
            connection_id=connection.id,
            external_device_id="ext-no-edge",
            code="dev-no-edge",
            name="采集no-edge",
        ),
    )
    device.product_id = product.id
    await device.save(update_fields=["product_id", "updated_at"])
    command = await create_command(1, device.id, function_key="reboot", params={"value": 1})
    assert command.dispatch_channel == "thingsboard"
    assert command.status == NOT_SENT
    assert await claim_pending_commands(1, device.id) == []

    edge_connection = await control_service.create_connection(
        1,
        ConnectionCreate(code="conn-edge-na", name="边缘", connection_type="http"),
    )
    edge_device = await control_service.create_device(
        1,
        DeviceCreate(
            connection_id=edge_connection.id,
            external_device_id="ext-edge-na",
            code="dev-edge-na",
            name="采集edge-na",
        ),
    )
    edge_device.product_id = product.id
    await edge_device.save(update_fields=["product_id", "updated_at"])
    with pytest.raises(ValidationError, match="写寄存器地址"):
        await create_command(1, edge_device.id, function_key="reboot", params={"value": 1})
    assert await KuaiiotDeviceCommand.filter(device_id=edge_device.id).count() == 0


@pytest.mark.asyncio
async def test_overlength_idempotency_key_is_rejected(db):
    set_current_tenant_id(1)
    connection, device = await _mapped_device("long-key", "thingsboard", dict(_PATH_CONFIG))
    result = await platform_telemetry.normalize_thingsboard(connection, _mapped_payload(device, "k" * 200))
    assert result["stored"] is False
    assert "幂等键" in str(result.get("reason") or "")
    assert await KuaiiotTagSnapshot.filter(device_id=device.id).count() == 0


def test_topic_matches_treats_empty_levels_as_real_levels():
    assert platform_telemetry.topic_matches("a//b", "a//b") is True
    assert platform_telemetry.topic_matches("a/+/b", "a//b") is True
    assert platform_telemetry.topic_matches("a/#", "a//b") is True
    assert platform_telemetry.topic_matches("a/b", "a//b") is False
    assert platform_telemetry.topic_matches("a//b", "a/b") is False
    assert platform_telemetry.topic_matches("a/b/c", "a//b") is False
    assert platform_telemetry.topic_matches("", "") is False
    assert platform_telemetry.topic_matches("a/b", "a/b") is True
    assert platform_telemetry.topic_matches("a/+", "a/b") is True
    assert platform_telemetry.topic_matches("a/#", "a/b/c") is True


@pytest.mark.asyncio
async def test_pull_skips_invalid_records_without_breaking(db, monkeypatch):
    set_current_tenant_id(1)
    _connection, device = await _mapped_device("pull-mix", "thingsboard", dict(_PATH_CONFIG))

    def _mixed() -> list[dict]:
        return [
            {"device_token": device.device_token, "tags": {"temp": "1"}, "idempotency_key": "k" * 200},
            {"device_token": device.device_token, "tags": {"temp": "2"}, "timestamp": "not-a-time"},
            {"device_token": device.device_token, "tags": {"temp": "3"}, "idempotency_key": "good-key"},
        ]

    monkeypatch.setattr(platform_telemetry, "load_platform_records", _mixed)
    pulled = await run_kuaiiot_telemetry_pull()
    assert pulled == {"stored": 1, "skipped_unregistered": 2}
    snapshots = await KuaiiotTagSnapshot.filter(device_id=device.id)
    assert len(snapshots) == 1
    assert snapshots[0].value_number == Decimal("3")


@pytest.mark.asyncio
async def test_mqtt_reload_matches_connection_type_case_insensitively(db):
    set_current_tenant_id(1)
    await control_service.create_connection(
        1,
        ConnectionCreate(
            code="conn-uptype",
            integration_uuid=await _core_uuid("mqtt", "core-uptype"),
            name="上行",
            connection_type="MQTT",
            config={"topic": "plant/#"},
        ),
    )
    assert await run_kuaiiot_mqtt_reload() == {"subscriptions_aligned": 1}
