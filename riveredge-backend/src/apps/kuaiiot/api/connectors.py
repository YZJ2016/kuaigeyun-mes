"""ThingsBoard / JetLinks 连接器 API。"""

from fastapi import APIRouter, Depends

from apps.kuaiiot.schemas.iot import ConnectorSyncRequest, ConnectorSyncResponse
from apps.kuaiiot.services.connector_service import ConnectorService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant

router = APIRouter(prefix="/connectors", tags=["App - KuaiIoT - Connectors"])


@router.post("/sync", response_model=ConnectorSyncResponse, dependencies=[Depends(require_permission_codes("kuaiiot:connection:update"))])
async def sync_connector_devices(
    data: ConnectorSyncRequest,
    tenant_id: int = Depends(get_current_tenant),
):
    return await ConnectorService.sync_connection(tenant_id, data.connection_uuid)


@router.post("/health-check/{connection_uuid}", dependencies=[Depends(require_permission_codes("kuaiiot:connection:read"))])
async def health_check_connection(connection_uuid: str, tenant_id: int = Depends(get_current_tenant)):
    item = await ConnectorService.health_check(tenant_id, connection_uuid)
    return {"health_status": item.health_status, "last_health_at": item.last_health_at}
