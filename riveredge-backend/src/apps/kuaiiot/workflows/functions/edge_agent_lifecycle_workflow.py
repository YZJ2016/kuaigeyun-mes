"""边缘 Agent 心跳超时。不写告警。"""

from apps.kuaiiot.services.edge_config_service import EdgeConfigService


async def run_kuaiiot_edge_agent_offline_check() -> dict:
    return await EdgeConfigService.mark_agents_offline()
