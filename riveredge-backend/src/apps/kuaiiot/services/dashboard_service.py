"""快数采仪表盘服务。"""

from __future__ import annotations

from apps.kuaiiot.models.iot import IotConnection, IotDevice, IotTagDefinition
from apps.kuaiiot.schemas.iot import DashboardSummaryResponse, DeviceResponse
from apps.kuaiiot.services.tag_history_store import TagHistoryStore


class DashboardService:
    @staticmethod
    async def summary(tenant_id: int) -> DashboardSummaryResponse:
        total_devices = await IotDevice.filter(tenant_id=tenant_id, deleted_at__isnull=True).count()
        online_devices = await IotDevice.filter(
            tenant_id=tenant_id, is_online=True, deleted_at__isnull=True
        ).count()
        total_connections = await IotConnection.filter(tenant_id=tenant_id, deleted_at__isnull=True).count()
        enabled_connections = await IotConnection.filter(
            tenant_id=tenant_id, is_enabled=True, deleted_at__isnull=True
        ).count()
        total_tags = await IotTagDefinition.filter(tenant_id=tenant_id, deleted_at__isnull=True).count()
        points_today = await TagHistoryStore.count_points_today(tenant_id)

        recent = await IotDevice.filter(tenant_id=tenant_id, deleted_at__isnull=True).order_by(
            "-last_seen_at", "-updated_at"
        ).limit(8)

        return DashboardSummaryResponse(
            total_devices=total_devices,
            online_devices=online_devices,
            total_connections=total_connections,
            enabled_connections=enabled_connections,
            total_tags=total_tags,
            points_today=points_today,
            recent_devices=[DeviceResponse.model_validate(item) for item in recent],
        )
