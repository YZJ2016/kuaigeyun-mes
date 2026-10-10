"""快数采告警评估与记录。"""

from __future__ import annotations

from datetime import timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from apps.kuaiiot.constants import EVENT_ALERT_TAG_PREFIX, OFFLINE_ALERT_TAG_KEY
from apps.kuaiiot.models.iot import IotAlert, IotAlertRule, IotDevice
from apps.kuaiiot.services.alert_threshold_resolver import format_actual_value, is_threshold_breached
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import NotFoundError, ValidationError


class AlertService:
    @staticmethod
    async def list_alerts(
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        device_id: Optional[int] = None,
    ) -> tuple[list[IotAlert], int]:
        query = IotAlert.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if status:
            query = query.filter(status=status)
        if device_id is not None:
            query = query.filter(device_id=device_id)
        total = await query.count()
        items = await query.order_by("-triggered_at").offset((page - 1) * page_size).limit(page_size)
        return items, total

    @staticmethod
    async def get_by_uuid(tenant_id: int, uuid: str) -> IotAlert:
        item = await IotAlert.filter(tenant_id=tenant_id, uuid=uuid, deleted_at__isnull=True).first()
        if not item:
            raise NotFoundError(f"告警记录不存在: {uuid}")
        return item

    @staticmethod
    async def acknowledge(tenant_id: int, uuid: str, user_id: int) -> IotAlert:
        item = await AlertService.get_by_uuid(tenant_id, uuid)
        if item.status == "acknowledged":
            return item
        now = resolve_business_datetime()
        item.status = "acknowledged"
        item.acknowledged_at = now
        item.acknowledged_by = user_id
        await item.save()
        return item

    @staticmethod
    async def evaluate_device_ingest(
        tenant_id: int,
        device: IotDevice,
        tag_values: dict[str, tuple[Optional[str], Optional[Decimal], Optional[bool]]],
    ) -> int:
        if not tag_values:
            return 0
        rules = await IotAlertRule.filter(
            tenant_id=tenant_id,
            is_enabled=True,
            deleted_at__isnull=True,
        )
        matched_rules = []
        for rule in rules:
            if getattr(rule, "rule_type", "threshold") != "threshold":
                continue
            if rule.device_id and rule.device_id != device.id:
                continue
            if rule.equipment_uuid and rule.equipment_uuid != device.equipment_uuid:
                continue
            if not rule.device_id and not rule.equipment_uuid:
                continue
            if rule.tag_key not in tag_values:
                continue
            matched_rules.append(rule)

        triggered = 0
        now = resolve_business_datetime()
        for rule in matched_rules:
            value_text, value_number, value_bool = tag_values[rule.tag_key]
            if not is_threshold_breached(
                rule.operator,
                threshold_number=rule.threshold_number,
                threshold_text=rule.threshold_text,
                value_text=value_text,
                value_number=value_number,
                value_bool=value_bool,
            ):
                continue
            cutoff = now - timedelta(seconds=max(rule.cooldown_seconds, 0))
            recent = await IotAlert.filter(
                tenant_id=tenant_id,
                rule_id=rule.id,
                device_id=device.id,
                status="open",
                triggered_at__gte=cutoff,
                deleted_at__isnull=True,
            ).exists()
            if recent:
                continue
            actual = format_actual_value(value_text, value_number, value_bool)
            threshold_label = (
                str(rule.threshold_number)
                if rule.threshold_number is not None
                else str(rule.threshold_text or "")
            )
            message = f"{rule.name} 触发：{rule.tag_key}={actual}，阈值 {rule.operator} {threshold_label}"
            await IotAlert.create(
                tenant_id=tenant_id,
                rule_id=rule.id,
                device_id=device.id,
                equipment_uuid=device.equipment_uuid,
                tag_key=rule.tag_key,
                severity=rule.severity,
                message=message,
                actual_value=actual,
                status="open",
                triggered_at=now,
            )
            triggered += 1
            if rule.notify_enabled:
                await AlertService._dispatch_notification(
                    tenant_id=tenant_id,
                    rule=rule,
                    device=device,
                    message=message,
                    trigger_action="threshold_breached",
                )
        return triggered

    @staticmethod
    async def record_event_alert(
        tenant_id: int,
        device: IotDevice,
        *,
        event_key: str,
        event_name: str,
        level: str,
        payload: dict[str, Any] | None = None,
    ) -> int:
        if level not in {"warning", "critical"}:
            return 0
        now = resolve_business_datetime()
        tag_key = f"{EVENT_ALERT_TAG_PREFIX}{event_key}"
        cutoff = now - timedelta(seconds=300)
        recent = await IotAlert.filter(
            tenant_id=tenant_id,
            device_id=device.id,
            tag_key=tag_key,
            status="open",
            triggered_at__gte=cutoff,
            deleted_at__isnull=True,
        ).exists()
        if recent:
            return 0
        actual = ""
        if payload:
            actual = str(payload.get("message") or payload.get("detail") or payload)
        message = f"事件告警 {event_name} ({event_key})"
        if actual:
            message = f"{message}: {actual}"
        await IotAlert.create(
            tenant_id=tenant_id,
            rule_id=None,
            device_id=device.id,
            equipment_uuid=device.equipment_uuid,
            tag_key=tag_key,
            severity=level,
            message=message,
            actual_value=actual or event_key,
            status="open",
            triggered_at=now,
        )
        return 1

    @staticmethod
    async def evaluate_device_offline(tenant_id: int, device: IotDevice) -> int:
        rules = await IotAlertRule.filter(
            tenant_id=tenant_id,
            rule_type="offline",
            is_enabled=True,
            deleted_at__isnull=True,
        )
        matched_rules = []
        for rule in rules:
            if rule.device_id and rule.device_id != device.id:
                continue
            if rule.equipment_uuid and rule.equipment_uuid != device.equipment_uuid:
                continue
            if not rule.device_id and not rule.equipment_uuid:
                continue
            matched_rules.append(rule)

        triggered = 0
        now = resolve_business_datetime()
        for rule in matched_rules:
            cutoff = now - timedelta(seconds=max(rule.cooldown_seconds, 0))
            recent = await IotAlert.filter(
                tenant_id=tenant_id,
                rule_id=rule.id,
                device_id=device.id,
                tag_key=OFFLINE_ALERT_TAG_KEY,
                status="open",
                triggered_at__gte=cutoff,
                deleted_at__isnull=True,
            ).exists()
            if recent:
                continue
            message = f"{rule.name} 触发：设备 {device.name} 离线"
            await IotAlert.create(
                tenant_id=tenant_id,
                rule_id=rule.id,
                device_id=device.id,
                equipment_uuid=device.equipment_uuid,
                tag_key=OFFLINE_ALERT_TAG_KEY,
                severity=rule.severity,
                message=message,
                actual_value="offline",
                status="open",
                triggered_at=now,
            )
            triggered += 1
            if rule.notify_enabled:
                await AlertService._dispatch_notification(
                    tenant_id=tenant_id,
                    rule=rule,
                    device=device,
                    message=message,
                    trigger_action="device_offline",
                )
        return triggered

    @staticmethod
    async def _dispatch_notification(
        tenant_id: int,
        rule: IotAlertRule,
        device: IotDevice,
        message: str,
        *,
        trigger_action: str,
    ) -> None:
        try:
            from core.services.business.business_notification_service import BusinessNotificationService

            await BusinessNotificationService.dispatch(
                tenant_id,
                trigger_document="iot_alert",
                trigger_action=trigger_action,
                variables={
                    "rule_name": rule.name,
                    "device_name": device.name,
                    "tag_key": rule.tag_key,
                    "message": message,
                },
            )
        except Exception:
            return

