"""设备运营馈送与一条报表 HTTP 登记。"""

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from tortoise import Tortoise

from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaireport.models.dashboard import KuaireportDashboard, KuaireportDashboardVersion
from apps.kuaireport.models.data_source import KuaireportDataSource
from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaizhizao.models.equipment_ops import EquipmentSpotCheck
from apps.kuaizhizao.models.equipment_status_monitor import EquipmentStatusMonitor
from apps.kuaizhizao.models.reporting_record import ReportingRecord
from apps.kuaiiot.services.ops_feed_service import (
    EQUIPMENT_OPS_DASHBOARD_CODE,
    FEED_PATH,
    FEED_SOURCE_NAME,
    read_equipment_ops_feed,
)
from core.utils.timezone_utils import resolve_business_datetime, to_site_date
from infra.config.infra_config import infra_settings
from infra.domain.tenant_context import clear_tenant_context, set_current_tenant_id
from infra.exceptions.exceptions import ValidationError

_BACKEND = Path(__file__).resolve().parents[3]
_SERVICE = _BACKEND / "src/apps/kuaiiot/services/ops_feed_service.py"
_EMPTY = {
    "equipment_list": [],
    "ops_metrics": [],
    "status_dist": [],
    "workshop_stats": [],
    "spot_check_recent": [],
}


@pytest_asyncio.fixture
async def feed_db():
    clear_tenant_context()
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={
            "models": [
                "apps.kuaiiot.models.device",
                "apps.kuaizhizao.models.equipment",
                "apps.kuaizhizao.models.equipment_status_monitor",
                "apps.kuaizhizao.models.reporting_record",
                "apps.kuaizhizao.models.equipment_ops",
                "apps.kuaireport.models.data_source",
                "apps.kuaireport.models.dashboard",
            ]
        },
    )
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        clear_tenant_context()
        await Tortoise.close_connections()


def _base(monkeypatch, value: str) -> None:
    monkeypatch.setattr(infra_settings, "base_url_override", value)


def _feed_url(origin: str) -> str:
    return origin.rstrip("/") + FEED_PATH


async def _equipment(tenant_id: int, code: str, *, workshop_id: int | None = None, workshop_name: str | None = None):
    return await Equipment.create(
        tenant_id=tenant_id,
        code=code,
        name=f"设备{code}",
        workshop_id=workshop_id,
        workshop_name=workshop_name,
    )


async def _device(tenant_id: int, equipment: Equipment | None, suffix: str):
    return await KuaiiotDevice.create(
        tenant_id=tenant_id,
        external_device_id=f"ext-{suffix}",
        code=f"iot-{suffix}",
        name=f"采集{suffix}",
        device_token=f"tok-{suffix}",
        equipment_uuid=None if equipment is None else equipment.uuid,
    )


async def _monitor(equipment: Equipment, status: str, at, *, source: str = "sensor"):
    return await EquipmentStatusMonitor.create(
        tenant_id=equipment.tenant_id,
        equipment_id=equipment.id,
        equipment_uuid=equipment.uuid,
        equipment_code=equipment.code,
        equipment_name=equipment.name,
        status=status,
        is_online=status == "运行中",
        data_source=source,
        monitored_at=at,
    )


async def _report(equipment: Equipment, at, *, status: str = "approved", reported: str = "10", qualified: str = "8", info=None):
    return await ReportingRecord.create(
        tenant_id=equipment.tenant_id,
        work_order_id=1,
        work_order_code="WO-1",
        work_order_name="工单",
        operation_id=1,
        operation_code="OP-1",
        operation_name="工序",
        reported_quantity=Decimal(reported),
        qualified_quantity=Decimal(qualified),
        unqualified_quantity=Decimal(reported) - Decimal(qualified),
        work_hours=Decimal("1"),
        reported_at=at,
        status=status,
        device_info=info if info is not None else {"code": equipment.code},
    )


