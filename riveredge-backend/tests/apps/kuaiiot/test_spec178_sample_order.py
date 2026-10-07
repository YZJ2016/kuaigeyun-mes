from datetime import timedelta
from decimal import Decimal

import pytest

from apps.kuaiiot.models.tag import KuaiiotTagSnapshot
from apps.kuaiiot.schemas.ingest import IngestBody
from apps.kuaiiot.services.ingest_service import IngestService
from apps.kuaiiot.services.status_mapper import normalize_equipment_status
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import set_current_tenant_id
from tests.apps.kuaiiot.test_ingest_service import _register_pair


@pytest.mark.asyncio
async def test_old_and_equal_sample_cannot_replace_snapshot(db):
    set_current_tenant_id(1)
    device = await _register_pair(None, "order")
    now = resolve_business_datetime()
    for timestamp, value in [(now, 20), (now - timedelta(minutes=1), 10), (now, 30)]:
        await IngestService.ingest(device.device_token, IngestBody(tags={"temp": value}, timestamp=timestamp.isoformat()))
    row = await KuaiiotTagSnapshot.get(device_id=device.id, tag_key="temp")
    assert row.value_number == Decimal("20")


@pytest.mark.asyncio
async def test_bad_quality_preserves_quality_without_business_value(db):
    set_current_tenant_id(1)
    device = await _register_pair(None, "quality")
    await IngestService.ingest(device.device_token, IngestBody(tags={"temp": 999}, qualities={"temp": "bad"}))
    row = await KuaiiotTagSnapshot.get(device_id=device.id, tag_key="temp")
    assert row.quality == "bad"
    assert row.value_number is None
    from apps.kuaiiot.models.delivery import KuaiiotDelivery
    delivery = await KuaiiotDelivery.get(kind="trend")
    assert delivery.payload["quality"] == "bad"
    assert delivery.payload["value"] is None


def test_unknown_status_stays_unknown():
    assert normalize_equipment_status("vendor-unknown") == "未知"


@pytest.mark.asyncio
async def test_writeback_guard_uses_locked_equipment_state(db):
    from apps.kuaizhizao.models.equipment import Equipment
    set_current_tenant_id(1)
    stale = await Equipment.create(tenant_id=1, code="STATE-LOCK", name="锁后状态", status="正常")
    await Equipment.filter(id=stale.id).update(status="报废")
    now = resolve_business_datetime()
    assert await IngestService._maybe_insert_monitor(1, stale, {"status": "运行中"}, now, now) is False
