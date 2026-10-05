"""继电器制造行业插件 API。"""

from datetime import date as date_cls
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from apps.ind_relay.models.changeover_matrix import RelayChangeoverMatrix
from apps.ind_relay.models.line_capacity import RelayLineCapacity
from apps.kuaizhizao.services.output_basis_service import OutputBasisService
from apps.master_data.models.factory import ProductionLine
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from core.utils.timezone_utils import (
    resolve_business_datetime,
    site_day_bounds_utc,
    to_site_date,
)
from infra.api.deps.deps import get_current_user
from infra.models.user import User

router = APIRouter(prefix="", tags=["App - Industry Relay"])


class LineCapacityCreate(BaseModel):
    production_line_id: int
    takt_seconds: float = 0
    daily_capacity_qty: float = 0
    changeover_minutes_default: float = 0
    remarks: Optional[str] = None


class LineCapacityUpdate(BaseModel):
    takt_seconds: Optional[float] = None
    daily_capacity_qty: Optional[float] = None
    changeover_minutes_default: Optional[float] = None
    is_active: Optional[bool] = None
    remarks: Optional[str] = None


class LineCapacityResponse(BaseModel):
    id: int
    production_line_id: int
    production_line_code: Optional[str] = None
    production_line_name: Optional[str] = None
    takt_seconds: float
    daily_capacity_qty: float
    changeover_minutes_default: float
    is_active: bool
    remarks: Optional[str] = None


class ChangeoverCreate(BaseModel):
    from_family: str = Field(..., max_length=100)
    to_family: str = Field(..., max_length=100)
    changeover_minutes: float = 0
    forbid_same_line: bool = False
    remarks: Optional[str] = None


class ChangeoverUpdate(BaseModel):
    changeover_minutes: Optional[float] = None
    forbid_same_line: Optional[bool] = None
    remarks: Optional[str] = None


class ChangeoverResponse(BaseModel):
    id: int
    from_family: str
    to_family: str
    changeover_minutes: float
    forbid_same_line: bool
    remarks: Optional[str] = None


class LineOutputRow(BaseModel):
    production_line_id: int
    production_line_code: Optional[str] = None
    production_line_name: Optional[str] = None
    daily_capacity_qty: float
    planned_quantity: float = 0
    output_qualified: float
    achievement_rate: float
    plan_achievement_rate: float = 0


