"""租户内分段诊断，不返回配置地址、设备凭据或原始错误。"""
from apps.kuaiiot.models.connection import KuaiiotConnection
from apps.kuaiiot.models.delivery import KuaiiotDelivery
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.edge_config import KuaiiotEdgeConfig
from apps.kuaiiot.services.control_service import _require_tenant
from apps.kuaiiot.services.edge_config_service import EdgeConfigService


async def read_diagnostics(tenant_id: int) -> dict:
    tid = _require_tenant(tenant_id)
    connections = await KuaiiotConnection.filter(tenant_id=tid, deleted_at__isnull=True).limit(500)
    devices = await KuaiiotDevice.filter(tenant_id=tid, deleted_at__isnull=True).limit(500)
    edges = await KuaiiotEdgeConfig.filter(tenant_id=tid, deleted_at__isnull=True).limit(500)
    pending = await KuaiiotDelivery.filter(tenant_id=tid, status__in=["pending", "blocked"]).order_by("id").limit(100)
    return {
        "connections": [{"id": r.id, "name": r.name, "type": r.connection_type, "health_status": r.health_status, "last_health_at": r.last_health_at.isoformat() if r.last_health_at else None} for r in connections],
        "devices": [{"id": r.id, "name": r.name, "is_online": r.is_online, "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else None} for r in devices],
        "agents": [{key: value for key, value in EdgeConfigService._public(r).items() if key != "config"} for r in edges],
        "deliveries": [{"id": r.id, "kind": r.kind, "status": r.status, "attempts": r.attempts, "last_error": r.last_error} for r in pending],
    }
