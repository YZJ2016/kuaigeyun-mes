"""平台遥测收成现有入站。未登记设备不入库。"""

from __future__ import annotations

from typing import Any, Optional
import hashlib

from pydantic import ValidationError as PydanticValidationError

from apps.kuaiiot.models.connection import KuaiiotConnection
from apps.kuaiiot.schemas.ingest import IngestBody
from apps.kuaiiot.services.ingest_service import IngestService
from apps.kuaiiot.services.connection_runtime import connection_is_active, resolve_core_connection
from apps.kuaiiot.models.device import KuaiiotDevice
from core.services.integration.iot_platform_client import PlatformClient, sample_timestamp
from infra.domain.tenant_context import with_tenant, unscoped
from infra.exceptions.exceptions import AuthenticationError, ValidationError

# KuaiiotConnection.config 字段名。topic 只用于 mqtt。
TOPIC_FIELD = "topic"
DEVICE_TOKEN_PATH = "device_token_path"
TAGS_PATH = "tags_path"
EVENTS_PATH = "events_path"
TIMESTAMP_PATH = "timestamp_path"
IDEMPOTENCY_KEY_PATH = "idempotency_key_path"
SECRET_CONFIG_KEYS = frozenset({"password", "passwd", "broker_password", "mqtt_password"})
SPEC_ADDRESS_SECTION = "平台地址未进入仓库"


def load_platform_records() -> list[dict[str, Any]]:
    """遥测地址为空，不发请求。说明见 spec 156「平台地址未进入仓库」。"""
    return []


def _config_dict(connection: KuaiiotConnection) -> dict[str, Any]:
    raw = connection.config
    return raw if isinstance(raw, dict) else {}


def _configured_path(config: dict[str, Any], key: str) -> str:
    value = config.get(key)
    if not isinstance(value, str):
        return ""
    return value.strip()


def _secret_key(name: str) -> bool:
    return name.strip().lower() in SECRET_CONFIG_KEYS


def _path_value(payload: Any, path: str) -> Any:
    if not path or not isinstance(payload, dict):
        return None
    current: Any = payload
    for part in path.split("."):
        if _secret_key(part):
            return None
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if _secret_key(name):
                continue
            cleaned[name] = _scrub(item)
        return cleaned
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def _text(value: Any, limit: Optional[int] = None) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if limit is not None and len(text) > limit:
        return None
    return text


def _events(value: Any) -> list[dict[str, Any]]:
    scrubbed = _scrub(value)
    if not isinstance(scrubbed, list):
        return []
    return [item for item in scrubbed if isinstance(item, dict)]


def topic_matches(pattern: str, topic: str) -> bool:
    # 空层是真实层级：保留空段逐层比较，a//b 不等于 a/b
    wanted = pattern.strip().split("/")
    actual = (topic or "").strip().split("/")
    if not pattern.strip() or not (topic or "").strip() or "#" in wanted[:-1]:
        return False
    index = 0
    for part in wanted:
        if part == "#":
            return True
        if index >= len(actual):
            return False
        if part != "+" and part != actual[index]:
            return False
        index += 1
    return index == len(actual)


async def ingest_mapped_payload(connection: KuaiiotConnection, payload: dict[str, Any]) -> dict[str, Any]:
    """按 config 的 JSON 路径收成 IngestBody，只调用 IngestService.ingest。"""
    async with with_tenant(int(connection.tenant_id), reason="归一化读取数采连接所属租户"):
        if not await connection_is_active(connection):
            return {"stored": False}
    config = _config_dict(connection)
    token = _text(_path_value(payload, _configured_path(config, DEVICE_TOKEN_PATH)))
    if not token:
        return {"stored": False}
    tags = _scrub(_path_value(payload, _configured_path(config, TAGS_PATH)))
    if not isinstance(tags, dict):
        tags = {}
    raw_key = _path_value(payload, _configured_path(config, IDEMPOTENCY_KEY_PATH))
    idempotency_key = _text(raw_key, 128)
    if idempotency_key is None and isinstance(raw_key, str) and raw_key.strip():
        # 幂等键超 128 限长：整条拒收，不静默降级为无幂等键入库
        return {"stored": False, "reason": "幂等键超限"}
    try:
        body = IngestBody(
            tags=tags,
            events=_events(_path_value(payload, _configured_path(config, EVENTS_PATH))),
            timestamp=_text(_path_value(payload, _configured_path(config, TIMESTAMP_PATH))),
            idempotency_key=idempotency_key,
        )
        device = await IngestService._match_device(token)
        if device.tenant_id != connection.tenant_id or device.connection_id != connection.id:
            return {"stored": False}
        await IngestService.ingest(token, body)
    except (AuthenticationError, ValidationError, PydanticValidationError):
        return {"stored": False}
    return {"stored": True}


