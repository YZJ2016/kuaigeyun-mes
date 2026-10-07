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


async def list_rules(tenant_id: int) -> list[KuaiiotAlertRule]:
    tid = _require_tenant(tenant_id)
    return await KuaiiotAlertRule.filter(tenant_id=tid, deleted_at__isnull=True).order_by("id").limit(500)


async def get_rule(tenant_id: int, rule_id: int) -> KuaiiotAlertRule:
    tid = _require_tenant(tenant_id)
    row = await KuaiiotAlertRule.filter(
        tenant_id=tid, id=rule_id, deleted_at__isnull=True
    ).first()
    if row is None:
        raise NotFoundError("告警规则不存在")
    return row


async def update_rule(tenant_id: int, rule_id: int, payload, *, user_id: Optional[int] = None) -> KuaiiotAlertRule:
    row = await get_rule(tenant_id, rule_id)
    fields = payload.model_fields_set
    structural = {"tag_key", "operator", "threshold_number", "threshold_text"}
    if row.rule_type != "threshold" and structural & fields:
        raise ValidationError("离线规则的点位、比较符与阈值不可编辑")
    if "operator" in fields and payload.operator is not None:
        operator = payload.operator.strip()
        if operator not in OPERATORS:
            raise ValidationError("比较符仅允许 gt、lt、gte、lte、eq、ne")
        row.operator = operator
    if "severity" in fields and payload.severity is not None:
        severity = payload.severity.strip()
        if severity not in _RULE_SEVERITIES:
            raise ValidationError("告警严重级别仅允许 info、warning、critical")
        row.severity = severity
    if "name" in fields:
        title = (payload.name or "").strip()
        if not title:
            raise ValidationError("规则名称不能为空")
        row.name = title
    if "tag_key" in fields and payload.tag_key is not None:
        row.tag_key = payload.tag_key.strip()
    if "threshold_number" in fields:
        row.threshold_number = payload.threshold_number
    if "threshold_text" in fields:
        row.threshold_text = (payload.threshold_text or "").strip() or None
    if row.rule_type == "threshold" and row.threshold_number is None and row.threshold_text is None:
        raise ValidationError("数值阈值与文本阈值至少填写其一")
    if "device_id" in fields:
        if payload.device_id is not None:
            device = await KuaiiotDevice.filter(
                tenant_id=int(row.tenant_id),
                id=payload.device_id,
                deleted_at__isnull=True,
            ).first()
            if device is None:
                raise NotFoundError("IoT 设备不存在")
        row.device_id = payload.device_id
    if "equipment_uuid" in fields:
        equipment_uuid = (payload.equipment_uuid or "").strip() or None
        if equipment_uuid is not None:
            try:
                await EquipmentService.get_equipment_by_uuid(int(row.tenant_id), equipment_uuid)
            except NotFoundError as exc:
                raise ValidationError("绑定设备不属于当前租户") from exc
        row.equipment_uuid = equipment_uuid
    if "cooldown_seconds" in fields and payload.cooldown_seconds is not None:
        row.cooldown_seconds = payload.cooldown_seconds
    if "notify_enabled" in fields and payload.notify_enabled is not None:
        row.notify_enabled = payload.notify_enabled
    if "is_enabled" in fields and payload.is_enabled is not None:
        row.is_enabled = payload.is_enabled
    if "remark" in fields:
        row.remark = payload.remark
    row.updated_by = user_id
    await row.save()
    return row


async def delete_rule(tenant_id: int, rule_id: int, *, user_id: Optional[int] = None) -> None:
    row = await get_rule(tenant_id, rule_id)
    row.deleted_at = resolve_business_datetime()
    row.deleted_by = user_id
    await row.save(update_fields=["deleted_at", "deleted_by", "updated_at"])


async def delete_alert(tenant_id: int, alert_id: int, *, user_id: Optional[int] = None) -> None:
    tid = _require_tenant(tenant_id)
    row = await KuaiiotAlert.filter(tenant_id=tid, id=alert_id, deleted_at__isnull=True).first()
    if row is None:
        raise NotFoundError("告警不存在")
    row.deleted_at = resolve_business_datetime()
    row.deleted_by = user_id
    await row.save(update_fields=["deleted_at", "deleted_by", "updated_at"])


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
