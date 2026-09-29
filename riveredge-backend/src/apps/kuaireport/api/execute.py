"""报表执行路由。返回 data / total / summary。"""

from typing import Any

from fastapi import APIRouter, Body, Depends, Request

from apps.kuaireport.schemas.execute import ExecuteReportResult
from apps.kuaireport.services.execute_service import (
    HttpGet,
    execute_report,
    forward_auth_http_get,
)
from apps.kuaireport.slices.s149_distribution import RESOURCE_REPORT, enforce_grant_view
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user
from infra.models.user import User

router = APIRouter(tags=["App - 星报表 - 执行"])


async def execute_report_for_viewer(
    tenant_id: int,
    user_id: int | None,
    report_id: str | int,
    filters: dict[str, Any] | None = None,
    *,
    grant_store: Any = None,
    http_get: HttpGet | None = None,
) -> ExecuteReportResult:
    await enforce_grant_view(
        tenant_id, user_id, RESOURCE_REPORT, int(report_id), store=grant_store
    )
    if http_get is None:
        return await execute_report(tenant_id, report_id, filters)
    return await execute_report(tenant_id, report_id, filters, http_get=http_get)


@router.post(
    "/reports/{report_id}/execute",
    response_model=ExecuteReportResult,
    dependencies=[Depends(require_permission_codes("kuaireport:report:execute"))],
)
async def api_execute_report(
    report_id: str,
    request: Request,
    filters: dict[str, Any] = Body(default_factory=dict),
    tenant_id: int = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
) -> ExecuteReportResult:
    return await execute_report_for_viewer(
        tenant_id,
        current_user.id,
        report_id,
        filters,
        http_get=forward_auth_http_get(request),
    )
