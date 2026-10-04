"""快制造 — 移动端 H5 聚合 API（企微工作台入口）。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from apps.kuaizhizao.models.equipment_fault import EquipmentFault
from apps.kuaizhizao.models.maintenance_reminder import MaintenanceReminder
from apps.kuaizhizao.services.mobile_home_service import (
    fetch_mobile_home_bootstrap,
    list_mobile_pending_kuaizhizao_approvals,
)
from core.schemas.approval_instance import ApprovalInstanceResponse
from apps.kuaizhizao.services.mobile_workbench import resolve_mobile_workbench
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user
from infra.models.user import User

router = APIRouter(
    prefix="/mobile",
    tags=["App - Kuaige Zhizao - 移动端"],
)


class MobileWorkbenchEntryOut(BaseModel):
    key: str
    label: str
    route: str
    icon: str
    icon_group: str | None = None
    solo_row: bool = False


class MobileWorkbenchSectionOut(BaseModel):
    key: str
    title: str
    entries: list[MobileWorkbenchEntryOut]


class MobileHomeBootstrapOut(BaseModel):
    sections: list[MobileWorkbenchSectionOut]
    work_order_stats: dict[str, int]
    pending_inspection_count: int
    unread_message_count: int
    im_unread_count: int = Field(default=0, description="IM 会话未读合计")
    pending_task_count: int
    pending_inbox_task_count: int = Field(
        default=0,
        description="消息中心待办（不含快制造审批）",
    )
    pending_kuaizhizao_approval_count: int
    notices: list[dict[str, str]]


class MobileEquipmentBootstrapOut(BaseModel):
    pending_fault_count: int = Field(description="待处理设备故障数量")
    overdue_maintenance_reminder_count: int = Field(description="逾期未处理保养提醒数量")


@router.get("/bootstrap", response_model=MobileEquipmentBootstrapOut, summary="设备 H5 启动角标")
async def get_mobile_bootstrap(
    tenant_id: Annotated[int, Depends(get_current_tenant)],
) -> MobileEquipmentBootstrapOut:
    pending_fault_count = await EquipmentFault.filter(
        tenant_id=tenant_id,
        status="待处理",
        deleted_at__isnull=True,
    ).count()
    overdue_maintenance_reminder_count = await MaintenanceReminder.filter(
        tenant_id=tenant_id,
        reminder_type="overdue",
        is_handled=False,
        deleted_at__isnull=True,
    ).count()
    return MobileEquipmentBootstrapOut(
        pending_fault_count=pending_fault_count,
        overdue_maintenance_reminder_count=overdue_maintenance_reminder_count,
    )


@router.get(
    "/pending-approvals",
    response_model=list[ApprovalInstanceResponse],
    summary="手机待我审批（快制造）",
)
async def get_mobile_pending_approvals(
    tenant_id: Annotated[int, Depends(get_current_tenant)],
    user: Annotated[User, Depends(get_current_user)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ApprovalInstanceResponse]:
    rows = await list_mobile_pending_kuaizhizao_approvals(
        tenant_id=tenant_id,
        user_id=user.id,
        skip=skip,
        limit=limit,
    )
    return [ApprovalInstanceResponse.model_validate(row) for row in rows]


@router.get("/home", response_model=MobileHomeBootstrapOut, summary="手机工作台首屏聚合")
async def get_mobile_home_bootstrap(
    tenant_id: Annotated[int, Depends(get_current_tenant)],
    user: Annotated[User, Depends(get_current_user)],
) -> MobileHomeBootstrapOut:
    payload = await fetch_mobile_home_bootstrap(tenant_id=tenant_id, user=user)
    return MobileHomeBootstrapOut.model_validate(payload)


@router.get("/workbench", response_model=list[MobileWorkbenchSectionOut], summary="移动端工作台导航")
async def get_mobile_workbench(
    tenant_id: Annotated[int, Depends(get_current_tenant)],
    user: Annotated[User, Depends(get_current_user)],
    scope: Annotated[
        str,
        Query(description="equipment 等 scope 键；home 为工作台首屏全部分区（单次权限解析）"),
    ] = "equipment",
) -> list[MobileWorkbenchSectionOut]:
    sections: list[dict[str, Any]] = await resolve_mobile_workbench(
        tenant_id=tenant_id,
        user=user,
        scope=scope,
    )
    return [MobileWorkbenchSectionOut.model_validate(s) for s in sections]
