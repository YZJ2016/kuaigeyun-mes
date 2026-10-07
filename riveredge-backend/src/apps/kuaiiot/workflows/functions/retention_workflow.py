"""按业务配置留存日志和已完成投递；不清理未完成投递或幂等身份。"""
from datetime import timedelta
from apps.kuaiiot.models.connection import KuaiiotConnection
from apps.kuaiiot.models.delivery import KuaiiotDelivery
from apps.kuaiiot.models.message_log import KuaiiotMessageLog
from infra.services.business_config_service import BusinessConfigService
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import unscoped, with_tenant


async def run_kuaiiot_retention_cleanup() -> dict:
    async with unscoped(reason="扫描数采租户执行已配置留存", resource="KuaiiotConnection"):
        tenants = await KuaiiotConnection.all().distinct().values_list("tenant_id", flat=True)
    deleted = missing = 0
    for tid in tenants:
        if tid is None:
            continue
        async with with_tenant(int(tid), reason="清理所属租户数采日志和已完成投递"):
            config = await BusinessConfigService().get_business_config(int(tid))
            days = (config.get("parameters") or {}).get("kuaiiot_retention_days")
            if isinstance(days, bool) or not isinstance(days, int) or days < 1:
                missing += 1
                continue
            cutoff = resolve_business_datetime() - timedelta(days=days)
            deleted += await KuaiiotMessageLog.filter(tenant_id=tid, created_at__lt=cutoff).delete()
            deleted += await KuaiiotDelivery.filter(tenant_id=tid, status="delivered", updated_at__lt=cutoff).delete()
    return {"deleted": deleted, "configuration_required": missing}