async def _planned_qty_by_line(
    tenant_id: int,
    start_day: date_cls,
    end_day: date_cls,
    range_start: datetime,
    range_end: datetime,
) -> dict:
    """按产线汇总计划量：优先滚动计划行，否则用工单计划量（按窗内已排工序归属产线）。"""
    from collections import defaultdict

    from apps.kuaizhizao.models.rolling_schedule_plan import (
        RollingSchedulePlan,
        RollingSchedulePlanLine,
    )
    from apps.kuaizhizao.models.work_order import WorkOrder
    from apps.kuaizhizao.models.work_order_operation import WorkOrderOperation
    from apps.master_data.models.factory import Workstation

    result: dict = defaultdict(float)
    station_to_line = {
        int(r["id"]): int(r.get("production_line_id") or 0)
        for r in await Workstation.filter(
            tenant_id=tenant_id, deleted_at__isnull=True
        ).values("id", "production_line_id")
        if int(r.get("production_line_id") or 0) > 0
    }

    plans = await RollingSchedulePlan.filter(
        tenant_id=tenant_id,
        plan_date__gte=start_day,
        plan_date__lte=end_day,
        deleted_at__isnull=True,
    ).all()
    if plans:
        plan_ids = [int(p.id) for p in plans]
        plan_lines = await RollingSchedulePlanLine.filter(
            tenant_id=tenant_id, plan_id__in=plan_ids
        ).all()
        wo_ids = list({int(ln.work_order_id) for ln in plan_lines if ln.work_order_id})
        wo_to_line: dict = {}
        if wo_ids:
            ops = await WorkOrderOperation.filter(
                tenant_id=tenant_id,
                work_order_id__in=wo_ids,
                deleted_at__isnull=True,
                assigned_station_id__gt=0,
            ).all()
            for op in ops:
                wid = int(op.work_order_id or 0)
                if wid in wo_to_line:
                    continue
                lid = station_to_line.get(int(op.assigned_station_id or 0), 0)
                if lid > 0:
                    wo_to_line[wid] = lid
        for ln in plan_lines:
            lid = wo_to_line.get(int(ln.work_order_id or 0), 0)
            if lid > 0:
                result[lid] += float(ln.planned_quantity or 0)
        if result:
            return dict(result)

    # fallback：窗内已排工序归属产线的工单计划量（同 WO 只计一次）
    ops = await WorkOrderOperation.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        assigned_station_id__gt=0,
        planned_start_date__gte=range_start,
        planned_start_date__lte=range_end,
    ).all()
    wo_to_line = {}
    for op in ops:
        wid = int(op.work_order_id or 0)
        if wid in wo_to_line:
            continue
        lid = station_to_line.get(int(op.assigned_station_id or 0), 0)
        if lid > 0:
            wo_to_line[wid] = lid
    if not wo_to_line:
        return {}
    for row in await WorkOrder.filter(
        tenant_id=tenant_id, id__in=list(wo_to_line.keys()), deleted_at__isnull=True
    ).values("id", "quantity"):
        lid = wo_to_line.get(int(row["id"]), 0)
        if lid > 0:
            result[lid] += float(row.get("quantity") or 0)
    return dict(result)


def _capacity_response(row: RelayLineCapacity) -> LineCapacityResponse:
    return LineCapacityResponse(
        id=row.id,
        production_line_id=row.production_line_id,
        production_line_code=row.production_line_code,
        production_line_name=row.production_line_name,
        takt_seconds=float(row.takt_seconds or 0),
        daily_capacity_qty=float(row.daily_capacity_qty or 0),
        changeover_minutes_default=float(row.changeover_minutes_default or 0),
        is_active=bool(row.is_active),
        remarks=row.remarks,
    )


def _changeover_response(row: RelayChangeoverMatrix) -> ChangeoverResponse:
    return ChangeoverResponse(
        id=row.id,
        from_family=row.from_family,
        to_family=row.to_family,
        changeover_minutes=float(row.changeover_minutes or 0),
        forbid_same_line=bool(row.forbid_same_line),
        remarks=row.remarks,
    )


@router.get(
    "/health",
    dependencies=[Depends(require_permission_codes("ind-relay:entry:read"))],
)
async def health(tenant_id: int = Depends(get_current_tenant)) -> dict:
    return {"ok": True, "app": "ind-relay", "tenant_id": tenant_id}


