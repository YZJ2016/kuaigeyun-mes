"""报表执行路由。返回 data / total / summary。"""

from typing import Any

from fastapi import APIRouter, Body, Depends

from apps.kuaireport.schemas.execute import ExecuteReportResult
from apps.kuaireport.services.execute_service import execute_report
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant

router = APIRouter(tags=["App - 星报表 - 执行"])


@router.post(
    "/reports/{report_id}/execute",
    response_model=ExecuteReportResult,
    dependencies=[Depends(require_permission_codes("kuaireport:report:execute"))],
)
async def api_execute_report(
    report_id: str,
    filters: dict[str, Any] = Body(default_factory=dict),
    tenant_id: int = Depends(get_current_tenant),
) -> ExecuteReportResult:
    return await execute_report(tenant_id, report_id, filters)
