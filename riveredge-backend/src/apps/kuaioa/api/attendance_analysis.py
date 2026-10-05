"""考勤分析报表 API。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.kuaioa.services.attendance_analysis_service import AttendanceAnalysisService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.exceptions.exceptions import BusinessLogicError

router = APIRouter(prefix="/attendance-analysis", tags=["App - Kuaioa - Attendance Analysis"])
svc = AttendanceAnalysisService()


@router.get("")
async def get_attendance_analysis(
    granularity: str = Query("day", description="day|month"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    department_name: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    _auth=Depends(require_permission_codes("kuaioa:attendance-analysis:read")),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        data = await svc.analyze(
            tenant_id,
            granularity=granularity,
            date_from=date_from,
            date_to=date_to,
            department_name=department_name,
            keyword=keyword,
        )
        return {"data": data, "success": True}
    except BusinessLogicError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message": str(e)})
