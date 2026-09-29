"""spec 153：产品物模型、批量设备、离线告警与 Influx 趋势。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaiiot.constants import DEVICE_BATCH_MAX
from apps.kuaiiot.models.alert import KuaiiotAlert, KuaiiotAlertRule
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.product import KuaiiotProduct
from apps.kuaiiot.models.tag import KuaiiotTagDefinition, KuaiiotTagHistory, KuaiiotTagSnapshot
from apps.kuaiiot.schemas.control import DeviceCreate, DeviceOut, TagCreate
from apps.kuaiiot.schemas.ingest import IngestBody
from apps.kuaiiot.schemas.prefill import AlertRuleCreate
from apps.kuaiiot.schemas.product import DeviceBatchCreate, ProductCreate, ProductTagIn, ProductUpdate
from apps.kuaiiot.services import alert_service, control_service, offline_alert_service, product_service
from apps.kuaiiot.services.edge_config_service import EdgeConfigService
from apps.kuaiiot.services.ingest_service import IngestService
from apps.kuaiiot.services.trend_service import query_trend, write_trend
from apps.kuaiiot.workflows.functions.device_lifecycle_workflow import run_kuaiiot_offline_check
from core.models.integration_config import IntegrationConfig
from infra.domain.tenant_context import TenantContextError, clear_tenant_context, set_current_tenant_id
from infra.exceptions.exceptions import NotFoundError, ValidationError

_TOKEN = "spec153-influx-token"
_URL = "http://influx.example.invalid:8086"
_OTHER_URL = "http://other-tenant.example.invalid:8086"
_OTHER_TOKEN = "other-tenant-token"


def _tag() -> ProductTagIn:
    return ProductTagIn(tag_key="temp", name="温度", value_type="number", map_target="temperature", unit="C")


async def _product(code: str = "press") -> KuaiiotProduct:
    return await product_service.create_product(
        1,
        ProductCreate(code=code, name="压力机", tags=[_tag()]),
    )


def _tsdb(tenant_id: int, *, active: bool = True, url: str = _URL, token: str = _TOKEN, config: dict | None = None):
    body = config if config is not None else {
        "url": url,
        "org": "mes",
        "bucket": "iot",
        "token": token,
    }
    return IntegrationConfig.create(
        tenant_id=tenant_id,
        name="数采时序",
        code="kuaiiot_tsdb",
        type="influxdb",
        config=body,
        is_active=active,
    )


class _Record:
    def __init__(self, when: datetime, value: float):
        self._when = when
        self._value = value

    def get_time(self):
        return self._when

    def get_value(self):
        return self._value


class _Table:
    def __init__(self, records: list[_Record]):
        self.records = records


@pytest.mark.asyncio
async def test_product_tags_are_unique_per_tenant(db):
    set_current_tenant_id(1)
    created = await _product()
    assert created.tags[0]["tag_key"] == "temp"
    assert created.tags[0]["map_target"] == "temperature"
    with pytest.raises(ValidationError):
        product_service._validate_tags([{"tag_key": "temp", "name": "温度", "value_type": "number"}])
    updated = await product_service.update_product(
        1,
        created.id,
        ProductUpdate(tags=[ProductTagIn(tag_key="press", name="压力", value_type="number", map_target="pressure")]),
    )
    assert updated.tags[0]["tag_key"] == "press"
    with pytest.raises(ValidationError, match="产品编码已存在"):
        await _product()
    set_current_tenant_id(2)
    other = await product_service.create_product(2, ProductCreate(code="press", name="另一租户"))
    assert other.tenant_id == 2
    set_current_tenant_id(1)
    listed = await product_service.list_products(1)
    assert [row.id for row in listed] == [created.id]


@pytest.mark.asyncio
async def test_batch_copies_tags_and_rejects_over_100(db):
    set_current_tenant_id(1)
    product = await _product()
    with pytest.raises(ValidationError, match="100"):
        await product_service.batch_create_devices(
            1,
            DeviceBatchCreate(
                product_id=product.id,
                name_prefix="设备",
                code_prefix="dev",
                count=DEVICE_BATCH_MAX + 1,
            ),
        )
    assert await KuaiiotDevice.all().count() == 0
    assert await Equipment.all().count() == 0
    assert await KuaiiotTagDefinition.all().count() == 0

    created = await product_service.batch_create_devices(
        1,
        DeviceBatchCreate(product_id=product.id, name_prefix="设备", code_prefix="dev", count=2),
    )
    assert len(created) == 2
    assert await Equipment.all().count() == 0
    devices = await KuaiiotDevice.filter(product_id=product.id).order_by("code")
    assert [row.code for row in devices] == ["dev-001", "dev-002"]
    assert all(row.product_id == product.id for row in devices)
    tags = await KuaiiotTagDefinition.filter(tag_key="temp")
    assert {row.device_id for row in tags} == {devices[0].id, devices[1].id}
    assert tags[0].map_target == "temperature"
    public = DeviceOut.model_validate(devices[0]).model_dump()
    assert "device_token" not in public
    assert created[0]["device_token"]
    assert created[0]["device_token"] not in public.values()
    listed = [DeviceOut.model_validate(row).model_dump() for row in await control_service.list_devices(1)]
    assert all("device_token" not in row for row in listed)
    assert all(created[0]["device_token"] not in str(row) for row in listed)


@pytest.mark.asyncio
async def test_no_tenant_does_not_read_products_or_write_influx(db):
    clear_tenant_context()
    with patch("influxdb_client.InfluxDBClient") as client_cls:
        with pytest.raises(TenantContextError):
            await product_service.list_products(1)
        with pytest.raises(TenantContextError):
            await write_trend(1, device_id=1, tag_key="temp", value=1.0)
        client_cls.assert_not_called()
    set_current_tenant_id(1)
    assert await KuaiiotProduct.all().count() == 0


@pytest.mark.asyncio
async def test_offline_alert_follows_152_flip_only(db):
    set_current_tenant_id(1)
    stale = await control_service.create_device(
        1,
        DeviceCreate(external_device_id="ext-stale", code="stale", name="曾在线"),
    )
    fresh = await control_service.create_device(
        1,
        DeviceCreate(external_device_id="ext-fresh", code="fresh", name="仍在线"),
    )
    never = await control_service.create_device(
        1,
        DeviceCreate(external_device_id="ext-never", code="never", name="从未入站"),
    )
    already = await control_service.create_device(
        1,
        DeviceCreate(external_device_id="ext-down", code="down", name="早已离线"),
    )
    offline_rule = await offline_alert_service.create_offline_rule(
        1, code="offline-1", name="设备离线", severity="critical"
    )
    threshold = await alert_service.create_rule(
        1,
        AlertRuleCreate(
            code="hot",
            name="超温",
            tag_key="temp",
            operator="gt",
            threshold_number=Decimal("80"),
            device_id=stale.id,
        ),
    )
    assert offline_rule.rule_type == "offline"
    assert offline_rule.tag_key == "is_online"
    assert offline_rule.operator == "eq"
    assert offline_rule.threshold_text == "false"
    assert offline_rule.threshold_number is None
    fixed = datetime(2026, 9, 28, 8, 0, tzinfo=timezone.utc)
    stale.is_online = True
    stale.last_seen_at = fixed - timedelta(minutes=6)
    await stale.save(update_fields=["is_online", "last_seen_at", "updated_at"])
    fresh.is_online = True
    fresh.last_seen_at = fixed - timedelta(minutes=1)
    await fresh.save(update_fields=["is_online", "last_seen_at", "updated_at"])
    already.is_online = False
    already.last_seen_at = fixed - timedelta(minutes=30)
    await already.save(update_fields=["is_online", "last_seen_at", "updated_at"])

    set_current_tenant_id(2)
    foreign = await control_service.create_device(
        2,
        DeviceCreate(external_device_id="ext-foreign", code="foreign", name="他租户"),
    )
    foreign_rule = await offline_alert_service.create_offline_rule(2, code="offline-2", name="他租户离线")
    foreign.is_online = True
    foreign.last_seen_at = fixed - timedelta(minutes=6)
    await foreign.save(update_fields=["is_online", "last_seen_at", "updated_at"])

    clear_tenant_context()
    with patch(
        "apps.kuaiiot.services.edge_config_service.resolve_business_datetime",
        return_value=fixed,
    ):
        result = await run_kuaiiot_offline_check()
    assert result == {"devices_marked_offline": 2}

    set_current_tenant_id(1)
    own_rows = await KuaiiotAlert.filter(device_id=stale.id)
    assert len(own_rows) == 1
    own = own_rows[0]
    assert own.rule_id == offline_rule.id
    assert own.tag_key == "is_online"
    assert own.severity == "critical"
    triggered = own.triggered_at
    if triggered.tzinfo is None:
        triggered = triggered.replace(tzinfo=timezone.utc)
    assert triggered == fixed
    assert "152" in own.message
    assert own.rule_id is not None
    assert await KuaiiotAlert.filter(device_id__in=[never.id, fresh.id, already.id]).count() == 0
    await threshold.refresh_from_db()
    assert threshold.rule_type == "threshold"
    assert "rule_type" not in KuaiiotAlert._meta.fields_map

    set_current_tenant_id(2)
    peer_rows = await KuaiiotAlert.filter(device_id=foreign.id)
    assert len(peer_rows) == 1
    assert peer_rows[0].rule_id == foreign_rule.id


@pytest.mark.asyncio
async def test_heartbeat_does_not_insert_offline_alerts(db):
    set_current_tenant_id(1)
    device = await control_service.create_device(
        1,
        DeviceCreate(external_device_id="ext-hb", code="hb", name="心跳"),
    )
    await offline_alert_service.create_offline_rule(1, code="offline-hb", name="离线", device_id=device.id)
    await EdgeConfigService.save_config(
        1,
        code="line",
        name="线边",
        device_id=device.id,
        protocol="modbus_tcp",
        config={
            "host": "127.0.0.1",
            "port": 502,
            "unit_id": 1,
            "registers": [{"tag_key": "temp", "address": 0, "data_type": "float32"}],
            "publish": {"mode": "http_ingest"},
        },
    )
    clear_tenant_context()
    body = await EdgeConfigService.record_heartbeat(
        device.device_token,
        edge_config_code="line",
        config_version=1,
        agent_version="1.0.0",
        buffer_pending_count=0,
        status="online",
    )
    assert device.device_token not in str(body)
    set_current_tenant_id(1)
    assert await KuaiiotAlert.all().count() == 0


@pytest.mark.asyncio
async def test_trend_unavailable_leaves_snapshots_and_history(db):
    set_current_tenant_id(1)
    device = await control_service.create_device(
        1,
        DeviceCreate(external_device_id="ext-snap", code="snap", name="快照"),
    )
    await control_service.create_tag(
        1,
        device.id,
        TagCreate(tag_key="temp", name="温度", value_type="number", map_target="temperature"),
    )
    await _tsdb(2, url=_OTHER_URL, token=_OTHER_TOKEN)
    await _tsdb(1, active=False)
    clear_tenant_context()
    with patch("influxdb_client.InfluxDBClient") as client_cls:
        set_current_tenant_id(1)
        with pytest.raises(ValidationError, match="趋势不可用") as missing:
            await query_trend(
                1,
                device_id=device.id,
                tag_key="temp",
                start=datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc),
                stop=datetime(2026, 9, 28, 1, 0, tzinfo=timezone.utc),
            )
        assert _URL not in str(missing.value)
        assert _TOKEN not in str(missing.value)
        assert _OTHER_URL not in str(missing.value)
        client_cls.assert_not_called()
        clear_tenant_context()
        await IngestService.ingest(device.device_token, IngestBody(tags={"temp": "21.5"}))
        client_cls.assert_not_called()
    set_current_tenant_id(1)
    assert await KuaiiotTagSnapshot.filter(device_id=device.id, tag_key="temp").count() == 1
    assert await KuaiiotTagHistory.all().count() == 0


@pytest.mark.asyncio
async def test_trend_uses_only_this_tenant_influx(db, caplog):
    set_current_tenant_id(1)
    product = await _product()
    created = await product_service.batch_create_devices(
        1,
        DeviceBatchCreate(product_id=product.id, name_prefix="设备", code_prefix="trend", count=1),
    )
    device_id = created[0]["id"]
    token = created[0]["device_token"]
    await _tsdb(2, url=_OTHER_URL, token=_OTHER_TOKEN)
    await _tsdb(1)
    start = datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc)
    stop = datetime(2026, 9, 28, 2, 0, tzinfo=timezone.utc)
    sampled = datetime(2026, 9, 28, 1, 0, tzinfo=timezone.utc)
    query_api = MagicMock()
    query_api.query.return_value = [_Table([_Record(sampled, 21.5)])]
    write_api = MagicMock()
    client = MagicMock()
    client.query_api.return_value = query_api
    client.write_api.return_value = write_api

    with patch("influxdb_client.InfluxDBClient", return_value=client) as client_cls:
        await write_trend(1, device_id=device_id, tag_key="temp", value=21.5, sampled_at=sampled)
        points = await query_trend(1, device_id=device_id, tag_key="temp", start=start, stop=stop)
        text_tag = await KuaiiotTagDefinition.create(
            tenant_id=1,
            device_id=device_id,
            tag_key="note",
            name="备注",
            value_type="text",
            map_target="status",
        )
        with pytest.raises(ValidationError, match="数值点位"):
            await write_trend(1, device_id=device_id, tag_key=text_tag.tag_key, value=1)
        write_api.write.side_effect = RuntimeError(f"failed {_URL} {_TOKEN}")
        with pytest.raises(ValidationError, match="^趋势不可用$") as hidden:
            await write_trend(1, device_id=device_id, tag_key="temp", value=2)
        assert _URL not in str(hidden.value)
        assert _TOKEN not in str(hidden.value)

    assert points == [{"time": sampled, "value": 21.5}]
    assert await KuaiiotTagHistory.all().count() == 0
    assert await KuaiiotTagSnapshot.all().count() == 0
    urls = [call.kwargs["url"] for call in client_cls.call_args_list]
    tokens = [call.kwargs["token"] for call in client_cls.call_args_list]
    assert urls
    assert set(urls) == {_URL}
    assert _OTHER_URL not in urls
    assert set(tokens) == {_TOKEN}
    flux = query_api.query.call_args.args[0]
    assert str(device_id) in flux
    assert "temp" in flux
    assert _TOKEN not in flux
    assert _URL not in flux
    assert token not in caplog.text
    assert _TOKEN not in caplog.text
    assert _URL not in caplog.text


@pytest.mark.asyncio
async def test_trend_rejects_bad_tag_key_and_nonfinite_value(db):
    set_current_tenant_id(1)
    product = await _product()
    created = await product_service.batch_create_devices(
        1,
        DeviceBatchCreate(product_id=product.id, name_prefix="设备", code_prefix="bad", count=1),
    )
    device_id = created[0]["id"]
    await _tsdb(1)
    start = datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc)
    stop = datetime(2026, 9, 28, 2, 0, tzinfo=timezone.utc)
    with patch("influxdb_client.InfluxDBClient") as client_cls:
        for bad_key in ("temp,evil", "a=b", "tag key", 'qu"ote', "line\nbreak"):
            with pytest.raises(ValidationError, match="点位键无效"):
                await write_trend(1, device_id=device_id, tag_key=bad_key, value=1.0)
            with pytest.raises(ValidationError, match="点位键无效"):
                await query_trend(
                    1, device_id=device_id, tag_key=bad_key, start=start, stop=stop
                )
        for bad_value in (float("inf"), float("-inf"), float("nan"), "not-a-number"):
            with pytest.raises(ValidationError):
                await write_trend(1, device_id=device_id, tag_key="temp", value=bad_value)
        client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_trend_naive_sampled_at_is_utc(db):
    set_current_tenant_id(1)
    product = await _product()
    created = await product_service.batch_create_devices(
        1,
        DeviceBatchCreate(product_id=product.id, name_prefix="设备", code_prefix="naive", count=1),
    )
    device_id = created[0]["id"]
    await _tsdb(1)
    naive = datetime(2026, 9, 28, 1, 0, 0)
    write_api = MagicMock()
    client = MagicMock()
    client.write_api.return_value = write_api
    with patch("influxdb_client.InfluxDBClient", return_value=client):
        await write_trend(1, device_id=device_id, tag_key="temp", value=1.5, sampled_at=naive)
    record = write_api.write.call_args.kwargs["record"]
    expected_ns = int(naive.replace(tzinfo=timezone.utc).timestamp() * 1_000_000_000)
    assert record.endswith(str(expected_ns))


@pytest.mark.asyncio
async def test_other_tenant_product_is_not_used_for_batch(db):
    set_current_tenant_id(1)
    product = await _product()
    set_current_tenant_id(2)
    with pytest.raises(NotFoundError):
        await product_service.batch_create_devices(
            2,
            DeviceBatchCreate(product_id=product.id, name_prefix="设备", code_prefix="x", count=1),
        )
    assert await KuaiiotDevice.all().count() == 0
