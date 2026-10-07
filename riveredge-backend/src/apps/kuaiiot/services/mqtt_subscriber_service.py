"""云侧订阅客户自备 Broker。不内置 Broker，不改边缘 Agent。"""

from __future__ import annotations

from typing import Any, Optional

from apps.kuaiiot.models.connection import KuaiiotConnection
from apps.kuaiiot.services.platform_telemetry import TOPIC_FIELD, deliver_registered_telemetry
from infra.domain.tenant_context import unscoped, with_tenant
from apps.kuaiiot.services.connection_runtime import connection_is_active


class MqttSubscriberService:
    @staticmethod
    def _extract_device_token(topic: str) -> Optional[str]:
        text = (topic or "").strip().strip("/")
        if not text:
            return None
        part = text.split("/")[-1].strip()
        return part or None

    @staticmethod
    async def accept_topic_telemetry(
        topic: str,
        *,
        tags: Optional[dict[str, Any]] = None,
        events: Optional[list[dict[str, Any]]] = None,
        timestamp: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, bool]:
        token = MqttSubscriberService._extract_device_token(topic)
        if not token:
            return {"stored": False}
        return await deliver_registered_telemetry(
            token,
            tags=tags,
            events=events,
            timestamp=timestamp,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    async def reload() -> dict[str, int]:
        """按 config.topic 统计可对齐的订阅。不连接 Broker，不读取口令。"""
        async with unscoped(reason="订阅对齐只读取各租户 MQTT 连接的 topic", resource="KuaiiotConnection"):
            rows = await KuaiiotConnection.filter(
                connection_type__iexact="mqtt",
                is_enabled=True,
                deleted_at__isnull=True,
            )
        aligned = 0
        for row in rows:
            async with with_tenant(int(row.tenant_id), reason="订阅配置核对所属租户公共连接"):
                if not await connection_is_active(row):
                    continue
            config = row.config if isinstance(row.config, dict) else {}
            topic = config.get(TOPIC_FIELD)
            if isinstance(topic, str) and topic.strip():
                aligned += 1
        return {"subscriptions_aligned": aligned}

    @staticmethod
    async def start_all() -> None:
        await MqttSubscriberService.reload()

    @staticmethod
    async def stop_all() -> None:
        return None
