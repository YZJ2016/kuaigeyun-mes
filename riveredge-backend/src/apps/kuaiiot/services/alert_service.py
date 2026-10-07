"""入站阈值评估。notify_enabled 为真也只插入告警行。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from apps.kuaizhizao.services.equipment_service import EquipmentService
from apps.kuaiiot.models.alert import KuaiiotAlert, KuaiiotAlertRule
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.services.alert_threshold_resolver import (
    OPERATORS,
    format_actual_value,
    is_threshold_breached,
)
from apps.kuaiiot.services.tag_template_service import _require_tenant
from infra.exceptions.exceptions import NotFoundError, ValidationError
from apps.kuaiiot.services.delivery_service import enqueue
from core.utils.timezone_utils import resolve_business_datetime


_RULE_SEVERITIES = {"info", "warning", "critical"}


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def evaluate_thresholds(
    tenant_id: int,
    device_id: int,
    equipment_uuid: Optional[str],
    samples: dict[str, tuple[Optional[str], Optional[Decimal], Optional[bool]]],
    server_now: datetime,
) -> int:
    """对本次入站里已映射且启用的点位做阈值判断。冷却期内不新增告警。"""
    if not samples:
        return 0
    rules = await KuaiiotAlertRule.filter(
        tenant_id=tenant_id,
        is_enabled=True,
        deleted_at__isnull=True,
        rule_type="threshold",
        tag_key__in=list(samples.keys()),
    )
    created = 0
    for rule in rules:
        if rule.device_id is not None and int(rule.device_id) != int(device_id):
            continue
        if rule.equipment_uuid:
            if not equipment_uuid or rule.equipment_uuid != equipment_uuid:
                continue
        sample = samples.get(rule.tag_key)
        if sample is None:
            continue
        value_text, value_number, value_bool = sample
        breached = is_threshold_breached(
            rule.operator,
            threshold_number=rule.threshold_number,
            threshold_text=rule.threshold_text,
            value_number=value_number,
            value_text=value_text,
            value_bool=value_bool,
        )
        previous = await KuaiiotAlert.filter(
            tenant_id=tenant_id,
            rule_id=rule.id,
            device_id=device_id,
            equipment_uuid=equipment_uuid,
            deleted_at__isnull=True,
        ).order_by("-triggered_at").first()
        if not breached:
            if previous is not None and previous.recovered_at is None:
                previous.recovered_at = server_now
                if previous.status != "closed":
                    previous.status = "recovered"
                await previous.save()
                if rule.notify_enabled:
                    await enqueue(tenant_id, "notification", f"alert:{previous.id}:recovered", {"alert_id": previous.id, "action": "recovered", "message": previous.message})
            continue
        if previous is not None:
            if previous.recovered_at is None:
                continue
            elapsed = _aware(server_now) - _aware(previous.triggered_at)
            if elapsed < timedelta(seconds=int(rule.cooldown_seconds)):
                continue
        actual = format_actual_value(value_text, value_number, value_bool)
        alert = await KuaiiotAlert.create(
            tenant_id=tenant_id,
            rule_id=rule.id,
            device_id=device_id,
            equipment_uuid=equipment_uuid,
            tag_key=rule.tag_key,
            severity=rule.severity,
            message=f"{rule.name} 阈值命中",
            actual_value=actual,
            status="open",
            triggered_at=server_now,
        )
        if rule.notify_enabled:
            await enqueue(tenant_id, "notification", f"alert:{alert.id}:raised", {"alert_id": alert.id, "action": "raised", "message": alert.message})
        created += 1
    return created


async def create_rule(tenant_id: int, payload, *, user_id: Optional[int] = None) -> KuaiiotAlertRule:
    tid = _require_tenant(tenant_id)
    operator = payload.operator.strip()
    if operator not in OPERATORS:
        raise ValidationError("比较符仅允许 gt、lt、gte、lte、eq、ne")
    severity = (payload.severity or "warning").strip() or "warning"
    if severity not in _RULE_SEVERITIES:
        raise ValidationError("告警严重级别仅允许 info、warning、critical")
    threshold_text = (payload.threshold_text or "").strip() or None
    if payload.threshold_number is None and threshold_text is None:
        raise ValidationError("数值阈值与文本阈值至少填写其一")
    equipment_uuid = (payload.equipment_uuid or "").strip() or None
    if equipment_uuid is not None:
        try:
            await EquipmentService.get_equipment_by_uuid(tid, equipment_uuid)
        except NotFoundError as exc:
            raise ValidationError("绑定设备不属于当前租户") from exc
    if payload.device_id is not None:
        device = await KuaiiotDevice.filter(
            tenant_id=tid,
            id=payload.device_id,
            deleted_at__isnull=True,
        ).first()
        if device is None:
            raise NotFoundError("IoT 设备不存在")
    code = payload.code.strip()
    exists = await KuaiiotAlertRule.filter(tenant_id=tid, code=code, deleted_at__isnull=True).exists()
    if exists:
        raise ValidationError("告警规则编码已存在")
    try:
        return await KuaiiotAlertRule.create(
            tenant_id=tid,
            code=code,
            name=payload.name.strip(),
            device_id=payload.device_id,
            equipment_uuid=equipment_uuid,
            tag_key=payload.tag_key.strip(),
            operator=operator,
            threshold_number=payload.threshold_number,
            threshold_text=threshold_text,
            severity=severity,
            cooldown_seconds=payload.cooldown_seconds,
            notify_enabled=payload.notify_enabled,
            is_enabled=payload.is_enabled,
            rule_type="threshold",
            remark=payload.remark,
            created_by=user_id,
            updated_by=user_id,
        )
    except IntegrityError as exc:
        raise ValidationError("告警规则编码已存在") from exc


async def list_alerts(tenant_id: int) -> list[KuaiiotAlert]:
    tid = _require_tenant(tenant_id)
    return await KuaiiotAlert.filter(tenant_id=tid, deleted_at__isnull=True).order_by("-triggered_at").limit(100)


async def transition_alert(tenant_id: int, alert_id: int, action: str, user_id: int) -> KuaiiotAlert:
    tid = _require_tenant(tenant_id)
    async with in_transaction():
        row = await KuaiiotAlert.filter(tenant_id=tid, id=alert_id, deleted_at__isnull=True).select_for_update().first()
        if row is None:
            raise NotFoundError("告警不存在")
        if action == "acknowledge" and row.acknowledged_at is None and row.status != "closed":
            row.acknowledged_at = resolve_business_datetime()
            row.acknowledged_by = user_id
            if row.recovered_at is None:
                row.status = "acknowledged"
        elif action == "close" and row.closed_at is None:
            row.closed_at = resolve_business_datetime()
            row.closed_by = user_id
            row.status = "closed"
        await row.save()
    return row