@router.get(
    "/status",
    dependencies=[Depends(require_permission_codes("ind-relay:entry:read"))],
)
async def module_status(tenant_id: int = Depends(get_current_tenant)) -> dict:
    """行业包生效状态：产量口径、排程资源模式、主数据就绪情况。"""
    from apps.ind_relay.extension_hooks import SNAPSHOT_KEY
    from apps.kuaizhizao.services.scheduling_config_service import SchedulingConfigService
    from infra.models.tenant import Tenant

    basis = await OutputBasisService.get_output_basis(tenant_id)
    cfg = await SchedulingConfigService().get_default_config(tenant_id)
    constraints = {}
    if cfg and cfg.constraints is not None:
        raw = cfg.constraints
        constraints = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw or {})
    tenant = await Tenant.get_or_none(id=tenant_id)
    settings = dict(tenant.settings or {}) if tenant else {}
    has_snapshot = SNAPSHOT_KEY in settings
    line_cap_count = 0
    changeover_count = 0
    tables_ready = True
    try:
        line_cap_count = await RelayLineCapacity.filter(
            tenant_id=tenant_id, deleted_at__isnull=True
        ).count()
        changeover_count = await RelayChangeoverMatrix.filter(
            tenant_id=tenant_id, deleted_at__isnull=True
        ).count()
    except Exception:
        tables_ready = False

    return {
        "output_basis": basis,
        "resource_mode": constraints.get("resource_mode") or "workstation",
        "line_exclusive": bool(constraints.get("line_exclusive", True)),
        "host_defaults_applied": has_snapshot
        or (
            basis == "last_operation_effective_qualified"
            and constraints.get("resource_mode") == "production_line"
        ),
        "tables_ready": tables_ready,
        "line_capacity_count": line_cap_count,
        "changeover_count": changeover_count,
        "hints": [
            "侧栏「行业包」→「继电器制造」可见菜单后即表示模块已挂载",
            "配置中心 → 实现产能口径应为「仅末道有效合格」",
            "可视排产设置 → 排程资源维度应为「按产线」",
            "若口径未变，可在本页点击「重新应用默认配置」（需入口更新权限）",
            "换型矩阵已接入排程引擎与拖拽校验（按料号族；无矩阵时回退全局换型小时）",
        ],
    }


@router.post(
    "/status/reapply-defaults",
    dependencies=[Depends(require_permission_codes("ind-relay:entry:update"))],
)
async def reapply_host_defaults(tenant_id: int = Depends(get_current_tenant)) -> dict:
    """已启用租户可手动重放启停种子（产量口径 + 产线排程）；不覆盖首次快照。"""
    from apps.ind_relay.extension_hooks import HOST_DEFAULTS_EXT, apply_standalone

    await apply_standalone(tenant_id, HOST_DEFAULTS_EXT)
    return await module_status(tenant_id)