@pytest.mark.asyncio
async def test_feed_five_fields_hide_other_tenant_and_register_one_http_row(feed_db, monkeypatch):
    _base(monkeypatch, "https://mes.example.com/")
    end = resolve_business_datetime()
    set_current_tenant_id(2)
    foreign = await _equipment(2, "EQ-OTHER", workshop_id=9, workshop_name="外车间")
    await _device(2, foreign, "other")
    await _monitor(foreign, "运行中", end - timedelta(hours=2))
    await _monitor(foreign, "待机", end - timedelta(hours=1))
    await _report(foreign, end - timedelta(minutes=20))
    await EquipmentSpotCheck.create(
        tenant_id=2,
        document_no="SC-OTHER",
        equipment_id=foreign.id,
        equipment_uuid=foreign.uuid,
        equipment_code=foreign.code,
        check_date=to_site_date(end),
    )

    set_current_tenant_id(1)
    orphan = await _equipment(1, "EQ-ORPHAN", workshop_id=1, workshop_name="未绑定")
    await _device(1, None, "bare")
    equipment = await _equipment(1, "EQ-1", workshop_id=3, workshop_name="一车间")
    await _device(1, equipment, "bound")
    await _monitor(equipment, "运行中", end - timedelta(hours=2))
    await _monitor(equipment, "故障", end - timedelta(minutes=90), source="manual")
    await _monitor(equipment, "待机", end - timedelta(hours=1))
    report = await _report(equipment, end - timedelta(minutes=30), info={"equipment_id": equipment.id})
    await _report(equipment, end - timedelta(minutes=25), status="pending", reported="100", qualified="100")
    await _report(equipment, end - timedelta(minutes=20), reported="0", qualified="0")
    await EquipmentSpotCheck.create(
        tenant_id=1,
        document_no="SC-ORPHAN",
        equipment_id=orphan.id,
        equipment_uuid=orphan.uuid,
        equipment_code=orphan.code,
        check_date=to_site_date(end),
    )
    await EquipmentSpotCheck.create(
        tenant_id=1,
        document_no="SC-1",
        equipment_id=equipment.id,
        equipment_uuid=equipment.uuid,
        equipment_code=equipment.code,
        check_date=to_site_date(end),
        status="已完成",
        has_abnormality=False,
    )
    equipment_updated = equipment.updated_at
    report_status = report.status

    body = await read_equipment_ops_feed(1, 24, at=end)

    assert set(body) == set(_EMPTY)
    assert [row["code"] for row in body["equipment_list"]] == ["EQ-1"]
    listed = body["equipment_list"][0]
    assert listed["workshop_id"] == 3
    assert listed["workshop_name"] == "一车间"
    assert listed["status"] == "待机"
    assert listed["equipment_uuid"] != foreign.uuid
    metric = body["ops_metrics"][0]
    assert metric["availability_rate"] is None
    assert metric["quality_rate"] == 0.8
    assert metric["oee_live"] is None
    assert metric["unavailable_reasons"]
    assert metric["performance_rate"] is None
    assert body["status_dist"] == [{"status": "待机", "count": 1}]
    assert body["workshop_stats"] == [
        {"workshop_id": 3, "workshop_name": "一车间", "equipment_count": 1}
    ]
    assert [row["document_no"] for row in body["spot_check_recent"]] == ["SC-1"]
    assert "EQ-OTHER" not in json.dumps(body, ensure_ascii=False)
    assert "SC-OTHER" not in json.dumps(body, ensure_ascii=False)

    rows = await KuaireportDataSource.filter(type="http").order_by("id")
    assert len(rows) == 1
    assert rows[0].config["url"] == _feed_url("https://mes.example.com")
    assert "?" not in rows[0].config["url"]
    again = await read_equipment_ops_feed(1, 24, at=end)
    assert again["ops_metrics"][0]["oee_live"] is None
    assert await KuaireportDataSource.filter(type="http").count() == 1
    dashboards = await KuaireportDashboard.filter(tenant_id=1, code=EQUIPMENT_OPS_DASHBOARD_CODE)
    assert len(dashboards) == 1
    widgets = dashboards[0].widgets_config
    assert widgets[0]["options"]["field"] == "ops_metrics.oee_live"
    assert widgets[0]["data_source_id"] == rows[0].id
    assert "data_source_uuid" not in widgets[0]
    assert await KuaireportDashboardVersion.filter(tenant_id=1, dashboard_id=dashboards[0].id).count() == 1
    await equipment.refresh_from_db()
    await report.refresh_from_db()
    assert equipment.updated_at == equipment_updated
    assert report.status == report_status
    assert report.qualified_quantity == Decimal("8")


@pytest.mark.asyncio
async def test_other_tenant_context_does_not_read_this_tenant(feed_db, monkeypatch):
    _base(monkeypatch, "https://mes.example.com")
    end = resolve_business_datetime()
    set_current_tenant_id(1)
    equipment = await _equipment(1, "EQ-1")
    await _device(1, equipment, "bound")
    await _monitor(equipment, "运行中", end - timedelta(hours=1))
    set_current_tenant_id(2)
    body = await read_equipment_ops_feed(2, 24, at=end)
    assert body == _EMPTY
    assert await KuaireportDataSource.filter(type="http").count() == 1
    row = await KuaireportDataSource.filter(type="http").first()
    assert row is not None
    assert row.tenant_id == 2
    assert row.config["url"] == _feed_url("https://mes.example.com")


