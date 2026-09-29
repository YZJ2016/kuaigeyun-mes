"""HTTP 入站：凭据认设备、幂等、最新快照，并按星制造设备节流插入监控行。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaizhizao.models.equipment_fault import EquipmentFault, EquipmentRepair
from apps.kuaizhizao.models.equipment_status_monitor import EquipmentStatusMonitor
from apps.kuaizhizao.services.equipment_service import EquipmentService
from apps.kuaiiot.constants import (
    MONITOR_COLUMNS,
    OTHER_PARAMETERS_PREFIX,
    SENSOR_DATA_SOURCE,
    THROTTLE_SECONDS,
)
from apps.kuaiiot.models.alert import KuaiiotAlert
from apps.kuaiiot.models.dedup import KuaiiotIngestDedup
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.product import KuaiiotProduct
from apps.kuaiiot.models.tag import KuaiiotTagDefinition, KuaiiotTagSnapshot
from apps.kuaiiot.services.message_log_service import MessageLogService
from apps.kuaiiot.schemas.ingest import IngestBody
from apps.kuaiiot.services.alert_service import evaluate_thresholds
from apps.kuaiiot.services.status_mapper import (
    BLOCKED_EQUIPMENT_STATUSES,
    MONITOR_STATUS_WHEN_ABSENT,
    OPEN_FAULT_STATUSES,
    OPEN_REPAIR_STATUSES,
    normalize_equipment_status,
)
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import unscoped, with_tenant
from infra.exceptions.exceptions import AuthenticationError, NotFoundError, ValidationError

_NUMERIC_TARGETS = {"temperature", "pressure", "vibration"}

# 事件 message 里的 key=value 凭据统一打码（大小写不敏感）
_SECRET_PAIR = re.compile(r"\b(password|passwd|token|secret|api_key|apikey)\s*=\s*[^\s&,;]+", re.IGNORECASE)


def _mask_secret_pairs(text: str) -> str:
    return _SECRET_PAIR.sub(lambda match: f"{match.group(1)}=***", text)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
    raise ValidationError("布尔点位值无效")


def _as_decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValidationError("数值点位值无效")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise ValidationError("数值点位值无效") from exc
    if not number.is_finite() or abs(number) >= Decimal("1e12"):
        raise ValidationError("数值点位值超量程")
    return number


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _typed_snapshot(value_type: str, raw: Any) -> tuple[Optional[str], Optional[Decimal], Optional[bool]]:
    if raw is None:
        return None, None, None
    if value_type == "boolean":
        return None, None, _as_bool(raw)
    if value_type == "text":
        return str(raw), None, None
    return None, _as_decimal(raw), None


def _apply_monitor(map_target: str, tag_key: str, raw: Any, bucket: dict[str, Any]) -> None:
    if map_target == "status":
        bucket["status"] = None if raw is None else str(raw)
        return
    if map_target == "is_online":
        if raw is None:
            return
        bucket["is_online"] = _as_bool(raw)
        return
    if map_target in _NUMERIC_TARGETS:
        if raw is None:
            return
        bucket[map_target] = _as_decimal(raw).quantize(Decimal("0.01"))
        return
    if map_target == "other_parameters" or map_target.startswith(OTHER_PARAMETERS_PREFIX):
        current = bucket.setdefault("other_parameters", {})
        if map_target == "other_parameters":
            if isinstance(raw, dict):
                current.update(_json_ready(raw))
            elif raw is not None:
                current[tag_key] = _json_ready(raw)
            return
        key = map_target[len(OTHER_PARAMETERS_PREFIX) :]
        if raw is not None:
            current[key] = _json_ready(raw)


_ALERT_SEVERITIES = {"warning", "critical"}


def _event_severity(definition: dict, inbound: dict) -> str:
    defined = str(definition.get("severity") or definition.get("level") or "").strip().lower()
    if defined:
        return defined
    return str(inbound.get("severity") or inbound.get("level") or "").strip().lower()


def _event_message(definition: dict, inbound: dict, event_key: str) -> str:
    for source in (inbound, definition):
        text = source.get("message")
        if isinstance(text, str) and text.strip():
            return text.strip()
    name = definition.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return event_key


async def _defined_events(tenant_id: int, device: KuaiiotDevice) -> dict[str, dict]:
    if not device.product_id:
        return {}
    product = await KuaiiotProduct.filter(
        tenant_id=tenant_id,
        id=device.product_id,
        deleted_at__isnull=True,
    ).first()
    if product is None:
        return {}
    found: dict[str, dict] = {}
    for item in product.events or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("event_key") or "").strip()
        if key:
            found[key] = item
    return found


def _parse_sampled_at(raw: Optional[str], server_now: datetime) -> datetime:
    if raw is None or not str(raw).strip():
        return server_now
    text = str(raw).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError("timestamp 无效") from exc
    # 边缘端上送的是 UTC naive；naive 先按 UTC 标记，aware 原样走统一口径
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return resolve_business_datetime(parsed)


class IngestService:
    @staticmethod
    async def ingest(device_token: str, body: IngestBody) -> dict[str, Any]:
        token = (device_token or "").strip()
        if not token:
            raise AuthenticationError("设备凭据无效")
        device = await IngestService._match_device(token)
        async with with_tenant(int(device.tenant_id), reason="入站写入设备所属租户"):
            return await IngestService._ingest_matched(device, body)

    @staticmethod
    async def _match_device(token: str) -> KuaiiotDevice:
        async with unscoped(reason="按设备凭据匹配唯一未删除设备", resource="KuaiiotDevice"):
            rows = await KuaiiotDevice.filter(device_token=token, deleted_at__isnull=True).limit(2).all()
        if len(rows) != 1 or rows[0].tenant_id is None:
            raise AuthenticationError("设备凭据无效")
        return rows[0]

    @staticmethod
    async def _stored_response(tenant_id: int, device_id: int, key: str) -> Optional[dict[str, Any]]:
        row = await KuaiiotIngestDedup.filter(
            tenant_id=tenant_id,
            device_id=device_id,
            idempotency_key=key,
            deleted_at__isnull=True,
        ).first()
        if row is None:
            return None
        return json.loads(row.response_json)

    @staticmethod
    async def _ingest_matched(device: KuaiiotDevice, body: IngestBody) -> dict[str, Any]:
        tenant_id = int(device.tenant_id)
        key = (body.idempotency_key or "").strip()
        if key:
            stored = await IngestService._stored_response(tenant_id, device.id, key)
            if stored is not None:
                return stored

        equipment = await IngestService._bound_equipment(tenant_id, device.equipment_uuid)
        server_now = resolve_business_datetime()
        sampled_at = _parse_sampled_at(body.timestamp, server_now)
        definitions = await KuaiiotTagDefinition.filter(
            tenant_id=tenant_id,
            device_id=device.id,
            is_enabled=True,
            deleted_at__isnull=True,
        )
        by_key = {item.tag_key: item for item in definitions}
        planned: list[tuple[KuaiiotTagDefinition, Optional[str], Optional[Decimal], Optional[bool]]] = []
        monitor_fields: dict[str, Any] = {}
        for tag_key, raw in (body.tags or {}).items():
            definition = by_key.get(tag_key)
            if definition is None:
                continue
            value_text, value_number, value_bool = _typed_snapshot(definition.value_type, raw)
            planned.append((definition, value_text, value_number, value_bool))
            if definition.map_target in MONITOR_COLUMNS or definition.map_target.startswith(OTHER_PARAMETERS_PREFIX):
                _apply_monitor(definition.map_target, tag_key, raw, monitor_fields)

        try:
            async with in_transaction():
                for definition, value_text, value_number, value_bool in planned:
                    await IngestService._upsert_snapshot(
                        tenant_id,
                        device.id,
                        definition.tag_key,
                        value_text,
                        value_number,
                        value_bool,
                        sampled_at,
                    )
                current = await KuaiiotDevice.get(id=device.id, tenant_id=tenant_id)
                current.is_online = True
                current.last_seen_at = server_now
                await current.save(update_fields=["is_online", "last_seen_at", "updated_at"])
                monitor_written = False
                if equipment is not None and monitor_fields:
                    monitor_written = await IngestService._maybe_insert_monitor(
                        tenant_id,
                        equipment,
                        monitor_fields,
                        sampled_at,
                        server_now,
                    )
                if planned:
                    samples = {
                        definition.tag_key: (value_text, value_number, value_bool)
                        for definition, value_text, value_number, value_bool in planned
                    }
                    await evaluate_thresholds(
                        tenant_id,
                        device.id,
                        equipment.uuid if equipment is not None else None,
                        samples,
                        server_now,
                    )
                accepted_events = await IngestService._apply_events(
                    tenant_id,
                    device,
                    body.events or [],
                    sampled_at,
                )
                await MessageLogService.append(
                    tenant_id=tenant_id,
                    device_id=device.id,
                    direction="in",
                    msg_type="ingest",
                    payload={
                        "tag_keys": sorted(str(key) for key in (body.tags or {})),
                        "event_keys": accepted_events,
                    },
                    result="accepted",
                    forbidden_values=(device.device_token,),
                )
                if monitor_written and equipment is not None:
                    await MessageLogService.append(
                        tenant_id=tenant_id,
                        device_id=device.id,
                        direction="out",
                        msg_type="monitor_writeback",
                        payload={
                            "equipment_uuid": equipment.uuid,
                            "data_source": SENSOR_DATA_SOURCE,
                        },
                        result="written",
                        forbidden_values=(device.device_token,),
                    )
                result = {
                    "accepted": True,
                    "device_uuid": device.uuid,
                    "sampled_at": sampled_at.isoformat(),
                    "snapshot_keys": sorted(item[0].tag_key for item in planned),
                    "monitor_written": monitor_written,
                }
                text = json.dumps(result, ensure_ascii=False, sort_keys=True)
                if key:
                    await KuaiiotIngestDedup.create(
                        tenant_id=tenant_id,
                        device_id=device.id,
                        idempotency_key=key,
                        response_json=text,
                    )
        except IntegrityError:
            if key:
                stored = await IngestService._stored_response(tenant_id, device.id, key)
                if stored is not None:
                    return stored
            raise
        return json.loads(text)

    @staticmethod
    async def _apply_events(
        tenant_id: int,
        device: KuaiiotDevice,
        events: list,
        sampled_at: datetime,
    ) -> list[str]:
        defined = await _defined_events(tenant_id, device)
        accepted: list[str] = []
        seen: set[str] = set()
        for raw in events:
            if not isinstance(raw, dict):
                continue
            event_key = str(raw.get("event_key") or "").strip()
            if not event_key or event_key not in defined or event_key in seen:
                continue
            seen.add(event_key)
            definition = defined[event_key]
            severity = _event_severity(definition, raw)
            message = _event_message(definition, raw, event_key)
            token = device.device_token or ""
            if token and token in message:
                message = message.replace(token, "").strip() or event_key
            message = _mask_secret_pairs(message)
            accepted.append(event_key)
            alerted = severity in _ALERT_SEVERITIES
            if alerted:
                await KuaiiotAlert.create(
                    tenant_id=tenant_id,
                    rule_id=None,
                    device_id=device.id,
                    equipment_uuid=device.equipment_uuid,
                    tag_key=event_key,
                    severity=severity[:20],
                    message=message,
                    status="open",
                    triggered_at=sampled_at,
                )
            await MessageLogService.append(
                tenant_id=tenant_id,
                device_id=device.id,
                direction="in",
                msg_type="event",
                payload={"event_key": event_key, "severity": severity, "message": message},
                result="alerted" if alerted else "recorded",
                forbidden_values=(device.device_token,),
            )
        return accepted

    @staticmethod
    async def _bound_equipment(tenant_id: int, equipment_uuid: Optional[str]) -> Optional[Equipment]:
        text = (equipment_uuid or "").strip()
        if not text:
            return None
        try:
            return await EquipmentService.get_equipment_by_uuid(tenant_id, text)
        except NotFoundError as exc:
            raise ValidationError("绑定设备不属于当前租户") from exc

    @staticmethod
    async def _upsert_snapshot(
        tenant_id: int,
        device_id: int,
        tag_key: str,
        value_text: Optional[str],
        value_number: Optional[Decimal],
        value_bool: Optional[bool],
        sampled_at: datetime,
    ) -> None:
        row = await KuaiiotTagSnapshot.filter(
            tenant_id=tenant_id,
            device_id=device_id,
            tag_key=tag_key,
        ).first()
        if row is None:
            await KuaiiotTagSnapshot.create(
                tenant_id=tenant_id,
                device_id=device_id,
                tag_key=tag_key,
                value_text=value_text,
                value_number=value_number,
                value_bool=value_bool,
                quality="good",
                sampled_at=sampled_at,
            )
            return
        row.value_text = value_text
        row.value_number = value_number
        row.value_bool = value_bool
        row.quality = "good"
        row.sampled_at = sampled_at
        row.deleted_at = None
        await row.save(
            update_fields=[
                "value_text",
                "value_number",
                "value_bool",
                "quality",
                "sampled_at",
                "deleted_at",
                "updated_at",
            ]
        )

    @staticmethod
    async def _maybe_insert_monitor(
        tenant_id: int,
        equipment: Equipment,
        fields: dict[str, Any],
        sampled_at: datetime,
        server_now: datetime,
    ) -> bool:
        locked = await Equipment.filter(
            tenant_id=tenant_id,
            id=equipment.id,
            deleted_at__isnull=True,
        ).select_for_update().first()
        if locked is None:
            return False
        latest = await EquipmentStatusMonitor.filter(
            tenant_id=tenant_id,
            equipment_uuid=equipment.uuid,
            data_source=SENSOR_DATA_SOURCE,
            deleted_at__isnull=True,
        ).order_by("-created_at").first()
        blocked = await IngestService._writeback_blocked(tenant_id, equipment)
        if blocked and latest is None:
            return False
        if latest is not None:
            elapsed = _aware(server_now) - _aware(latest.created_at)
            if elapsed < timedelta(seconds=THROTTLE_SECONDS):
                return False
        if blocked:
            status_value = latest.status
            is_online = latest.is_online
        else:
            status_value = (
                normalize_equipment_status(fields.get("status"))
                if "status" in fields
                else MONITOR_STATUS_WHEN_ABSENT
            )
            is_online = fields["is_online"] if "is_online" in fields else True
        await EquipmentStatusMonitor.create(
            tenant_id=tenant_id,
            equipment_id=equipment.id,
            equipment_uuid=equipment.uuid,
            equipment_code=equipment.code,
            equipment_name=equipment.name,
            status=status_value,
            is_online=is_online,
            temperature=fields.get("temperature"),
            pressure=fields.get("pressure"),
            vibration=fields.get("vibration"),
            other_parameters=fields.get("other_parameters"),
            data_source=SENSOR_DATA_SOURCE,
            monitored_at=sampled_at,
        )
        return True

    @staticmethod
    async def _writeback_blocked(tenant_id: int, equipment: Equipment) -> bool:
        if equipment.status in BLOCKED_EQUIPMENT_STATUSES:
            return True
        if await EquipmentFault.filter(
            tenant_id=tenant_id,
            equipment_uuid=equipment.uuid,
            status__in=list(OPEN_FAULT_STATUSES),
            deleted_at__isnull=True,
        ).exists():
            return True
        return await EquipmentRepair.filter(
            tenant_id=tenant_id,
            equipment_uuid=equipment.uuid,
            status__in=list(OPEN_REPAIR_STATUSES),
            deleted_at__isnull=True,
        ).exists()
