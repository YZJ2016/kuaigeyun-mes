"""已注册的平台遥测拉取。不新注册 cron。

拉取为空的原因见 spec 156「平台地址未进入仓库」。
"""

from apps.kuaiiot.services.platform_telemetry import pull_registered_telemetry
from apps.kuaiiot.services.delivery_service import process_pending


async def run_kuaiiot_telemetry_pull() -> dict:
    await process_pending()
    return await pull_registered_telemetry()