@pytest.mark.asyncio
async def test_no_tenant_returns_empty_without_insert(feed_db, monkeypatch):
    _base(monkeypatch, "https://mes.example.com")
    set_current_tenant_id(1)
    equipment = await _equipment(1, "EQ-1")
    await _device(1, equipment, "bound")
    clear_tenant_context()
    body = await read_equipment_ops_feed(1, 24)
    assert body == _EMPTY
    set_current_tenant_id(1)
    assert await Equipment.filter(code="EQ-1").count() == 1
    assert await KuaireportDataSource.all().count() == 0
    assert await KuaireportDashboard.all().count() == 0


@pytest.mark.asyncio
async def test_oee_live_null_when_sensor_segments_missing(feed_db, monkeypatch):
    _base(monkeypatch, "https://mes.example.com")
    end = resolve_business_datetime()
    set_current_tenant_id(1)
    equipment = await _equipment(1, "EQ-1", workshop_id=3, workshop_name="一车间")
    await _device(1, equipment, "bound")
    await _monitor(equipment, "运行中", end - timedelta(hours=1), source="manual")
    await _report(
        equipment,
        end - timedelta(minutes=10),
        reported="4",
        qualified="4",
        info={"equipment_code": equipment.code},
    )
    body = await read_equipment_ops_feed(1, 24, at=end)
    metric = body["ops_metrics"][0]
    assert metric["availability_rate"] is None
    assert metric["quality_rate"] == 1.0
    assert metric["oee_live"] is None
    assert metric["oee_live"] != 0
    assert body["equipment_list"][0]["code"] == "EQ-1"
    assert body["status_dist"] == []
    assert body["workshop_stats"][0]["equipment_count"] == 1


@pytest.mark.asyncio
async def test_oee_live_null_when_approved_yield_missing(feed_db, monkeypatch):
    _base(monkeypatch, "https://mes.example.com")
    end = resolve_business_datetime()
    set_current_tenant_id(1)
    equipment = await _equipment(1, "EQ-1")
    await _device(1, equipment, "bound")
    await _monitor(equipment, "运行中", end - timedelta(hours=2))
    await _monitor(equipment, "待机", end - timedelta(hours=1))
    await _report(equipment, end - timedelta(minutes=10), status="pending")
    await _report(equipment, end - timedelta(minutes=5), reported="0", qualified="0", info={"id": equipment.id})
    body = await read_equipment_ops_feed(1, 24, at=end)
    metric = body["ops_metrics"][0]
    assert metric["availability_rate"] is None
    assert metric["quality_rate"] is None
    assert metric["oee_live"] is None
    assert metric["oee_live"] != 0
    assert set(body) == set(_EMPTY)


@pytest.mark.asyncio
async def test_code_key_match_yields_numeric_oee(feed_db, monkeypatch):
    _base(monkeypatch, "https://mes.example.com")
    end = resolve_business_datetime()
    set_current_tenant_id(1)
    equipment = await _equipment(1, "EQ-CODE")
    await _device(1, equipment, "code")
    await _monitor(equipment, "运行中", end - timedelta(hours=1))
    await _report(equipment, end - timedelta(minutes=10), reported="4", qualified="2", info={"equipment_code": "EQ-CODE"})
    body = await read_equipment_ops_feed(1, 24, at=end)
    metric = body["ops_metrics"][0]
    assert metric["availability_rate"] is None
    assert metric["quality_rate"] == 0.5
    assert metric["oee_live"] is None


@pytest.mark.asyncio
async def test_empty_base_url_does_not_insert_row(feed_db, monkeypatch):
    _base(monkeypatch, "")
    set_current_tenant_id(1)
    with pytest.raises(ValidationError, match="请配置站点根地址") as caught:
        await read_equipment_ops_feed(1, 24)
    assert "http" not in caught.value.message
    assert await KuaireportDataSource.all().count() == 0


