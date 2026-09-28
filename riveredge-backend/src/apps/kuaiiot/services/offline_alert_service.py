"""离线告警。只消费 152 已经标成离线的设备，不另做超时判断。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from apps.kuaiiot.constants import (
    OFFLINE_ALERT_OPERATOR,
    OFFLINE_ALERT_TAG_KEY,
    OFFLINE_ALERT_THRESHOLD_TEXT,
)
from apps.kuaiiot.models.alert import KuaiiotAlert, KuaiiotAlertRule
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.services.tag_template_service import _require_tenant
from infra.domain.tenant_context import with_tenant
from infra.exceptions.exceptions import NotFoundError, ValidationError


async def create_offline_rule(
    tenant_id: int,
    *,
    code: str,
    name: str,
    device_id: Optional[int] = None,
    severity: str = "warning",
    user_id: Optional[int] = None,
) -> KuaiiotAlertRule:
    tid = _require_tenant(tenant_id)
    rule_code = (code or "").strip()
    rule_name = (name or "").strip()
    if not rule_code or not rule_name:
        raise ValidationError("离线规则编码和名称不能为空")
    level = (severity or "warning").strip() or "warning"
    if device_id is not None:
        device = await KuaiiotDevice.filter(
            tenant_id=tid,
            id=device_id,
            deleted_at__isnull=True,
        ).first()
        if device is None:
            raise NotFoundError("IoT 设备不存在")
    exists = await KuaiiotAlertRule.filter(tenant_id=tid, code=rule_code, deleted_at__isnull=True).exists()
    if exists:
        raise ValidationError("告警规则编码已存在")
    return await KuaiiotAlertRule.create(
        tenant_id=tid,
        code=rule_code,
        name=rule_name,
        device_id=device_id,
        tag_key=OFFLINE_ALERT_TAG_KEY,
        operator=OFFLINE_ALERT_OPERATOR,
        threshold_number=None,
        threshold_text=OFFLINE_ALERT_THRESHOLD_TEXT,
        severity=level,
        rule_type="offline",
        created_by=user_id,
        updated_by=user_id,
    )


async def write_offline_alerts(flipped: list[dict], checked_at: datetime | None) -> int:
    """为本次被标成离线、且曾经有入站时间的设备写告警。没有 offline 规则则不写。"""
    if not flipped or checked_at is None:
        return 0
    created = 0
    for item in flipped:
        if item.get("last_seen_at") is None:
            continue
        tenant_id = item.get("tenant_id")
        device_id = item.get("id")
        if tenant_id is None or device_id is None:
            continue
        async with with_tenant(int(tenant_id), reason="离线告警写入设备所属租户"):
            rules = await KuaiiotAlertRule.filter(
                tenant_id=int(tenant_id),
                rule_type="offline",
                is_enabled=True,
                deleted_at__isnull=True,
            )
            for rule in rules:
                if rule.device_id is not None and int(rule.device_id) != int(device_id):
                    continue
                await KuaiiotAlert.create(
                    tenant_id=int(tenant_id),
                    rule_id=rule.id,
                    device_id=int(device_id),
                    equipment_uuid=item.get("equipment_uuid"),
                    tag_key=OFFLINE_ALERT_TAG_KEY,
                    severity=(rule.severity or "warning").strip() or "warning",
                    message=f"设备 {item.get('code') or device_id} 已被 152 离线检查标成离线",
                    actual_value="false",
                    status="open",
                    triggered_at=checked_at,
                )
                created += 1
    return created
