"""云侧订阅客户自备 Broker。不内置 Broker，不改边缘 Agent。"""

from __future__ import annotations

from typing import Any, Optional
import asyncio
import hashlib
import json
import ssl
import uuid
from datetime import timedelta
from tortoise.expressions import Q
from core.utils.timezone_utils import resolve_business_datetime

from apps.kuaiiot.models.connection import KuaiiotConnection
from apps.kuaiiot.services.platform_telemetry import TOPIC_FIELD, deliver_registered_telemetry, normalize_mqtt
from infra.domain.tenant_context import unscoped, with_tenant
from apps.kuaiiot.services.connection_runtime import connection_is_active, resolve_core_connection


class MqttSubscriberService:
    _tasks: dict[tuple[int, int], tuple[str, asyncio.Task]] = {}
    _health: dict[tuple[int, int], str] = {}
    _owner = str(uuid.uuid4())
    _reload_lock = asyncio.Lock()

    @staticmethod
    async def consume(connection: KuaiiotConnection, config: dict, *, expected_owner: str | None = None) -> None:
        import aiomqtt
        async with aiomqtt.Client(
            hostname=config["host"], port=int(config.get("port", 1883)),
            username=config.get("username") or None, password=config.get("password") or None,
            tls_context=ssl.create_default_context() if config.get("use_tls") else None,
            identifier=f"kuaiiot-{connection.tenant_id}-{connection.id}",
            max_queued_incoming_messages=1000,
        ) as client:
            await client.subscribe(connection.config[TOPIC_FIELD], qos=1)
            MqttSubscriberService._health[(connection.tenant_id, connection.id)] = "connected"
            async for message in client.messages:
                try:
                    payload = json.loads(message.payload)
                    async with with_tenant(int(connection.tenant_id), reason="MQTT 入站按订阅所属租户处理"):
                        if expected_owner is not None:
                            owned = await KuaiiotConnection.filter(id=connection.id, tenant_id=connection.tenant_id, subscriber_owner=expected_owner, subscriber_lease_until__gt=resolve_business_datetime(), is_enabled=True, deleted_at__isnull=True).exists()
                            if not owned:
                                return
                        await normalize_mqtt(connection, str(message.topic), payload)
                except (ValueError, TypeError):
                    continue

    @staticmethod
    async def _listen(connection: KuaiiotConnection, config: dict) -> None:
        while True:
            try:
                await MqttSubscriberService.consume(connection, config, expected_owner=MqttSubscriberService._owner)
            except asyncio.CancelledError:
                raise
            except Exception:
                MqttSubscriberService._health[(connection.tenant_id, connection.id)] = "disconnected"
            await asyncio.sleep(5)

    @staticmethod
    async def _renew(connection: KuaiiotConnection, consumer: asyncio.Task) -> None:
        while True:
            await asyncio.sleep(20)
            async with with_tenant(int(connection.tenant_id), reason="续期 MQTT 所属租户订阅租约"):
                updated = await KuaiiotConnection.filter(id=connection.id, subscriber_owner=MqttSubscriberService._owner, is_enabled=True, deleted_at__isnull=True).update(subscriber_lease_until=resolve_business_datetime() + timedelta(seconds=60), health_status=MqttSubscriberService._health.get((connection.tenant_id, connection.id), "unknown"), last_health_at=resolve_business_datetime())
                if not updated or not await connection_is_active(connection):
                    consumer.cancel()
                    return

    @staticmethod
    async def _owned_listen(connection, config):
        consumer = asyncio.create_task(MqttSubscriberService._listen(connection, config))
        renewal = asyncio.create_task(MqttSubscriberService._renew(connection, consumer))
        try:
            done, _ = await asyncio.wait({consumer, renewal}, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            consumer.cancel()
            renewal.cancel()
            await asyncio.gather(consumer, renewal, return_exceptions=True)
            async with with_tenant(int(connection.tenant_id), reason="释放 MQTT 订阅租约"):
                await KuaiiotConnection.filter(id=connection.id, subscriber_owner=MqttSubscriberService._owner).update(subscriber_owner=None, subscriber_lease_until=None)
    @staticmethod
    def _extract_device_token(topic: str) -> Optional[str]:
        text = (topic or "").strip().strip("/")
        if not text:
            return None
        part = text.split("/")[-1].strip()
        return part or None

    @staticmethod
    def _resolve_format(payload_format: str, payload_data: Any) -> str:
        """识别报文格式（上游三易产线适配兼容）。"""
        from apps.kuaiiot.services.sanyi_line_adapter import is_sanyi_line_payload

        if payload_format not in {"auto", "kuaiiot", "sanyi_line"}:
            return "kuaiiot"
        if payload_format == "sanyi_line":
            return "sanyi_line"
        if payload_format == "kuaiiot":
            return "kuaiiot"
        if is_sanyi_line_payload(payload_data):
            return "sanyi_line"
        return "kuaiiot"

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
    async def reload(force_restart: bool = False) -> dict[str, int]:
        async with MqttSubscriberService._reload_lock:
            return await MqttSubscriberService._reload(force_restart=force_restart)

    @staticmethod
    async def _reload(force_restart: bool = False) -> dict[str, int]:
        """对齐本进程订阅；返回配置对齐数，连接结果另查健康状态。"""
        if force_restart:
            for key, (_, task) in list(MqttSubscriberService._tasks.items()):
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            MqttSubscriberService._tasks.clear()
            MqttSubscriberService._health.clear()
        async with unscoped(reason="订阅对齐只读取各租户 MQTT 连接的 topic", resource="KuaiiotConnection"):
            rows = await KuaiiotConnection.filter(
                connection_type__iexact="mqtt",
                is_enabled=True,
                deleted_at__isnull=True,
            )
        aligned = 0
        desired = set()
        for row in rows:
            async with with_tenant(int(row.tenant_id), reason="订阅配置核对所属租户公共连接"):
                if not await connection_is_active(row):
                    continue
                core = await resolve_core_connection(row)
                core_config = core.get_config()
            config = row.config if isinstance(row.config, dict) else {}
            topic = config.get(TOPIC_FIELD)
            if isinstance(topic, str) and topic.strip():
                aligned += 1
                key = (int(row.tenant_id), row.id)
                desired.add(key)
                fingerprint = hashlib.sha256(json.dumps([core_config, config], sort_keys=True).encode()).hexdigest()
                previous = MqttSubscriberService._tasks.get(key)
                if previous is not None and (previous[0] != fingerprint or previous[1].done()):
                    previous[1].cancel()
                    await asyncio.gather(previous[1], return_exceptions=True)
                    previous = None
                if previous is None:
                    async with with_tenant(int(row.tenant_id), reason="原子领取 MQTT 订阅租约"):
                        claimed = await KuaiiotConnection.filter(
                            Q(subscriber_owner=MqttSubscriberService._owner) | Q(subscriber_lease_until__isnull=True) | Q(subscriber_lease_until__lt=resolve_business_datetime()),
                            id=row.id, tenant_id=row.tenant_id,
                        ).update(subscriber_owner=MqttSubscriberService._owner, subscriber_lease_until=resolve_business_datetime() + timedelta(seconds=60))
                    if not claimed:
                        continue
                    MqttSubscriberService._health[key] = "connecting"
                    MqttSubscriberService._tasks[key] = (fingerprint, asyncio.create_task(MqttSubscriberService._owned_listen(row, core_config)))
        for key in list(MqttSubscriberService._tasks):
            if key not in desired:
                _, task = MqttSubscriberService._tasks.pop(key)
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                MqttSubscriberService._health.pop(key, None)
        return {"subscriptions_aligned": aligned}

    @staticmethod
    async def start_all() -> None:
        await MqttSubscriberService.reload()

    @staticmethod
    async def stop_all() -> None:
        tasks = [task for _, task in MqttSubscriberService._tasks.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        MqttSubscriberService._tasks.clear()
        MqttSubscriberService._health.clear()
