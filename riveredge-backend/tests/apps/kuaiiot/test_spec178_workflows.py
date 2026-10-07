from datetime import timedelta
from unittest.mock import AsyncMock
import pytest
from apps.kuaiiot.models.connection import KuaiiotConnection
from apps.kuaiiot.models.delivery import KuaiiotDelivery
from apps.kuaiiot.workflows.functions import retention_workflow as retention
from apps.kuaiiot.workflows.functions.connection_health_workflow import run_kuaiiot_connection_health_check
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import set_current_tenant_id


@pytest.mark.asyncio
async def test_health_distinguishes_idle_http_and_disabled(db):
    set_current_tenant_id(1)
    enabled = await KuaiiotConnection.create(tenant_id=1, code='health', name='HTTP', connection_type='http')
    disabled = await KuaiiotConnection.create(tenant_id=1, code='disabled', name='停用', connection_type='http', is_enabled=False)
    assert await run_kuaiiot_connection_health_check() == {'checked': 2}
    await enabled.refresh_from_db()
    await disabled.refresh_from_db()
    assert enabled.health_status == 'idle'
    assert disabled.health_status == 'disabled'


@pytest.mark.asyncio
async def test_retention_requires_configuration_and_preserves_failed_delivery(db, monkeypatch):
    set_current_tenant_id(1)
    await KuaiiotConnection.create(tenant_id=1, code='retention', name='HTTP', connection_type='http')
    pending = await KuaiiotDelivery.create(tenant_id=1, kind='trend', delivery_key='pending', payload={})
    sent = await KuaiiotDelivery.create(tenant_id=1, kind='trend', delivery_key='sent', payload={}, status='delivered')
    await KuaiiotDelivery.filter(id__in=[pending.id, sent.id]).update(updated_at=resolve_business_datetime()-timedelta(days=10))
    monkeypatch.setattr(retention.BusinessConfigService, 'get_business_config', AsyncMock(return_value={'parameters': {}}))
    assert await retention.run_kuaiiot_retention_cleanup() == {'deleted': 0, 'configuration_required': 1}
    monkeypatch.setattr(retention.BusinessConfigService, 'get_business_config', AsyncMock(return_value={'parameters': {'kuaiiot_retention_days': 7}}))
    assert await retention.run_kuaiiot_retention_cleanup() == {'deleted': 1, 'configuration_required': 0}
    assert await KuaiiotDelivery.filter(id=pending.id).exists()
    assert not await KuaiiotDelivery.filter(id=sent.id).exists()
