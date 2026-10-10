"""快数采告警 API。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from apps.kuaiiot.schemas.iot import (
    AlertListResponse,
    AlertResponse,
    AlertRuleCreate,
    AlertRuleListResponse,
    AlertRuleResponse,
    AlertRuleUpdate,
)
from apps.kuaiiot.services.alert_rule_service import AlertRuleService
from apps.kuaiiot.services.alert_service import AlertService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant, get_current_user_id

router = APIRouter(prefix="/alerts", tags=["App - KuaiIoT - Alerts"])


@router.get("/rules", response_model=AlertRuleListResponse, dependencies=[Depends(require_permission_codes("kuaiiot:alert:read"))])
async def list_alert_rules(
    tenant_id: int = Depends(get_current_tenant),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    device_id: Optional[int] = None,
    is_enabled: Optional[bool] = None,
    q: Optional[str] = None,
):
    items, total = await AlertRuleService.list_rules(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        device_id=device_id,
        is_enabled=is_enabled,
        q=q,
    )
    return AlertRuleListResponse(
        items=[AlertRuleResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/rules",
    response_model=AlertRuleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission_codes("kuaiiot:alert:create"))],
)
async def create_alert_rule(data: AlertRuleCreate, tenant_id: int = Depends(get_current_tenant)):
    item = await AlertRuleService.create(tenant_id, data)
    return AlertRuleResponse.model_validate(item)


@router.put(
    "/rules/{uuid}",
    response_model=AlertRuleResponse,
    dependencies=[Depends(require_permission_codes("kuaiiot:alert:update"))],
)
async def update_alert_rule(uuid: str, data: AlertRuleUpdate, tenant_id: int = Depends(get_current_tenant)):
    item = await AlertRuleService.update(tenant_id, uuid, data)
    return AlertRuleResponse.model_validate(item)


@router.delete(
    "/rules/{uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission_codes("kuaiiot:alert:delete"))],
)
async def delete_alert_rule(uuid: str, tenant_id: int = Depends(get_current_tenant)):
    await AlertRuleService.delete(tenant_id, uuid)


@router.get("", response_model=AlertListResponse, dependencies=[Depends(require_permission_codes("kuaiiot:alert:read"))])
async def list_alerts(
    tenant_id: int = Depends(get_current_tenant),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    device_id: Optional[int] = None,
):
    items, total = await AlertService.list_alerts(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        status=status,
        device_id=device_id,
    )
    return AlertListResponse(
        items=[AlertResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{uuid}/acknowledge",
    response_model=AlertResponse,
    dependencies=[Depends(require_permission_codes("kuaiiot:alert:update"))],
)
async def acknowledge_alert(
    uuid: str,
    tenant_id: int = Depends(get_current_tenant),
    user_id: int = Depends(get_current_user_id),
):
    item = await AlertService.acknowledge(tenant_id, uuid, user_id)
    return AlertResponse.model_validate(item)