# ---- 星数采本地执行版：告警规则 CRUD 与状态迁移（整型 ID 接口） ----

from datetime import datetime as _datetime  # noqa: F401  # 保持与本地版一致的前置依赖

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from apps.kuaizhizao.services.equipment_service import EquipmentService
from apps.kuaiiot.services.alert_threshold_resolver import OPERATORS
from apps.kuaiiot.services.delivery_service import enqueue
from apps.kuaiiot.services.tag_template_service import _require_tenant

_RULE_SEVERITIES = {"info", "warning", "critical"}

async def create_rule(tenant_id: int, payload, *, user_id: Optional[int] = None) -> IotAlertRule:
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
        device = await IotDevice.filter(
            tenant_id=tid,
            id=payload.device_id,
            deleted_at__isnull=True,
        ).first()
        if device is None:
            raise NotFoundError("IoT 设备不存在")
    code = payload.code.strip()
    exists = await IotAlertRule.filter(tenant_id=tid, code=code, deleted_at__isnull=True).exists()
    if exists:
        raise ValidationError("告警规则编码已存在")
    try:
        return await IotAlertRule.create(
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


async def list_alerts(tenant_id: int) -> list[IotAlert]:
    tid = _require_tenant(tenant_id)
    return await IotAlert.filter(tenant_id=tid, deleted_at__isnull=True).order_by("-triggered_at").limit(100)


async def list_rules(tenant_id: int) -> list[IotAlertRule]:
    tid = _require_tenant(tenant_id)
    return await IotAlertRule.filter(tenant_id=tid, deleted_at__isnull=True).order_by("id").limit(500)


async def get_rule(tenant_id: int, rule_id: int) -> IotAlertRule:
    tid = _require_tenant(tenant_id)
    row = await IotAlertRule.filter(
        tenant_id=tid, id=rule_id, deleted_at__isnull=True
    ).first()
    if row is None:
        raise NotFoundError("告警规则不存在")
    return row


async def update_rule(tenant_id: int, rule_id: int, payload, *, user_id: Optional[int] = None) -> IotAlertRule:
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
            device = await IotDevice.filter(
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
    row = await IotAlert.filter(tenant_id=tid, id=alert_id, deleted_at__isnull=True).first()
    if row is None:
        raise NotFoundError("告警不存在")
    row.deleted_at = resolve_business_datetime()
    row.deleted_by = user_id
    await row.save(update_fields=["deleted_at", "deleted_by", "updated_at"])


async def transition_alert(tenant_id: int, alert_id: int, action: str, user_id: int) -> IotAlert:
    tid = _require_tenant(tenant_id)
    async with in_transaction():
        row = await IotAlert.filter(tenant_id=tid, id=alert_id, deleted_at__isnull=True).select_for_update().first()
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


def _aware(value: _datetime) -> _datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def evaluate_thresholds(
    tenant_id: int,
    device_id: int,
    equipment_uuid: Optional[str],
    samples: dict[str, tuple[Optional[str], Optional[Decimal], Optional[bool]]],
    server_now: _datetime,
) -> int:
    """星数采阈值评估：对本次入站里已映射且启用的点位做阈值判断，冷却期内不新增告警。"""
    if not samples:
        return 0
    rules = await IotAlertRule.filter(
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
        previous = await IotAlert.filter(
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
        alert = await IotAlert.create(
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