@pytest.mark.asyncio
async def test_localhost_base_url_registers_row_via_service(feed_db, monkeypatch):
    """回环地址经星报表服务层正常登记（_LOCAL_TEST_HOSTS 已放行），不再直写 ORM。"""
    _base(monkeypatch, "http://127.0.0.1:8000")
    set_current_tenant_id(1)
    body = await read_equipment_ops_feed(1, 24)
    assert set(body) == set(_EMPTY)
    rows = await KuaireportDataSource.filter(type="http")
    assert len(rows) == 1
    assert rows[0].config["url"] == "http://127.0.0.1:8000" + FEED_PATH
    assert rows[0].name == FEED_SOURCE_NAME
    assert rows[0].tenant_id == 1


@pytest.mark.asyncio
async def test_localhost_feed_row_seeds_dashboard(feed_db, monkeypatch):
    _base(monkeypatch, "http://localhost:8000")
    set_current_tenant_id(1)
    await read_equipment_ops_feed(1, 24)
    source = await KuaireportDataSource.filter(type="http").first()
    assert source is not None
    dashboards = await KuaireportDashboard.filter(tenant_id=1, code=EQUIPMENT_OPS_DASHBOARD_CODE)
    assert len(dashboards) == 1
    assert dashboards[0].widgets_config[0]["data_source_id"] == source.id


@pytest.mark.asyncio
async def test_private_base_url_returns_feed_without_row(feed_db, monkeypatch):
    _base(monkeypatch, "http://192.168.1.10:8000")
    set_current_tenant_id(1)
    body = await read_equipment_ops_feed(1, 24)
    assert set(body) == set(_EMPTY)
    assert await KuaireportDataSource.all().count() == 0
    assert await KuaireportDashboard.all().count() == 0


@pytest.mark.asyncio
async def test_repeat_read_keeps_edited_dashboard(feed_db, monkeypatch):
    _base(monkeypatch, "https://mes.example.com")
    set_current_tenant_id(1)
    await read_equipment_ops_feed(1, 24)
    source = await KuaireportDataSource.filter(type="http").first()
    dashboard = await KuaireportDashboard.get(tenant_id=1, code=EQUIPMENT_OPS_DASHBOARD_CODE)
    assert dashboard.widgets_config[0]["data_source_id"] == source.id
    assert dashboard.widgets_config[0]["options"]["field"] == "ops_metrics.oee_live"
    edited = [{"id": "custom", "type": "title", "refresh_seconds": 5, "title": "用户改过"}]
    dashboard.widgets_config = edited
    dashboard.name = "用户改过的大屏"
    await dashboard.save()
    await read_equipment_ops_feed(1, 24)
    await dashboard.refresh_from_db()
    assert dashboard.widgets_config == edited
    assert dashboard.name == "用户改过的大屏"
    assert await KuaireportDashboard.filter(tenant_id=1).count() == 1
    assert await KuaireportDashboardVersion.filter(dashboard_id=dashboard.id).count() == 1
    listed = await KuaireportDashboard.filter(tenant_id=1).values("id", "code", "name", "status", "is_shared")
    assert listed[0]["code"] == EQUIPMENT_OPS_DASHBOARD_CODE


@pytest.mark.asyncio
async def test_existing_feed_row_updates_when_base_changes(feed_db, monkeypatch):
    _base(monkeypatch, "https://mes.example.com/")
    set_current_tenant_id(1)
    await read_equipment_ops_feed(1, 24)
    first = await KuaireportDataSource.filter(type="http").first()
    assert first is not None
    _base(monkeypatch, "https://mes.other.example")
    await read_equipment_ops_feed(1, 24)
    rows = await KuaireportDataSource.filter(type="http").order_by("id")
    assert len(rows) == 1
    assert rows[0].id == first.id
    assert rows[0].config["url"] == _feed_url("https://mes.other.example")


def test_service_source_does_not_query_tag_history_or_planned_oee():
    source = _SERVICE.read_text(encoding="utf-8")
    assert "tag_history" not in source
    assert "KuaiiotTagHistory" not in source
    assert "calculate_equipment_oee" not in source
    assert "EquipmentOEEService" not in source
    manifest = json.loads((_BACKEND / "src/apps/kuaiiot/manifest.json").read_text(encoding="utf-8"))
    assert "kuaiiot:analytics:read" in manifest["permissions"]


def test_route_is_tenant_rbac_not_device_token():
    from apps.kuaiiot.api.analytics import router

    route = next(item for item in router.routes if getattr(item, "path", None) == "/analytics/equipment-ops-feed")
    assert "GET" in route.methods
    found = False
    for dep in route.dependant.dependencies:
        closure = getattr(dep.call, "__closure__", None) or ()
        for cell in closure:
            if cell.cell_contents == ["kuaiiot:analytics:read"]:
                found = True
    assert found
    assert "{" not in route.path
