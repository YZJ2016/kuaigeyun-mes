"""通过公共配置检查连接，配置存在不等于已连通。"""
from datetime import timedelta
from apps.kuaiiot.models.connection import KuaiiotConnection
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.services.connection_runtime import resolve_core_connection
from core.services.integration.iot_platform_client import PlatformClient
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import unscoped, with_tenant


async def run_kuaiiot_connection_health_check() -> dict:
    now = resolve_business_datetime()
    async with unscoped(reason="健康任务扫描公共关联数采连接", resource="KuaiiotConnection"):
        rows = await KuaiiotConnection.filter(deleted_at__isnull=True)
    checked = 0
    for row in rows:
        async with with_tenant(int(row.tenant_id), reason="数采连接健康按所属租户核对"):
            try:
                core = await resolve_core_connection(row)
                if row.connection_type == "mqtt":
                    if not row.subscriber_lease_until or row.subscriber_lease_until < now or not row.last_health_at or row.last_health_at < now - timedelta(seconds=60):
                        row.health_status = "disconnected"
                elif row.connection_type in {"thingsboard", "jetlinks"}:
                    async with PlatformClient(row.connection_type, core.get_config()) as client:
                        await client.probe()
                    row.health_status = "authenticated"
                else:
                    recent = await KuaiiotDevice.filter(tenant_id=row.tenant_id, connection_id=row.id, deleted_at__isnull=True, last_seen_at__gte=now-timedelta(minutes=5)).exists()
                    row.health_status = "receiving" if recent else "idle"
            except Exception:
                row.health_status = "disabled" if not row.is_enabled else "unavailable"
            row.last_health_at = now
            await row.save(update_fields=["health_status", "last_health_at", "updated_at"])
            checked += 1
    return {"checked": checked}
