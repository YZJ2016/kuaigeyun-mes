"""平台遥测收成现有入站。未登记设备不入库。"""

from __future__ import annotations

from typing import Any, Optional

from apps.kuaiiot.models.connection import KuaiiotConnection
from apps.kuaiiot.schemas.ingest import IngestBody
from apps.kuaiiot.services.ingest_service import IngestService
from infra.exceptions.exceptions import AuthenticationError

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
    wanted = [part for part in pattern.strip().split("/") if part]
    actual = [part for part in (topic or "").strip().split("/") if part]
    if not wanted or not actual or "#" in wanted[:-1]:
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


async def ingest_mapped_payload(connection: KuaiiotConnection, payload: dict[str, Any]) -> dict[str, bool]:
    """按 config 的 JSON 路径收成 IngestBody，只调用 IngestService.ingest。"""
    config = _config_dict(connection)
    token = _text(_path_value(payload, _configured_path(config, DEVICE_TOKEN_PATH)))
    if not token:
        return {"stored": False}
    tags = _scrub(_path_value(payload, _configured_path(config, TAGS_PATH)))
    if not isinstance(tags, dict):
        tags = {}
    body = IngestBody(
        tags=tags,
        events=_events(_path_value(payload, _configured_path(config, EVENTS_PATH))),
        timestamp=_text(_path_value(payload, _configured_path(config, TIMESTAMP_PATH))),
        idempotency_key=_text(_path_value(payload, _configured_path(config, IDEMPOTENCY_KEY_PATH)), 128),
    )
    try:
        await IngestService.ingest(token, body)
    except AuthenticationError:
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
    body = IngestBody(
        tags=dict(tags or {}),
        events=list(events or []),
        timestamp=timestamp,
        idempotency_key=idempotency_key,
    )
    try:
        await IngestService.ingest(device_token, body)
    except AuthenticationError:
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
    return {"stored": stored, "skipped_unregistered": skipped}
