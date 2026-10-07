"""已注册的平台遥测拉取。不新注册 cron。

平台地址和认证只从所属租户的公共连接读取。
"""

from apps.kuaiiot.services.platform_telemetry import pull_registered_telemetry
from apps.kuaiiot.services.delivery_service import process_pending


async def run_kuaiiot_telemetry_pull() -> dict:
    await process_pending()
    return await pull_registered_telemetry()
