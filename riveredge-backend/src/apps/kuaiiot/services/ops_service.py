"""快数采租户运维汇总。"""

from __future__ import annotations

from datetime import timedelta

from apps.kuaiiot.constants import EDGE_AGENT_OFFLINE_SECONDS, OFFLINE_THRESHOLD_SECONDS
from apps.kuaiiot.models.iot import IotAlert, IotConnection, IotDevice, IotEdgeConfig
from apps.kuaiiot.schemas.iot import OpsSummaryResponse
from apps.kuaiiot.services.tag_history_store import TagHistoryStore
from core.utils.timezone_utils import resolve_business_datetime


class OpsService:
    @staticmethod
    async def summary(tenant_id: int) -> OpsSummaryResponse:
        now = resolve_business_datetime()
        device_cutoff = now - timedelta(seconds=OFFLINE_THRESHOLD_SECONDS)
        agent_cutoff = now - timedelta(seconds=EDGE_AGENT_OFFLINE_SECONDS)

        connections = await IotConnection.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        conn_total = len(connections)
        conn_healthy = sum(1 for item in connections if item.health_status == "healthy")
        conn_unhealthy = sum(1 for item in connections if item.health_status == "unhealthy")
        conn_unknown = conn_total - conn_healthy - conn_unhealthy

        total_devices = await IotDevice.filter(tenant_id=tenant_id, deleted_at__isnull=True).count()
        online_devices = await IotDevice.filter(
            tenant_id=tenant_id, is_online=True, deleted_at__isnull=True
        ).count()
        stale_devices = await IotDevice.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            last_seen_at__lt=device_cutoff,
        ).count()

        edge_configs = await IotEdgeConfig.filter(tenant_id=tenant_id, deleted_at__isnull=True, is_enabled=True)
        edge_total = len(edge_configs)
        edge_online = sum(
            1
            for item in edge_configs
            if item.agent_status == "online"
            and item.last_agent_heartbeat_at is not None
            and item.last_agent_heartbeat_at >= agent_cutoff
        )
        edge_offline = sum(
            1
            for item in edge_configs
            if item.last_agent_heartbeat_at is not None and item.last_agent_heartbeat_at < agent_cutoff
        )
        edge_unknown = edge_total - edge_online - edge_offline

        open_alerts = await IotAlert.filter(tenant_id=tenant_id, status="open", deleted_at__isnull=True).count()
        ack_alerts = await IotAlert.filter(
            tenant_id=tenant_id, status="acknowledged", deleted_at__isnull=True
        ).count()
        points_today = await TagHistoryStore.count_points_today(tenant_id)
        tsdb_configured = await TagHistoryStore.is_configured(tenant_id)

        return OpsSummaryResponse(
            connections={
                "total": conn_total,
                "healthy": conn_healthy,
                "unhealthy": conn_unhealthy,
                "unknown": conn_unknown,
            },
            devices={
                "total": total_devices,
                "online": online_devices,
                "offline": total_devices - online_devices,
                "stale": stale_devices,
            },
            edge_agents={
                "total": edge_total,
                "online": edge_online,
                "offline": edge_offline,
                "unknown": edge_unknown,
            },
            alerts={"open": open_alerts, "acknowledged": ack_alerts},
            ingest={"points_today": points_today},
            tsdb_configured=tsdb_configured,
        )
