"""设备入站离线。告警写在标记之后，心跳路径不插入告警。"""

from apps.kuaiiot.services.edge_config_service import EdgeConfigService
from apps.kuaiiot.services.offline_alert_service import write_offline_alerts


async def run_kuaiiot_offline_check() -> dict:
    result = await EdgeConfigService.mark_devices_offline()
    await write_offline_alerts(result.get("flipped") or [], result.get("checked_at"))
    return {"devices_marked_offline": int(result["devices_marked_offline"])}