async def normalize_mqtt(
    connection: KuaiiotConnection,
    message_topic: str,
    payload: dict[str, Any],
) -> dict[str, bool]:
    """读该连接 config 的 topic 与 JSON 路径，收成 IngestBody 后只调用 IngestService.ingest。"""
    if (connection.connection_type or "").strip().lower() != "mqtt":
        return {"stored": False}
    if not isinstance(payload, dict):
        return {"stored": False}
    pattern = _config_dict(connection).get(TOPIC_FIELD)
    if not isinstance(pattern, str) or not topic_matches(pattern, message_topic):
        return {"stored": False}
    return await ingest_mapped_payload(connection, payload)


async def normalize_thingsboard(connection: KuaiiotConnection, payload: dict[str, Any]) -> dict[str, bool]:
    """读该连接 config 的 JSON 路径后入站。不请求遥测地址。说明见 spec 156「平台地址未进入仓库」。"""
    if (connection.connection_type or "").strip().lower() != "thingsboard":
        return {"stored": False}
    if not isinstance(payload, dict):
        return {"stored": False}
    return await ingest_mapped_payload(connection, payload)


async def normalize_jetlinks(connection: KuaiiotConnection, payload: dict[str, Any]) -> dict[str, bool]:
    """读该连接 config 的 JSON 路径后入站。不请求遥测地址。说明见 spec 156「平台地址未进入仓库」。"""
    if (connection.connection_type or "").strip().lower() != "jetlinks":
        return {"stored": False}
    if not isinstance(payload, dict):
        return {"stored": False}
    return await ingest_mapped_payload(connection, payload)


async def deliver_registered_telemetry(
    device_token: str,
    *,
    tags: Optional[dict[str, Any]] = None,
    events: Optional[list[dict[str, Any]]] = None,
    timestamp: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict[str, bool]:
    try:
        body = IngestBody(
            tags=dict(tags or {}),
            events=list(events or []),
            timestamp=timestamp,
            idempotency_key=idempotency_key,
        )
        await IngestService.ingest(device_token, body)
    except (AuthenticationError, ValidationError, PydanticValidationError):
        return {"stored": False}
    return {"stored": True}


async def pull_registered_telemetry() -> dict[str, int]:
    """只消费 load_platform_records。说明见 spec 156「平台地址未进入仓库」。"""
    stored = 0
    skipped = 0
    for item in load_platform_records():
        outcome = await deliver_registered_telemetry(
            str(item.get("device_token") or ""),
            tags=item.get("tags") if isinstance(item.get("tags"), dict) else {},
            events=item.get("events") if isinstance(item.get("events"), list) else [],
            timestamp=item.get("timestamp") if isinstance(item.get("timestamp"), str) else None,
            idempotency_key=item.get("idempotency_key") if isinstance(item.get("idempotency_key"), str) else None,
        )
        if outcome["stored"]:
            stored += 1
        else:
            skipped += 1
    async with unscoped(reason="扫描已登记平台遥测连接", resource="KuaiiotConnection"):
        connections = await KuaiiotConnection.filter(connection_type__in=["thingsboard", "jetlinks"], is_enabled=True, deleted_at__isnull=True)
    for connection in connections:
        async with with_tenant(int(connection.tenant_id), reason="拉取所属租户平台已登记设备"):
            try:
                core = await resolve_core_connection(connection)
                config = core.get_config()
                if not config.get("base_url"):
                    continue
                devices = await KuaiiotDevice.filter(tenant_id=connection.tenant_id, connection_id=connection.id, deleted_at__isnull=True)
                async with PlatformClient(connection.connection_type, config) as client:
                    for device in devices:
                        try:
                            for sample in await client.telemetry(device.external_device_id):
                                key = hashlib.sha256(f"{connection.id}:{device.id}:{sample['tag_key']}:{sample['timestamp']}".encode()).hexdigest()
                                await IngestService.ingest(device.device_token, IngestBody(tags={sample["tag_key"]: sample["value"]}, timestamp=sample_timestamp(sample["timestamp"]), idempotency_key=key))
                                stored += 1
                        except (ValidationError, ValueError, OverflowError):
                            skipped += 1
            except ValidationError:
                skipped += 1
    return {"stored": stored, "skipped_unregistered": skipped}
