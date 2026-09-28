"""点位模板、阈值规则与报工/点检预填。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from apps.kuaiiot.schemas.prefill import (
    AlertOut,
    AlertRuleCreate,
    AlertRuleOut,
    ApplyTemplateIn,
    ApplyTemplateOut,
    FillContextOut,
    TemplateOut,
)
from apps.kuaiiot.services import alert_service, prefill_service
from apps.kuaiiot.services.tag_template_service import TagTemplateService, apply_template
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user

router = APIRouter(tags=["App - 星数采 - 预填"])


@router.get(
    "/tag-templates",
    response_model=list[TemplateOut],
    dependencies=[Depends(require_permission_codes("kuaiiot:template:display"))],
)
async def api_list_templates(tenant_id: int = Depends(get_current_tenant)):
    del tenant_id
    return [
        TemplateOut(code=item.code, name=item.name, tags=item.tags)
        for item in TagTemplateService.list_templates()
    ]


@router.post(
    "/devices/{device_id}/template",
    response_model=ApplyTemplateOut,
    dependencies=[Depends(require_permission_codes("kuaiiot:template:create"))],
)
async def api_apply_template(
    device_id: int,
    payload: ApplyTemplateIn,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    tag_keys = await apply_template(
        tenant_id,
        device_id,
        payload.code,
        user_id=getattr(current_user, "id", None),
    )
    return ApplyTemplateOut(code=payload.code.strip(), tag_keys=tag_keys)


@router.post(
    "/alert-rules",
    response_model=AlertRuleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission_codes("kuaiiot:alert:create"))],
)
async def api_create_alert_rule(
    payload: AlertRuleCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    rule = await alert_service.create_rule(
        tenant_id,
        payload,
        user_id=getattr(current_user, "id", None),
    )
    return AlertRuleOut.model_validate(rule)


@router.get(
    "/alerts",
    response_model=list[AlertOut],
    dependencies=[Depends(require_permission_codes("kuaiiot:alert:display"))],
)
async def api_list_alerts(tenant_id: int = Depends(get_current_tenant)):
    rows = await alert_service.list_alerts(tenant_id)
    return [AlertOut.model_validate(row) for row in rows]


@router.get(
    "/fill-context",
    response_model=FillContextOut,
    dependencies=[Depends(require_permission_codes("kuaiiot:fill:read"))],
)
async def api_fill_context(
    equipment_uuid: str = Query(..., min_length=1),
    context: Optional[str] = Query(default=None),
    tenant_id: int = Depends(get_current_tenant),
):
    return await prefill_service.read_fill_context(tenant_id, equipment_uuid, context)