@router.get(
    "/line-capacities",
    response_model=List[LineCapacityResponse],
    dependencies=[Depends(require_permission_codes("ind-relay:line-capacity:read"))],
)
async def list_line_capacities(
    tenant_id: int = Depends(get_current_tenant),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    rows = (
        await RelayLineCapacity.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        .order_by("-id")
        .offset(skip)
        .limit(limit)
    )
    return [_capacity_response(r) for r in rows]


@router.post(
    "/line-capacities",
    response_model=LineCapacityResponse,
    dependencies=[Depends(require_permission_codes("ind-relay:line-capacity:create"))],
)
async def create_line_capacity(
    body: LineCapacityCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    line = await ProductionLine.get_or_none(
        tenant_id=tenant_id, id=body.production_line_id, deleted_at__isnull=True
    )
    if not line:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="产线不存在")
    existing = await RelayLineCapacity.get_or_none(
        tenant_id=tenant_id,
        production_line_id=body.production_line_id,
        deleted_at__isnull=True,
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该产线已配置节拍产能")
    row = await RelayLineCapacity.create(
        tenant_id=tenant_id,
        production_line_id=body.production_line_id,
        production_line_code=line.code,
        production_line_name=line.name,
        takt_seconds=Decimal(str(body.takt_seconds or 0)),
        daily_capacity_qty=Decimal(str(body.daily_capacity_qty or 0)),
        changeover_minutes_default=Decimal(str(body.changeover_minutes_default or 0)),
        is_active=True,
        remarks=body.remarks,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    return _capacity_response(row)


@router.patch(
    "/line-capacities/{row_id}",
    response_model=LineCapacityResponse,
    dependencies=[Depends(require_permission_codes("ind-relay:line-capacity:update"))],
)
async def update_line_capacity(
    row_id: int,
    body: LineCapacityUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    row = await RelayLineCapacity.get_or_none(
        tenant_id=tenant_id, id=row_id, deleted_at__isnull=True
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")
    data = body.model_dump(exclude_unset=True)
    for key, val in data.items():
        if key in ("takt_seconds", "daily_capacity_qty", "changeover_minutes_default") and val is not None:
            setattr(row, key, Decimal(str(val)))
        else:
            setattr(row, key, val)
    row.updated_by = current_user.id
    await row.save()
    return _capacity_response(row)


@router.get(
    "/changeovers",
    response_model=List[ChangeoverResponse],
    dependencies=[Depends(require_permission_codes("ind-relay:changeover:read"))],
)
async def list_changeovers(
    tenant_id: int = Depends(get_current_tenant),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    rows = (
        await RelayChangeoverMatrix.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        .order_by("-id")
        .offset(skip)
        .limit(limit)
    )
    return [_changeover_response(r) for r in rows]


@router.post(
    "/changeovers",
    response_model=ChangeoverResponse,
    dependencies=[Depends(require_permission_codes("ind-relay:changeover:create"))],
)
async def create_changeover(
    body: ChangeoverCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    from_family = body.from_family.strip()
    to_family = body.to_family.strip()
    if not from_family or not to_family:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="料号族不能为空")
    existing = await RelayChangeoverMatrix.get_or_none(
        tenant_id=tenant_id,
        from_family=from_family,
        to_family=to_family,
        deleted_at__isnull=True,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该料号族换型规则已存在",
        )
    row = await RelayChangeoverMatrix.create(
        tenant_id=tenant_id,
        from_family=from_family,
        to_family=to_family,
        changeover_minutes=Decimal(str(body.changeover_minutes or 0)),
        forbid_same_line=bool(body.forbid_same_line),
        remarks=body.remarks,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    return _changeover_response(row)


@router.patch(
    "/changeovers/{row_id}",
    response_model=ChangeoverResponse,
    dependencies=[Depends(require_permission_codes("ind-relay:changeover:update"))],
)
async def update_changeover(
    row_id: int,
    body: ChangeoverUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    row = await RelayChangeoverMatrix.get_or_none(
        tenant_id=tenant_id, id=row_id, deleted_at__isnull=True
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")
    data = body.model_dump(exclude_unset=True)
    if "changeover_minutes" in data and data["changeover_minutes"] is not None:
        row.changeover_minutes = Decimal(str(data.pop("changeover_minutes")))
    for key, val in data.items():
        setattr(row, key, val)
    row.updated_by = current_user.id
    await row.save()
    return _changeover_response(row)


@router.delete(
    "/changeovers/{row_id}",
    dependencies=[Depends(require_permission_codes("ind-relay:changeover:update"))],
)
async def delete_changeover(
    row_id: int,
    tenant_id: int = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    """软删除换型规则。"""
    row = await RelayChangeoverMatrix.get_or_none(
        tenant_id=tenant_id, id=row_id, deleted_at__isnull=True
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")
    row.deleted_at = resolve_business_datetime()
    row.updated_by = current_user.id
    await row.save(update_fields=["deleted_at", "updated_by", "updated_at"])
    return {"ok": True}


@router.get(
    "/line-output",
    response_model=List[LineOutputRow],
    dependencies=[Depends(require_permission_codes("ind-relay:line-output:read"))],
)
async def line_output_dashboard(
    tenant_id: int = Depends(get_current_tenant),
    date_start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_end: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """按产线展示实现产能达成（分子走 output_basis）。"""
    today = to_site_date(resolve_business_datetime())
    try:
        end_day = date_cls.fromisoformat(date_end[:10]) if date_end else today
        start_day = date_cls.fromisoformat(date_start[:10]) if date_start else end_day
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="日期格式须为 YYYY-MM-DD",
        ) from exc
    if start_day > end_day:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="开始日期不能晚于结束日期",
        )
    start_utc, _ = site_day_bounds_utc(start_day)
    _, end_excl = site_day_bounds_utc(end_day)
    range_start = start_utc
    range_end = end_excl - timedelta(microseconds=1)
    planned_by_line = await _planned_qty_by_line(
        tenant_id, start_day, end_day, range_start, range_end
    )

    caps = await RelayLineCapacity.filter(
        tenant_id=tenant_id, deleted_at__isnull=True, is_active=True
    ).all()
    if not caps:
        lines = await ProductionLine.filter(
            tenant_id=tenant_id, deleted_at__isnull=True, is_active=True
        ).all()
        result: List[LineOutputRow] = []
        for line in lines:
            stats = await OutputBasisService.sum_output_quantities(
                tenant_id,
                date_start=range_start,
                date_end=range_end,
                production_line_id=int(line.id),
            )
            out_q = float(stats.get("qualified_quantity") or 0)
            plan_q = float(planned_by_line.get(int(line.id), 0))
            plan_rate = round(out_q / plan_q * 100, 2) if plan_q > 0 else 0.0
            result.append(
                LineOutputRow(
                    production_line_id=int(line.id),
                    production_line_code=line.code,
                    production_line_name=line.name,
                    daily_capacity_qty=0,
                    planned_quantity=plan_q,
                    output_qualified=out_q,
                    achievement_rate=0,
                    plan_achievement_rate=plan_rate,
                )
            )
        return result

    result = []
    for cap in caps:
        stats = await OutputBasisService.sum_output_quantities(
            tenant_id,
            date_start=range_start,
            date_end=range_end,
            production_line_id=int(cap.production_line_id),
        )
        out_q = float(stats.get("qualified_quantity") or 0)
        cap_q = float(cap.daily_capacity_qty or 0)
        # 日产能按区间天数放大，便于多日对比
        day_count = max(1, (end_day - start_day).days + 1)
        capacity_q = cap_q * day_count
        plan_q = float(planned_by_line.get(int(cap.production_line_id), 0))
        rate = round(out_q / capacity_q * 100, 2) if capacity_q > 0 else 0.0
        plan_rate = round(out_q / plan_q * 100, 2) if plan_q > 0 else 0.0
        result.append(
            LineOutputRow(
                production_line_id=int(cap.production_line_id),
                production_line_code=cap.production_line_code,
                production_line_name=cap.production_line_name,
                daily_capacity_qty=capacity_q,
                planned_quantity=plan_q,
                output_qualified=out_q,
                achievement_rate=rate,
                plan_achievement_rate=plan_rate,
            )
        )
    return result


# —— 自动报工 ——

class AutoReportConfigUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    match_by_device: Optional[bool] = None
    interval_minutes: Optional[int] = None
    report_mode: Optional[str] = None
    offline_threshold_seconds: Optional[int] = None
    reporter_user_id: Optional[int] = None
    remarks: Optional[str] = None


class AutoReportConfigResponse(BaseModel):
    id: int
    is_enabled: bool
    match_by_device: bool
    interval_minutes: int
    report_mode: str
    offline_threshold_seconds: int
    reporter_user_id: Optional[int] = None
    reporter_user_name: Optional[str] = None
    remarks: Optional[str] = None


class AutoReportBindingCreate(BaseModel):
    iot_device_id: int
    is_enabled: bool = True
    remarks: Optional[str] = None


class AutoReportBindingUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    remarks: Optional[str] = None


class AutoReportBindingResponse(BaseModel):
    id: int
    iot_device_id: int
    iot_device_uuid: Optional[str] = None
    iot_device_code: Optional[str] = None
    iot_device_name: Optional[str] = None
    external_device_id: Optional[str] = None
    equipment_uuid: str
    equipment_id: Optional[int] = None
    equipment_code: Optional[str] = None
    equipment_name: Optional[str] = None
    is_enabled: bool
    last_zscl: Optional[float] = None
    pending_quantity: float = 0
    baseline_aligned: bool
    bound_work_order_id: Optional[int] = None
    bound_work_order_code: Optional[str] = None
    bound_operation_id: Optional[int] = None
    bound_operation_name: Optional[str] = None
    last_settle_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    offline_flushed: bool = False
    remarks: Optional[str] = None


class AutoReportLogResponse(BaseModel):
    id: int
    binding_id: Optional[int] = None
    iot_device_id: Optional[int] = None
    level: str
    event: str
    message: Optional[str] = None
    zscl: Optional[float] = None
    increment_qty: Optional[float] = None
    work_order_id: Optional[int] = None
    work_order_code: Optional[str] = None
    operation_id: Optional[int] = None
    reporting_record_id: Optional[int] = None
    created_at: Optional[datetime] = None


def _config_response(row) -> AutoReportConfigResponse:
    return AutoReportConfigResponse(
        id=int(row.id),
        is_enabled=bool(row.is_enabled),
        match_by_device=bool(row.match_by_device),
        interval_minutes=int(row.interval_minutes or 5),
        report_mode=str(row.report_mode or "REALTIME_INCREMENT"),
        offline_threshold_seconds=int(row.offline_threshold_seconds or 180),
        reporter_user_id=row.reporter_user_id,
        reporter_user_name=row.reporter_user_name,
        remarks=row.remarks,
    )


def _binding_response(row) -> AutoReportBindingResponse:
    return AutoReportBindingResponse(
        id=int(row.id),
        iot_device_id=int(row.iot_device_id),
        iot_device_uuid=row.iot_device_uuid,
        iot_device_code=row.iot_device_code,
        iot_device_name=row.iot_device_name,
        external_device_id=row.external_device_id,
        equipment_uuid=row.equipment_uuid,
        equipment_id=row.equipment_id,
        equipment_code=row.equipment_code,
        equipment_name=row.equipment_name,
        is_enabled=bool(row.is_enabled),
        last_zscl=float(row.last_zscl) if row.last_zscl is not None else None,
        pending_quantity=float(row.pending_quantity or 0),
        baseline_aligned=bool(row.baseline_aligned),
        bound_work_order_id=row.bound_work_order_id,
        bound_work_order_code=row.bound_work_order_code,
        bound_operation_id=row.bound_operation_id,
        bound_operation_name=row.bound_operation_name,
        last_settle_at=row.last_settle_at,
        last_seen_at=row.last_seen_at,
        offline_flushed=bool(row.offline_flushed),
        remarks=row.remarks,
    )


@router.get(
    "/auto-report/config",
    response_model=AutoReportConfigResponse,
    dependencies=[Depends(require_permission_codes("ind-relay:auto-report:read"))],
)
async def get_auto_report_config(tenant_id: int = Depends(get_current_tenant)):
    from apps.ind_relay.services.auto_report_service import AutoReportService
    from infra.exceptions.exceptions import ValidationError

    try:
        row = await AutoReportService.get_or_create_config(tenant_id)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _config_response(row)


@router.put(
    "/auto-report/config",
    response_model=AutoReportConfigResponse,
    dependencies=[Depends(require_permission_codes("ind-relay:auto-report:update"))],
)
async def update_auto_report_config(
    body: AutoReportConfigUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    from apps.ind_relay.services.auto_report_service import AutoReportService
    from infra.exceptions.exceptions import ValidationError

    try:
        row = await AutoReportService.update_config(
            tenant_id,
            user_id=current_user.id,
            data=body.model_dump(exclude_unset=True),
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _config_response(row)


@router.get(
    "/auto-report/device-options",
    dependencies=[Depends(require_permission_codes("ind-relay:auto-report:read"))],
)
async def list_auto_report_device_options(tenant_id: int = Depends(get_current_tenant)):
    from apps.ind_relay.services.auto_report_service import AutoReportService

    return {"items": await AutoReportService.list_bound_iot_device_options(tenant_id)}


@router.get(
    "/auto-report/bindings",
    response_model=List[AutoReportBindingResponse],
    dependencies=[Depends(require_permission_codes("ind-relay:auto-report:read"))],
)
async def list_auto_report_bindings(tenant_id: int = Depends(get_current_tenant)):
    from apps.ind_relay.services.auto_report_service import AutoReportService

    rows = await AutoReportService.list_bindings(tenant_id)
    return [_binding_response(r) for r in rows]


@router.post(
    "/auto-report/bindings",
    response_model=AutoReportBindingResponse,
    dependencies=[Depends(require_permission_codes("ind-relay:auto-report:update"))],
)
async def create_auto_report_binding(
    body: AutoReportBindingCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    from apps.ind_relay.services.auto_report_service import AutoReportService
    from infra.exceptions.exceptions import NotFoundError, ValidationError

    try:
        row = await AutoReportService.upsert_binding(
            tenant_id,
            user_id=current_user.id,
            iot_device_id=body.iot_device_id,
            is_enabled=body.is_enabled,
            remarks=body.remarks,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _binding_response(row)


@router.patch(
    "/auto-report/bindings/{binding_id}",
    response_model=AutoReportBindingResponse,
    dependencies=[Depends(require_permission_codes("ind-relay:auto-report:update"))],
)
async def update_auto_report_binding(
    binding_id: int,
    body: AutoReportBindingUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    from apps.ind_relay.services.auto_report_service import AutoReportService
    from infra.exceptions.exceptions import NotFoundError, ValidationError

    data = body.model_dump(exclude_unset=True)
    try:
        if "is_enabled" in data and data["is_enabled"] is not None:
            row = await AutoReportService.set_binding_enabled(
                tenant_id,
                binding_id,
                is_enabled=bool(data["is_enabled"]),
                user_id=current_user.id,
            )
        else:
            rows = await AutoReportService.list_bindings(tenant_id)
            row = next((r for r in rows if int(r.id) == binding_id), None)
            if not row:
                raise NotFoundError("绑定不存在")
        if "remarks" in data:
            row.remarks = data["remarks"]
            row.updated_by = current_user.id
            await row.save()
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _binding_response(row)


@router.delete(
    "/auto-report/bindings/{binding_id}",
    dependencies=[Depends(require_permission_codes("ind-relay:auto-report:update"))],
)
async def delete_auto_report_binding(
    binding_id: int,
    tenant_id: int = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
):
    from apps.ind_relay.services.auto_report_service import AutoReportService
    from infra.exceptions.exceptions import NotFoundError

    try:
        await AutoReportService.delete_binding(
            tenant_id, binding_id, user_id=current_user.id
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True}


@router.get(
    "/auto-report/logs",
    dependencies=[Depends(require_permission_codes("ind-relay:auto-report:read"))],
)
async def list_auto_report_logs(
    tenant_id: int = Depends(get_current_tenant),
    binding_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    from apps.ind_relay.services.auto_report_service import AutoReportService

    rows, total = await AutoReportService.list_logs(
        tenant_id, binding_id=binding_id, skip=skip, limit=limit
    )
    return {
        "total": total,
        "items": [
            AutoReportLogResponse(
                id=int(r.id),
                binding_id=r.binding_id,
                iot_device_id=r.iot_device_id,
                level=r.level,
                event=r.event,
                message=r.message,
                zscl=float(r.zscl) if r.zscl is not None else None,
                increment_qty=float(r.increment_qty) if r.increment_qty is not None else None,
                work_order_id=r.work_order_id,
                work_order_code=r.work_order_code,
                operation_id=r.operation_id,
                reporting_record_id=r.reporting_record_id,
                created_at=r.created_at,
            )
            for r in rows
        ],
    }


@router.post(
    "/auto-report/settle-now",
    dependencies=[Depends(require_permission_codes("ind-relay:auto-report:update"))],
)
async def settle_auto_report_now(tenant_id: int = Depends(get_current_tenant)):
    """手动触发一次本租户结算（调试/运维）。"""
    from apps.ind_relay.services.auto_report_service import AutoReportService

    return await AutoReportService.settle_tenant(tenant_id, force=True)
