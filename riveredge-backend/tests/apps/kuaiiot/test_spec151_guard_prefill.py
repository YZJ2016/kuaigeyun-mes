"""阈值冷却、模板套用与预填只读。"""

from datetime import timedelta
from decimal import Decimal

import pytest

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaizhizao.models.equipment_ops import EquipmentSpotCheck
from apps.kuaizhizao.models.reporting_record import ReportingRecord
from apps.kuaiiot.models.alert import KuaiiotAlert, KuaiiotAlertRule
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.tag import KuaiiotTagDefinition, KuaiiotTagSnapshot
from apps.kuaiiot.schemas.control import ConnectionCreate, DeviceCreate, TagCreate
from apps.kuaiiot.schemas.ingest import IngestBody
from apps.kuaiiot.schemas.prefill import AlertRuleCreate
from apps.kuaiiot.services import alert_service, control_service, prefill_service
from apps.kuaiiot.services.ingest_service import IngestService
from apps.kuaiiot.services.tag_template_service import apply_template
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import TenantContextError, clear_tenant_context, set_current_tenant_id
from infra.exceptions.exceptions import ValidationError


async def _line(suffix: str, equipment_uuid: str | None = None):
    connection = await control_service.create_connection(
        1,
        ConnectionCreate(code=f"c-{suffix}", name="连接", connection_type="http"),
    )
    return await control_service.create_device(
        1,
        DeviceCreate(
            connection_id=connection.id,
            external_device_id=f"e-{suffix}",
            code=f"d-{suffix}",
            name=f"设备{suffix}",
            equipment_uuid=equipment_uuid,
        ),
    )


@pytest.mark.asyncio
async def test_template_apply_writes_only_tag_definitions(db):
    set_current_tenant_id(1)
    device = await control_service.create_device(
        1,
        DeviceCreate(
            external_device_id="ext-tpl",
            code="tpl-1",
            name="注塑采集",
            template_code="injection_molding",
        ),
    )
    rows = await KuaiiotTagDefinition.filter(device_id=device.id).order_by("tag_key")
    assert [row.tag_key for row in rows] == [
        "barrel_temperature",
        "injection_pressure",
        "mold_temperature",
        "online",
        "status",
    ]
    assert rows[0].map_target == "temperature"
    assert await KuaiiotAlert.all().count() == 0
    again = await apply_template(1, device.id, "injection_molding")
    assert len(again) == 5
    assert await KuaiiotTagDefinition.filter(device_id=device.id).count() == 5
    with pytest.raises(ValidationError, match="点位模板不存在"):
        await control_service.create_device(
            1,
            DeviceCreate(external_device_id="ext-x", code="tpl-x", name="无效", template_code="fourth"),
        )


@pytest.mark.asyncio
async def test_threshold_cooldown_skips_repeat_alert(db):
    set_current_tenant_id(1)
    equipment = await Equipment.create(tenant_id=1, code="EQ-HOT", name="加热")
    device = await _line("hot", equipment.uuid)
    await control_service.create_tag(
        1,
        device.id,
        TagCreate(tag_key="temp", name="温度", value_type="number", map_target="temperature"),
    )
    rule = await alert_service.create_rule(
        1,
        AlertRuleCreate(
            code="hot",
            name="过热",
            tag_key="temp",
            operator="gt",
            threshold_number=Decimal("10"),
            device_id=device.id,
            cooldown_seconds=300,
            notify_enabled=True,
        ),
    )
    assert rule.rule_type == "threshold"
    await IngestService.ingest(device.device_token, IngestBody(tags={"temp": 20}))
    await IngestService.ingest(device.device_token, IngestBody(tags={"temp": 21}))
    assert await KuaiiotAlert.filter(rule_id=rule.id).count() == 1
    await KuaiiotAlert.filter(rule_id=rule.id).update(
        triggered_at=resolve_business_datetime() - timedelta(seconds=301)
    )
    await IngestService.ingest(device.device_token, IngestBody(tags={"temp": 22}))
    alerts = await KuaiiotAlert.filter(rule_id=rule.id).order_by("id")
    assert len(alerts) == 1  # 持续越限仅一个告警，必须恢复后才能开启新周期
    await IngestService.ingest(device.device_token, IngestBody(tags={"temp": 5}))
    await alerts[0].refresh_from_db()
    assert alerts[0].recovered_at is not None
    await IngestService.ingest(device.device_token, IngestBody(tags={"temp": 22}))
    assert await KuaiiotAlert.filter(rule_id=rule.id).count() == 2
    assert alerts[0].actual_value == "20"
    alerts = await KuaiiotAlert.filter(rule_id=rule.id).order_by("id")
    assert alerts[1].actual_value == "22"
    assert alerts[0].status == "recovered"


