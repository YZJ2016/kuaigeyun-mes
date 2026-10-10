"""快数采连接源服务。"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from apps.kuaiiot.constants import CONNECTION_TYPES
from apps.kuaiiot.models.iot import IotConnection
from apps.kuaiiot.schemas.iot import ConnectionCreate, ConnectionUpdate
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import NotFoundError, ValidationError


class ConnectionService:
    @staticmethod
    async def _reload_mqtt_subscribers(*, force_restart: bool = True) -> None:
        """配置变更时通知 Worker 重建订阅，避免 API 进程自己订阅导致 Client ID 互踢。"""
        from loguru import logger

        try:
            from core.tasks.taskiq_app import kuaiiot_mqtt_reload_tick

            await kuaiiot_mqtt_reload_tick.kiq(force_restart=force_restart)
        except Exception as exc:  # pragma: no cover
            logger.warning("kuaiiot mqtt reload enqueue failed: {}", exc)

    @staticmethod
    async def list_connections(
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        q: Optional[str] = None,
        connection_type: Optional[str] = None,
    ) -> tuple[list[IotConnection], int]:
        query = IotConnection.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if q:
            query = query.filter(name__icontains=q)
        if connection_type:
            query = query.filter(connection_type=connection_type)
        total = await query.count()
        items = await query.order_by("-created_at", "-id").offset((page - 1) * page_size).limit(page_size)
        return items, total

    @staticmethod
    async def get_by_uuid(tenant_id: int, uuid: str) -> IotConnection:
        item = await IotConnection.filter(
            tenant_id=tenant_id, uuid=uuid, deleted_at__isnull=True
        ).first()
        if not item:
            raise NotFoundError(f"连接源不存在: {uuid}")
        return item

    @staticmethod
    async def create(tenant_id: int, data: ConnectionCreate) -> IotConnection:
        if data.connection_type not in CONNECTION_TYPES:
            raise ValidationError(f"不支持的连接类型: {data.connection_type}")
        exists = await IotConnection.filter(
            tenant_id=tenant_id, code=data.code, deleted_at__isnull=True
        ).exists()
        if exists:
            raise ValidationError(f"连接编码已存在: {data.code}")
        item = await IotConnection.create(tenant_id=tenant_id, **data.model_dump())
        if item.connection_type == "mqtt":
            await ConnectionService._reload_mqtt_subscribers()
        return item

    @staticmethod
    async def update(tenant_id: int, uuid: str, data: ConnectionUpdate) -> IotConnection:
        item = await ConnectionService.get_by_uuid(tenant_id, uuid)
        was_mqtt = item.connection_type == "mqtt"
        payload = data.model_dump(exclude_unset=True)
        if "connection_type" in payload and payload["connection_type"] not in CONNECTION_TYPES:
            raise ValidationError(f"不支持的连接类型: {payload['connection_type']}")
        for key, value in payload.items():
            setattr(item, key, value)
        await item.save()
        if was_mqtt or item.connection_type == "mqtt":
            await ConnectionService._reload_mqtt_subscribers()
        return item

    @staticmethod
    async def delete(tenant_id: int, uuid: str) -> None:
        item = await ConnectionService.get_by_uuid(tenant_id, uuid)
        was_mqtt = item.connection_type == "mqtt"
        item.deleted_at = resolve_business_datetime()
        await item.save()
        if was_mqtt:
            await ConnectionService._reload_mqtt_subscribers()

    @staticmethod
    async def apply_health(
        item: IotConnection,
        *,
        healthy: bool,
        min_interval_seconds: int = 0,
        allow_downgrade: bool = True,
    ) -> IotConnection:
        """写入健康状态。MQTT 定时探测失败时 allow_downgrade=False，避免覆盖正在收数的连接。"""
        now = resolve_business_datetime()
        new_status = "healthy" if healthy else "unhealthy"
        if (
            min_interval_seconds > 0
            and item.health_status == new_status
            and item.last_health_at
            and item.last_health_at > now - timedelta(seconds=min_interval_seconds)
        ):
            return item
        if not healthy and not allow_downgrade and item.health_status == "healthy":
            return item
        item.health_status = new_status
        item.last_health_at = now
        await item.save()
        return item

    @staticmethod
    async def touch_health(tenant_id: int, uuid: str, healthy: bool) -> IotConnection:
        item = await ConnectionService.get_by_uuid(tenant_id, uuid)
        return await ConnectionService.apply_health(item, healthy=healthy)
