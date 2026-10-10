"""已注册的平台遥测拉取。不新注册 cron。

平台地址和认证只从所属租户的公共连接读取。
"""

from apps.kuaiiot.services.platform_telemetry import pull_registered_telemetry
from apps.kuaiiot.services.delivery_service import process_pending
from apps.kuaiiot.services.telemetry_sync_service import TelemetrySyncService


async def run_kuaiiot_telemetry_pull() -> dict:
    await process_pending()
    result = await pull_registered_telemetry()
    connector = await TelemetrySyncService.pull_all_enabled_connections()
    if isinstance(result, dict) and isinstance(connector, dict):
        result.update(connector)
    return result
