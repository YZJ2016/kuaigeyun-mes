"""快数采边缘 Agent 离线检测。"""

from __future__ import annotations

from datetime import timedelta

from apps.kuaiiot.constants import EDGE_AGENT_OFFLINE_SECONDS
from apps.kuaiiot.models.iot import IotEdgeConfig
from core.utils.timezone_utils import resolve_business_datetime


class EdgeAgentLifecycleService:
    @staticmethod
    async def mark_stale_agents_offline() -> dict[str, int]:
        cutoff = resolve_business_datetime() - timedelta(seconds=EDGE_AGENT_OFFLINE_SECONDS)
        configs = await IotEdgeConfig.filter(
            agent_status="online",
            last_agent_heartbeat_at__lt=cutoff,
            deleted_at__isnull=True,
        )
        marked = 0
        for item in configs:
            item.agent_status = "offline"
            await item.save()
            marked += 1
        return {"marked_offline": marked}