@pytest.mark.asyncio
async def test_disabled_or_unmapped_rule_does_not_alert(db):
    set_current_tenant_id(1)
    device = await _line("quiet")
    await control_service.create_tag(
        1,
        device.id,
        TagCreate(tag_key="temp", name="温度", value_type="number", map_target="temperature"),
    )
    await alert_service.create_rule(
        1,
        AlertRuleCreate(
            code="off",
            name="关闭",
            tag_key="temp",
            operator="gt",
            threshold_number=Decimal("1"),
            device_id=device.id,
            is_enabled=False,
        ),
    )
    await KuaiiotAlertRule.create(
        tenant_id=1,
        code="ghost",
        name="未映射",
        tag_key="ghost",
        operator="gt",
        threshold_number=Decimal("1"),
        device_id=device.id,
        rule_type="threshold",
    )
    await IngestService.ingest(device.device_token, IngestBody(tags={"temp": 99}))
    assert await KuaiiotAlert.all().count() == 0


@pytest.mark.asyncio
async def test_prefill_returns_values_without_inserting_documents(db):
    set_current_tenant_id(1)
    equipment = await Equipment.create(tenant_id=1, code="EQ-FILL", name="预填机床")
    device = await _line("fill", equipment.uuid)
    await control_service.create_tag(
        1,
        device.id,
        TagCreate(
            tag_key="temp",
            name="温度",
            value_type="number",
            map_target="temperature",
            fill_target="sop_parameters.temp",
        ),
    )
    await control_service.create_tag(
        1,
        device.id,
        TagCreate(
            tag_key="press",
            name="压力",
            value_type="number",
            map_target="pressure",
            fill_target="spot_check.press",
        ),
    )
    reports_before = await ReportingRecord.all().count()
    checks_before = await EquipmentSpotCheck.all().count()
    await IngestService.ingest(device.device_token, IngestBody(tags={"temp": "25.5", "press": "4"}))
    reporting = await prefill_service.read_fill_context(1, equipment.uuid, "reporting")
    spot = await prefill_service.read_fill_context(1, equipment.uuid, "spot_check")
    assert reporting["values"] == {"temp": 25.5}
    assert reporting["device_uuid"] == device.uuid
    assert spot["values"] == {"press": 4.0}
    assert "temp" not in spot["values"]
    assert await ReportingRecord.all().count() == reports_before
    assert await EquipmentSpotCheck.all().count() == checks_before


@pytest.mark.asyncio
async def test_cross_tenant_prefill_returns_nothing_and_writes_no_alert(db):
    set_current_tenant_id(2)
    foreign = await Equipment.create(tenant_id=2, code="EQ-OTHER", name="外租户")
    connection = await control_service.create_connection(
        2,
        ConnectionCreate(code="c-other", name="外连接", connection_type="http"),
    )
    foreign_device = await control_service.create_device(
        2,
        DeviceCreate(
            connection_id=connection.id,
            external_device_id="ext-other",
            code="d-other",
            name="外设备",
            equipment_uuid=foreign.uuid,
        ),
    )
    await control_service.create_tag(
        2,
        foreign_device.id,
        TagCreate(
            tag_key="temp",
            name="温度",
            value_type="number",
            map_target="temperature",
            fill_target="sop_parameters.temp",
        ),
    )
    await alert_service.create_rule(
        2,
        AlertRuleCreate(
            code="foreign-hot",
            name="外租户过热",
            tag_key="temp",
            operator="gt",
            threshold_number=Decimal("1"),
            device_id=foreign_device.id,
            notify_enabled=True,
        ),
    )
    await IngestService.ingest(foreign_device.device_token, IngestBody(tags={"temp": 50}))
    alerts_before = await KuaiiotAlert.all().count()
    assert alerts_before == 1

    set_current_tenant_id(1)
    body = await prefill_service.read_fill_context(1, foreign.uuid, "reporting")
    assert body["values"] == {}
    assert "device_uuid" not in body
    set_current_tenant_id(2)
    assert await KuaiiotAlert.all().count() == alerts_before

    set_current_tenant_id(1)

    local = await _line("local")
    await control_service.create_tag(
        1,
        local.id,
        TagCreate(tag_key="temp", name="温度", value_type="number", map_target="temperature"),
    )
    await IngestService.ingest(local.device_token, IngestBody(tags={"temp": 80}))
    assert await KuaiiotAlert.filter(tenant_id=1).count() == 0


@pytest.mark.asyncio
async def test_prefill_without_tenant_reads_nothing(db, monkeypatch):
    clear_tenant_context()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("无租户上下文不应查询")

    monkeypatch.setattr(Equipment, "filter", forbidden)
    monkeypatch.setattr(KuaiiotDevice, "filter", forbidden)
    monkeypatch.setattr(KuaiiotTagDefinition, "filter", forbidden)
    monkeypatch.setattr(KuaiiotTagSnapshot, "filter", forbidden)
    monkeypatch.setattr(KuaiiotAlert, "filter", forbidden)
    with pytest.raises(TenantContextError):
        await prefill_service.read_fill_context(1, "missing-uuid", "reporting")
