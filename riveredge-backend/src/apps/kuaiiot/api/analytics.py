"""设备运营馈送。租户 RBAC，不接受设备凭据。"""

from fastapi import APIRouter, Depends, Query

from apps.kuaiiot.services.ops_feed_service import read_equipment_ops_feed
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant

router = APIRouter(tags=["App - 星数采 - 馈送"])


@router.get(
    "/analytics/equipment-ops-feed",
    dependencies=[Depends(require_permission_codes("kuaiiot:analytics:read"))],
)
async def api_equipment_ops_feed(
    hours: int = Query(default=24, ge=1, le=720),
    tenant_id: int = Depends(get_current_tenant),
):
    return await read_equipment_ops_feed(tenant_id, hours)
