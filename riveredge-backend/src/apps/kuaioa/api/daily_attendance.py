"""每日考勤登记 API。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from apps.kuaioa.schemas.daily_attendance import DailyAttendanceCreate, DailyAttendanceUpdate
from apps.kuaioa.services.daily_attendance_service import DailyAttendanceService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError
from infra.models.user import User

router = APIRouter(prefix="/attendance-daily", tags=["App - Kuaioa - Daily Attendance"])
svc = DailyAttendanceService()


@router.get("")
async def list_daily_attendance(
    keyword: Optional[str] = Query(None),
    work_date_from: Optional[str] = Query(None),
    work_date_to: Optional[str] = Query(None),
    department_name: Optional[str] = Query(None),
    employee_id: Optional[int] = Query(None),
    _auth=Depends(require_permission_codes("kuaioa:attendance-daily:read")),
    tenant_id: int = Depends(get_current_tenant),
):
    rows = await svc.list_rows(
        tenant_id,
        keyword=keyword,
        work_date_from=work_date_from,
        work_date_to=work_date_to,
        department_name=department_name,
        employee_id=employee_id,
    )
    return {"data": rows, "total": len(rows), "success": True}


@router.get("/{row_id}")
async def get_daily_attendance(
    row_id: int = Path(..., ge=1),
    _auth=Depends(require_permission_codes("kuaioa:attendance-daily:read")),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return {"data": await svc.get_row(tenant_id, row_id), "success": True}
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": str(e)})


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_daily_attendance(
    data: DailyAttendanceCreate,
    current_user: User = Depends(get_current_user),
    _auth=Depends(require_permission_codes("kuaioa:attendance-daily:create")),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return {
            "data": await svc.create_row(tenant_id, data, current_user.id),
            "success": True,
        }
    except BusinessLogicError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message": str(e)})


@router.put("/{row_id}")
async def update_daily_attendance(
    data: DailyAttendanceUpdate,
    row_id: int = Path(..., ge=1),
    current_user: User = Depends(get_current_user),
    _auth=Depends(require_permission_codes("kuaioa:attendance-daily:update")),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return {
            "data": await svc.update_row(tenant_id, row_id, data, current_user.id),
            "success": True,
        }
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": str(e)})
    except BusinessLogicError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message": str(e)})


@router.delete("/{row_id}")
async def delete_daily_attendance(
    row_id: int = Path(..., ge=1),
    current_user: User = Depends(get_current_user),
    _auth=Depends(require_permission_codes("kuaioa:attendance-daily:delete")),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        await svc.delete_row(tenant_id, row_id, current_user.id)
        return {"success": True}
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": str(e)})
