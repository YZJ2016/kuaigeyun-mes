"""快数采连接源服务。"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from apps.kuaiiot.constants import CONNECTION_TYPES
from apps.kuaiiot.models.iot import IotConnection
from apps.kuaiiot.schemas.iot import ConnectionCreate, ConnectionUpdate
from apps.kuaiiot.services.connection_runtime import validate_mapping, validate_type
from core.models.integration_config import IntegrationConfig
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
    async def _resolve_integration(
        tenant_id: int, integration_uuid: Optional[str], kind: str
    ) -> Optional[IntegrationConfig]:
        """数采连接绑定的公共连接：地址与凭据只放应用连接器，不落数采 config。"""
        if not integration_uuid:
            return None
        core = await IntegrationConfig.filter(
            uuid=str(integration_uuid), tenant_id=tenant_id, deleted_at__isnull=True
        ).first()
        if core is None:
            raise ValidationError("公共连接不存在或不属于当前租户")
        validate_type("http" if kind == "http_webhook" else kind, core.type)
        if not core.is_active:
            raise ValidationError("公共连接已停用")
        return core

    @staticmethod
    def _validate_mqtt_config(config: Optional[dict]) -> None:
        """订阅器只消费映射键与 config.topic，缺 topic 的连接不会订阅。"""
        validate_mapping(config)
        topic = (config or {}).get("topic")
        if not isinstance(topic, str) or not topic.strip():
            raise ValidationError("MQTT 连接必须配置订阅 Topic")

    @staticmethod
    async def _attach_integration_uuid(items: list[IotConnection]) -> None:
        ids = {item.integration_id for item in items if item.integration_id}
        if not ids:
            return
        cores = await IntegrationConfig.filter(id__in=list(ids), deleted_at__isnull=True)
        uuid_map = {core.id: core.uuid for core in cores}
        for item in items:
            item.integration_uuid = uuid_map.get(item.integration_id)

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
        await ConnectionService._attach_integration_uuid(items)
        return items, total

    @staticmethod
    async def get_by_uuid(tenant_id: int, uuid: str) -> IotConnection:
        item = await IotConnection.filter(
            tenant_id=tenant_id, uuid=uuid, deleted_at__isnull=True
        ).first()
        if not item:
            raise NotFoundError(f"连接源不存在: {uuid}")
        await ConnectionService._attach_integration_uuid([item])
        return item

    @staticmethod
    async def create(tenant_id: int, data: ConnectionCreate) -> IotConnection:
        kind = (data.connection_type or "").strip().lower()
        if kind not in CONNECTION_TYPES:
            raise ValidationError(f"不支持的连接类型: {data.connection_type}")
        exists = await IotConnection.filter(
            tenant_id=tenant_id, code=data.code, deleted_at__isnull=True
        ).exists()
        if exists:
            raise ValidationError(f"连接编码已存在: {data.code}")
        payload = data.model_dump()
        core = await ConnectionService._resolve_integration(tenant_id, payload.pop("integration_uuid", None), kind)
        if kind == "mqtt":
            if core is None:
                raise ValidationError("请选择同租户公共连接")
            ConnectionService._validate_mqtt_config(payload.get("config"))
        item = await IotConnection.create(
            tenant_id=tenant_id,
            integration_id=core.id if core else None,
            **payload,
        )
        await ConnectionService._attach_integration_uuid([item])
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
        if "integration_uuid" in payload:
            integration_uuid = payload.pop("integration_uuid")
            kind = (payload.get("connection_type") or item.connection_type or "").strip().lower()
            core = await ConnectionService._resolve_integration(tenant_id, integration_uuid, kind)
            item.integration_id = core.id if core else None
        for key, value in payload.items():
            setattr(item, key, value)
        if (item.connection_type or "").strip().lower() == "mqtt":
            if not item.integration_id:
                raise ValidationError("请选择同租户公共连接")
            ConnectionService._validate_mqtt_config(item.config)
        await item.save()
        await ConnectionService._attach_integration_uuid([item])
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
