"""MQTT 连接源最近消息：进程内缓冲 + 数据库持久化（API/Worker 跨进程可读）。"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Deque, Optional
from uuid import uuid4

from loguru import logger

from apps.kuaiiot.services.mqtt_device_discovery import compact_payload_for_store

# 每个连接保留条数；单条 payload 预览最大字符
MAX_MESSAGES_PER_CONNECTION = 50
MAX_PAYLOAD_CHARS = 20000


class MqttMessageBuffer:
    _lock = Lock()
    _buffers: dict[int, Deque[dict[str, Any]]] = {}

    @classmethod
    def _truncate_payload(cls, payload: Any) -> Any:
        return compact_payload_for_store(payload, max_chars=MAX_PAYLOAD_CHARS)

    @classmethod
    def append(
        cls,
        connection_id: int,
        *,
        topic: str,
        qos: int = 0,
        retained: bool = False,
        payload: Any = None,
        payload_format: str = "unknown",
        ingest_summary: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> dict[str, Any]:
        item = {
            "uuid": str(uuid4()),
            "topic": topic,
            "qos": qos,
            "retained": retained,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "payload": cls._truncate_payload(payload),
            "payload_format": payload_format,
            "ingest_summary": ingest_summary or {},
            "error": error,
        }
        with cls._lock:
            buf = cls._buffers.get(connection_id)
            if buf is None:
                buf = deque(maxlen=MAX_MESSAGES_PER_CONNECTION)
                cls._buffers[connection_id] = buf
            buf.appendleft(item)
        return item

    @classmethod
    def list_messages(cls, connection_id: int, *, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(limit, MAX_MESSAGES_PER_CONNECTION))
        with cls._lock:
            buf = cls._buffers.get(connection_id)
            if not buf:
                return []
            return list(buf)[:limit]

    @classmethod
    async def persist(
        cls,
        tenant_id: int,
        connection_id: int,
        *,
        topic: str,
        qos: int = 0,
        retained: bool = False,
        payload: Any = None,
        payload_format: str = "unknown",
        ingest_summary: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> dict[str, Any]:
        item = cls.append(
            connection_id,
            topic=topic,
            qos=qos,
            retained=retained,
            payload=payload,
            payload_format=payload_format,
            ingest_summary=ingest_summary,
            error=error,
        )
        try:
            from apps.kuaiiot.models.iot import IotConnectionMessage

            await IotConnectionMessage.create(
                tenant_id=tenant_id,
                connection_id=connection_id,
                topic=topic[:255],
                qos=qos,
                retained=retained,
                payload=item["payload"],
                payload_format=(payload_format or "unknown")[:30],
                ingest_summary=ingest_summary or {},
                error_message=error,
            )
            keep_ids = (
                await IotConnectionMessage.filter(
                    tenant_id=tenant_id,
                    connection_id=connection_id,
                    deleted_at__isnull=True,
                )
                .order_by("-created_at")
                .limit(MAX_MESSAGES_PER_CONNECTION)
                .values_list("id", flat=True)
            )
            if keep_ids:
                await (
                    IotConnectionMessage.filter(
                        tenant_id=tenant_id,
                        connection_id=connection_id,
                        deleted_at__isnull=True,
                    )
                    .exclude(id__in=list(keep_ids))
                    .delete()
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "kuaiiot persist connection message failed connection_id={}: {}",
                connection_id,
                exc,
            )
        try:
            from apps.kuaiiot.services.mqtt_device_discovery import MqttDeviceDiscoveryService

            await MqttDeviceDiscoveryService.upsert_from_payload(
                tenant_id,
                connection_id,
                payload,
                topic=topic,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "kuaiiot upsert discovered mqtt devices failed connection_id={}: {}",
                connection_id,
                exc,
            )
        return item

    @classmethod
    async def list_persisted(cls, tenant_id: int, connection_id: int, *, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(limit, MAX_MESSAGES_PER_CONNECTION))
        try:
            from apps.kuaiiot.models.iot import IotConnectionMessage

            rows = (
                await IotConnectionMessage.filter(
                    tenant_id=tenant_id,
                    connection_id=connection_id,
                    deleted_at__isnull=True,
                )
                .order_by("-created_at")
                .limit(limit)
            )
            if rows:
                return [
                    {
                        "uuid": row.uuid,
                        "topic": row.topic,
                        "qos": row.qos,
                        "retained": row.retained,
                        "received_at": row.created_at.isoformat() if row.created_at else None,
                        "payload": row.payload,
                        "payload_format": row.payload_format,
                        "ingest_summary": row.ingest_summary or {},
                        "error": row.error_message,
                    }
                    for row in rows
                ]
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "kuaiiot list connection messages failed connection_id={}: {}",
                connection_id,
                exc,
            )
        return cls.list_messages(connection_id, limit=limit)

    @classmethod
    def clear(cls, connection_id: int) -> None:
        with cls._lock:
            cls._buffers.pop(connection_id, None)
