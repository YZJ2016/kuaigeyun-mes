"""模具机加行业插件 API。"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from apps.ind_mold.models.material_arrival import MoldMaterialArrival
from apps.ind_mold.models.program_sheet import MoldProgramSheet
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from core.utils.timezone_utils import resolve_business_datetime, today_site_str
from infra.api.deps.deps import get_current_user
from infra.models.user import User

router = APIRouter(prefix="", tags=["App - Industry Mold"])


class MoldProgramSheetCreate(BaseModel):
    work_order_id: int
    work_order_code: str = Field(..., max_length=50)
    program_name: str = Field(..., max_length=200)
    nc_file_path: Optional[str] = Field(None, max_length=500)
    remarks: Optional[str] = None


class MoldProgramSheetResponse(BaseModel):
    id: int
    code: str
    work_order_id: int
    work_order_code: str
    program_name: str
    program_status: str
    nc_file_path: Optional[str] = None
    remarks: Optional[str] = None


class MoldMaterialArrivalCreate(BaseModel):
    work_order_id: Optional[int] = None
    work_order_code: Optional[str] = Field(None, max_length=50)
    material_name: str = Field(..., max_length=200)
    material_spec: Optional[str] = Field(None, max_length=200)
    weight: Optional[float] = None
    remarks: Optional[str] = None


class MoldMaterialArrivalResponse(BaseModel):
    id: int
    code: str
    work_order_id: Optional[int] = None
    work_order_code: Optional[str] = None
    material_name: str
    material_spec: Optional[str] = None
    weight: Optional[float] = None
    status: str
    remarks: Optional[str] = None


def _next_code(prefix: str) -> str:
    return f"{prefix}{today_site_str('%Y%m%d')}{resolve_business_datetime().strftime('%H%M%S')}"


@router.get(
    "/health",
    dependencies=[Depends(require_permission_codes("ind-mold:entry:read"))],
)
async def health(tenant_id: int = Depends(get_current_tenant)) -> dict:
    return {"ok": True, "app": "ind-mold", "tenant_id": tenant_id}


@router.get(
    "/program-sheets",
    response_model=List[MoldProgramSheetResponse],
    dependencies=[Depends(require_permission_codes("ind-mold:program:read"))],
)
async def list_program_sheets(
    tenant_id: int = Depends(get_current_tenant),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    rows = await MoldProgramSheet.filter(tenant_id=tenant_id, deleted_at__isnull=True).order_by("-id").offset(skip).limit(limit)
    return [
        MoldProgramSheetResponse(
            id=row.id,
            code=row.code,
            work_order_id=row.work_order_id,
            work_order_code=row.work_order_code,
            program_name=row.program_name,
            program_status=row.program_status,
            nc_file_path=row.nc_file_path,
            remarks=row.remarks,
        )
        for row in rows
    ]


@router.post(
    "/program-sheets",
    response_model=MoldProgramSheetResponse,
    dependencies=[Depends(require_permission_codes("ind-mold:program:create"))],
)
async def create_program_sheet(
    body: MoldProgramSheetCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    row = await MoldProgramSheet.create(
        tenant_id=tenant_id,
        code=_next_code("PG"),
        work_order_id=body.work_order_id,
        work_order_code=body.work_order_code,
        program_name=body.program_name,
        program_status="pending",
        nc_file_path=body.nc_file_path,
        remarks=body.remarks,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    return MoldProgramSheetResponse(
        id=row.id,
        code=row.code,
        work_order_id=row.work_order_id,
        work_order_code=row.work_order_code,
        program_name=row.program_name,
        program_status=row.program_status,
        nc_file_path=row.nc_file_path,
        remarks=row.remarks,
    )


@router.get(
    "/material-arrivals",
    response_model=List[MoldMaterialArrivalResponse],
    dependencies=[Depends(require_permission_codes("ind-mold:arrival:read"))],
)
async def list_material_arrivals(
    tenant_id: int = Depends(get_current_tenant),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    rows = await MoldMaterialArrival.filter(tenant_id=tenant_id, deleted_at__isnull=True).order_by("-id").offset(skip).limit(limit)
    return [
        MoldMaterialArrivalResponse(
            id=row.id,
            code=row.code,
            work_order_id=row.work_order_id,
            work_order_code=row.work_order_code,
            material_name=row.material_name,
            material_spec=row.material_spec,
            weight=float(row.weight) if row.weight is not None else None,
            status=row.status,
            remarks=row.remarks,
        )
        for row in rows
    ]


@router.post(
    "/material-arrivals",
    response_model=MoldMaterialArrivalResponse,
    dependencies=[Depends(require_permission_codes("ind-mold:arrival:create"))],
)
async def create_material_arrival(
    body: MoldMaterialArrivalCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    row = await MoldMaterialArrival.create(
        tenant_id=tenant_id,
        code=_next_code("MA"),
        work_order_id=body.work_order_id,
        work_order_code=body.work_order_code,
        material_name=body.material_name,
        material_spec=body.material_spec,
        weight=body.weight,
        status="pending",
        remarks=body.remarks,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    return MoldMaterialArrivalResponse(
        id=row.id,
        code=row.code,
        work_order_id=row.work_order_id,
        work_order_code=row.work_order_code,
        material_name=row.material_name,
        material_spec=row.material_spec,
        weight=float(row.weight) if row.weight is not None else None,
        status=row.status,
        remarks=row.remarks,
    )


@router.post(
    "/material-arrivals/{arrival_id}/void",
    response_model=MoldMaterialArrivalResponse,
    dependencies=[Depends(require_permission_codes("ind-mold:arrival:update"))],
)
async def void_material_arrival(
    arrival_id: int,
    tenant_id: int = Depends(get_current_tenant),
):
    row = await MoldMaterialArrival.get_or_none(
        tenant_id=tenant_id, id=arrival_id, deleted_at__isnull=True
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="到料单不存在")
    row.status = "void"
    await row.save()
    return MoldMaterialArrivalResponse(
        id=row.id,
        code=row.code,
        work_order_id=row.work_order_id,
        work_order_code=row.work_order_code,
        material_name=row.material_name,
        material_spec=row.material_spec,
        weight=float(row.weight) if row.weight is not None else None,
        status=row.status,
        remarks=row.remarks,
    )
