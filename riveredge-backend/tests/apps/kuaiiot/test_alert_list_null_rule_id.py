"""GET /alerts 必须能列出 rule_id 为空的事件告警。"""

import pytest

from apps.kuaiiot.models.alert import KuaiiotAlert
from apps.kuaiiot.services.alert_service import list_alerts
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import set_current_tenant_id


@pytest.mark.asyncio
async def test_list_alerts_returns_row_with_null_rule_id(db):
    set_current_tenant_id(1)
    created = await KuaiiotAlert.create(
        tenant_id=1,
        rule_id=None,
        device_id=1,
        tag_key="fault",
        severity="warning",
        message="event alert",
        status="open",
        triggered_at=resolve_business_datetime(),
    )

    listed = await list_alerts(1)

    found = next(item for item in listed if item.id == created.id)
    assert found.rule_id is None
    assert found.tag_key == "fault"
