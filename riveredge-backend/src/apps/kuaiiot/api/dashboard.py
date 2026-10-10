"""仪表盘 API。"""

from fastapi import APIRouter, Depends

from apps.kuaiiot.schemas.iot import DashboardSummaryResponse
from apps.kuaiiot.services.dashboard_service import DashboardService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant

router = APIRouter(prefix="/dashboard", tags=["App - KuaiIoT - Dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse, dependencies=[Depends(require_permission_codes("kuaiiot:dashboard:read"))])
async def dashboard_summary(tenant_id: int = Depends(get_current_tenant)):
    return await DashboardService.summary(tenant_id)
