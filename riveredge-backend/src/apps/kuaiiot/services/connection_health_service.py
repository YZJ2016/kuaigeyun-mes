"""快数采连接源批量健康探测。"""

from __future__ import annotations

from datetime import timedelta

from apps.kuaiiot.models.iot import IotConnection, IotConnectionMessage
from apps.kuaiiot.services.connection_service import ConnectionService
from apps.kuaiiot.services.connector_service import ConnectorService
from core.utils.timezone_utils import resolve_business_datetime

_MQTT_RECENT_SECONDS = 600


class ConnectionHealthService:
    @staticmethod
    async def _refresh_mqtt(connection: IotConnection) -> IotConnection:
        from apps.kuaiiot.services.mqtt_subscriber_service import MqttSubscriberService

        subscribed = connection.id in MqttSubscriberService._tasks
        cutoff = resolve_business_datetime() - timedelta(seconds=_MQTT_RECENT_SECONDS)
        recent = await IotConnectionMessage.filter(
            connection_id=int(connection.id),
            created_at__gte=cutoff,
            deleted_at__isnull=True,
        ).exists()
        if subscribed or recent:
            return await ConnectionService.apply_health(
                connection,
                healthy=True,
                min_interval_seconds=60,
            )
        probed = await MqttSubscriberService.probe_broker(connection)
        if probed:
            return await ConnectionService.apply_health(connection, healthy=True)
        return await ConnectionService.apply_health(
            connection,
            healthy=False,
            allow_downgrade=False,
        )

    @staticmethod
    async def probe_all_enabled() -> dict[str, int]:
        connections = await IotConnection.filter(is_enabled=True, deleted_at__isnull=True)
        checked = 0
        healthy = 0
        for connection in connections:
            if connection.connection_type == "mqtt":
                item = await ConnectionHealthService._refresh_mqtt(connection)
            else:
                item = await ConnectorService.health_check(connection.tenant_id, connection.uuid)
            checked += 1
            if item.health_status == "healthy":
                healthy += 1
        return {"checked": checked, "healthy": healthy, "unhealthy": checked - healthy}
