"""快数采租户运维 API。"""

from fastapi import APIRouter, Depends

from apps.kuaiiot.schemas.iot import OpsSummaryResponse
from apps.kuaiiot.services.ops_service import OpsService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant

router = APIRouter(prefix="/ops", tags=["App - KuaiIoT - Ops"])


@router.get("/summary", response_model=OpsSummaryResponse, dependencies=[Depends(require_permission_codes("kuaiiot:ops:read"))])
async def get_ops_summary(tenant_id: int = Depends(get_current_tenant)):
    return await OpsService.summary(tenant_id)
