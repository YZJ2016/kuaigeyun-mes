"""星数采设备消息追踪日志。payload 不写入设备凭据或 Influx 凭据。"""

from __future__ import annotations

import json
from typing import Any, Optional

from apps.kuaiiot.constants import (
    MESSAGE_DIRECTIONS,
    MESSAGE_LOG_PAYLOAD_MAX,
    MESSAGE_RESULTS,
    MESSAGE_TYPES,
)
from apps.kuaiiot.models.iot import IotMessageLog
from infra.domain.tenant_context import TenantContextError, get_current_tenant_id
from infra.exceptions.exceptions import ValidationError

_SECRET_PARTS = ("token", "password", "passwd", "secret", "authorization", "cipher")


def _require_tenant(explicit: int) -> int:
    current = get_current_tenant_id()
    if current is None:
        raise TenantContextError("组织上下文未设置")
    if int(current) != int(explicit):
        raise ValidationError("租户上下文不匹配")
    return int(current)


def _secret_key(key: str) -> bool:
    lowered = key.strip().lower()
    return any(part in lowered for part in _SECRET_PARTS)


def _scrub_text(value: Optional[str], forbidden: tuple[str, ...]) -> Optional[str]:
    if value is None:
        return None
    text = value
    for secret in forbidden:
        if secret:
            text = text.replace(secret, "")
    text = text.strip()
    return text or None


def sanitize_payload(value: Any, forbidden: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if _secret_key(name):
                continue
            cleaned[name] = sanitize_payload(item, forbidden)
        return cleaned
    if isinstance(value, list):
        return [sanitize_payload(item, forbidden) for item in value]
    if isinstance(value, str):
        return _scrub_text(value, forbidden) or ""
    return value


class MessageLogService:
    @staticmethod
    def _truncate_payload(payload: Any) -> Any:
        if payload is None:
            return None
        try:
            text = json.dumps(payload, ensure_ascii=False, default=str)
        except TypeError:
            text = str(payload)
        if len(text) <= MESSAGE_LOG_PAYLOAD_MAX:
            return payload if isinstance(payload, (dict, list)) else {"value": text}
        return {"truncated": True, "preview": text[:MESSAGE_LOG_PAYLOAD_MAX]}

    @staticmethod
    async def append(
        tenant_id: int,
        device_id: int,
        *,
        direction: str,
        msg_type: str,
        result: str,
        payload: Any = None,
        error_message: Optional[str] = None,
        forbidden_values: tuple[str, ...] = (),
    ) -> IotMessageLog:
        if direction not in MESSAGE_DIRECTIONS:
            raise ValidationError(f"无效 direction: {direction}")
        if msg_type not in MESSAGE_TYPES:
            raise ValidationError(f"无效 msg_type: {msg_type}")
        if result not in MESSAGE_RESULTS:
            raise ValidationError(f"无效 result: {result}")
        secrets = tuple(item for item in forbidden_values if item)
        if secrets:
            payload = sanitize_payload(payload, secrets)
            error_message = _scrub_text(error_message, secrets)
        return await IotMessageLog.create(
            tenant_id=tenant_id,
            device_id=device_id,
            direction=direction,
            msg_type=msg_type,
            payload=MessageLogService._truncate_payload(payload),
            result=result,
            error_message=error_message,
        )

    @staticmethod
    async def list_logs(
        tenant_id: int,
        device_id: int,
        *,
        page: int = 1,
        page_size: int = 20,
        direction: Optional[str] = None,
        msg_type: Optional[str] = None,
    ) -> tuple[list[IotMessageLog], int]:
        query = IotMessageLog.filter(
            tenant_id=tenant_id,
            device_id=device_id,
            deleted_at__isnull=True,
        )
        if direction:
            query = query.filter(direction=direction)
        if msg_type:
            query = query.filter(msg_type=msg_type)
        total = await query.count()
        items = await query.order_by("-created_at").offset((page - 1) * page_size).limit(page_size)
        return items, total

    @staticmethod
    async def list_messages(tenant_id: int, device_id: Optional[int] = None) -> list[IotMessageLog]:
        tid = _require_tenant(tenant_id)
        query = IotMessageLog.filter(tenant_id=tid, deleted_at__isnull=True)
        if device_id is not None:
            query = query.filter(device_id=device_id)
        return await query.order_by("-id").limit(100)
