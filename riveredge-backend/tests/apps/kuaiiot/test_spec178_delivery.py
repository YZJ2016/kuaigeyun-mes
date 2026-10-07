from unittest.mock import AsyncMock

import pytest

from apps.kuaiiot.models.delivery import KuaiiotDelivery
from apps.kuaiiot.schemas.ingest import IngestBody
from apps.kuaiiot.services import delivery_service
from apps.kuaiiot.services.ingest_service import IngestService
from infra.domain.tenant_context import set_current_tenant_id
from tests.apps.kuaiiot.test_ingest_service import _register_pair


@pytest.mark.asyncio
async def test_ingest_registers_history_once_and_worker_retries(db, monkeypatch):
    set_current_tenant_id(1)
    device = await _register_pair(None, "history")
    body = IngestBody(tags={"temp": 20}, idempotency_key="sample-one")
    await IngestService.ingest(device.device_token, body)
    await IngestService.ingest(device.device_token, body)
    assert await KuaiiotDelivery.all().count() == 1
    writer = AsyncMock(side_effect=RuntimeError("synthetic external failure"))
    monkeypatch.setattr(delivery_service, "write_trend", writer)
    await delivery_service.process_pending()
    row = await KuaiiotDelivery.get()
    assert row.status == "pending" and row.attempts == 1
    assert "synthetic" not in row.last_error
    writer.side_effect = None
    row.next_attempt_at = None
    await row.save()
    await delivery_service.process_pending()
    await row.refresh_from_db()
    assert row.status == "delivered"
    assert writer.call_count == 2


@pytest.mark.asyncio
async def test_missing_notification_rule_is_observable(db, monkeypatch):
    set_current_tenant_id(1)
    row = await delivery_service.enqueue(1, "notification", "alert:1:raised", {"alert_id": 1, "action": "raised", "message": "温度异常"})
    monkeypatch.setattr(delivery_service.BusinessNotificationService, "dispatch", AsyncMock(return_value=0))
    await delivery_service.process_pending()
    await row.refresh_from_db()
    assert row.status == "blocked"
    assert row.last_error == "未配置规则或接收人，或本次无发送"
