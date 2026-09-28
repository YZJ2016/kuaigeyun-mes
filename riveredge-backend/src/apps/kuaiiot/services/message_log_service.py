"""消息追踪。payload 不写入设备凭据或 Influx 凭据。"""

from __future__ import annotations

from typing import Any, Optional

from apps.kuaiiot.models.message_log import KuaiiotMessageLog
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
    async def append(
        *,
        tenant_id: int,
        device_id: int,
        direction: str,
        msg_type: str,
        payload: Optional[dict],
        result: str,
        error_message: Optional[str] = None,
        forbidden_values: tuple[str, ...] = (),
    ) -> KuaiiotMessageLog:
        way = (direction or "").strip()
        kind = (msg_type or "").strip()
        outcome = (result or "").strip()
        if way not in {"in", "out"} or not kind or not outcome:
            raise ValidationError("消息追踪字段无效")
        secrets = tuple(item for item in forbidden_values if item)
        return await KuaiiotMessageLog.create(
            tenant_id=tenant_id,
            device_id=device_id,
            direction=way,
            msg_type=kind[:30],
            payload=sanitize_payload(payload or {}, secrets),
            result=outcome[:20],
            error_message=_scrub_text(error_message, secrets),
        )

    @staticmethod
    async def list_messages(tenant_id: int, device_id: Optional[int] = None) -> list[KuaiiotMessageLog]:
        tid = _require_tenant(tenant_id)
        query = KuaiiotMessageLog.filter(tenant_id=tid, deleted_at__isnull=True)
        if device_id is not None:
            query = query.filter(device_id=device_id)
        return await query.order_by("-id").limit(100)
