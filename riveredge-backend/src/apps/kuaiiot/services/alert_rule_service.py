"""快数采告警规则服务。"""

from __future__ import annotations

from typing import Optional

from apps.kuaiiot.constants import ALERT_OPERATORS, ALERT_RULE_TYPES, ALERT_SEVERITIES, OFFLINE_ALERT_TAG_KEY
from apps.kuaiiot.models.iot import IotAlertRule, IotDevice
from apps.kuaiiot.schemas.iot import AlertRuleCreate, AlertRuleUpdate
from infra.exceptions.exceptions import NotFoundError, ValidationError


class AlertRuleService:
    @staticmethod
    def _normalize_offline_defaults(payload: dict) -> dict:
        payload.setdefault("rule_type", "threshold")
        rule_type = str(payload.get("rule_type") or "threshold").strip()
        if rule_type not in ALERT_RULE_TYPES:
            raise ValidationError(f"无效的规则类型: {rule_type}")
        if rule_type == "offline":
            payload["tag_key"] = OFFLINE_ALERT_TAG_KEY
            payload["operator"] = "eq"
            payload["threshold_text"] = "offline"
            payload["threshold_number"] = None
        return payload

    @staticmethod
    def _validate_rule(data: AlertRuleCreate | AlertRuleUpdate, *, is_create: bool) -> None:
        payload = data.model_dump(exclude_unset=not is_create)
        payload = AlertRuleService._normalize_offline_defaults(payload)
        rule_type = str(payload.get("rule_type") or "threshold")
        operator = payload.get("operator")
        if operator is not None and operator not in ALERT_OPERATORS:
            raise ValidationError(f"无效的比较运算符: {operator}")
        severity = payload.get("severity")
        if severity is not None and severity not in ALERT_SEVERITIES:
            raise ValidationError(f"无效的严重级别: {severity}")
        if is_create:
            create_data = data if isinstance(data, AlertRuleCreate) else None
            if create_data and not create_data.device_id and not create_data.equipment_uuid:
                raise ValidationError("device_id 与 equipment_uuid 至少填写一项")
            if rule_type == "threshold":
                if create_data and not create_data.tag_key:
                    raise ValidationError("阈值规则必须填写 tag_key")
                if create_data and create_data.threshold_number is None and not create_data.threshold_text:
                    raise ValidationError("threshold_number 与 threshold_text 至少填写一项")

    @staticmethod
    async def list_rules(
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        device_id: Optional[int] = None,
        is_enabled: Optional[bool] = None,
        q: Optional[str] = None,
    ) -> tuple[list[IotAlertRule], int]:
        query = IotAlertRule.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if device_id is not None:
            query = query.filter(device_id=device_id)
        if is_enabled is not None:
            query = query.filter(is_enabled=is_enabled)
        if q:
            query = query.filter(name__icontains=q)
        total = await query.count()
        items = await query.order_by("-created_at", "-id").offset((page - 1) * page_size).limit(page_size)
        return items, total

    @staticmethod
    async def get_by_uuid(tenant_id: int, uuid: str) -> IotAlertRule:
        item = await IotAlertRule.filter(tenant_id=tenant_id, uuid=uuid, deleted_at__isnull=True).first()
        if not item:
            raise NotFoundError(f"告警规则不存在: {uuid}")
        return item

    @staticmethod
    async def create(tenant_id: int, data: AlertRuleCreate) -> IotAlertRule:
        AlertRuleService._validate_rule(data, is_create=True)
        exists = await IotAlertRule.filter(tenant_id=tenant_id, code=data.code, deleted_at__isnull=True).exists()
        if exists:
            raise ValidationError(f"规则编码已存在: {data.code}")
        if data.device_id:
            device = await IotDevice.filter(id=data.device_id, tenant_id=tenant_id, deleted_at__isnull=True).first()
            if not device:
                raise NotFoundError(f"IoT 设备不存在: {data.device_id}")
        payload = AlertRuleService._normalize_offline_defaults(data.model_dump())
        return await IotAlertRule.create(tenant_id=tenant_id, **payload)

    @staticmethod
    async def update(tenant_id: int, uuid: str, data: AlertRuleUpdate) -> IotAlertRule:
        item = await AlertRuleService.get_by_uuid(tenant_id, uuid)
        AlertRuleService._validate_rule(data, is_create=False)
        payload = data.model_dump(exclude_unset=True)
        if "device_id" in payload and payload["device_id"]:
            device = await IotDevice.filter(
                id=payload["device_id"], tenant_id=tenant_id, deleted_at__isnull=True
            ).first()
            if not device:
                raise NotFoundError(f"IoT 设备不存在: {payload['device_id']}")
        merged = {
            "rule_type": item.rule_type,
            "tag_key": item.tag_key,
            "operator": item.operator,
            "threshold_number": item.threshold_number,
            "threshold_text": item.threshold_text,
            **payload,
        }
        merged = AlertRuleService._normalize_offline_defaults(merged)
        for key, value in merged.items():
            if key in payload or key in {"tag_key", "operator", "threshold_number", "threshold_text"}:
                setattr(item, key, value)
        await item.save()
        return item

    @staticmethod
    async def delete(tenant_id: int, uuid: str) -> None:
        item = await AlertRuleService.get_by_uuid(tenant_id, uuid)
        from core.utils.timezone_utils import resolve_business_datetime

        item.deleted_at = resolve_business_datetime()
        await item.save()
