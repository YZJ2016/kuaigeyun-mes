"""点位模板与预填诊断。告警规则/告警/预填取值走上游 uuid 版端点。"""

from fastapi import APIRouter, Depends

from apps.kuaiiot.schemas.prefill import (
    ApplyTemplateIn,
    ApplyTemplateOut,
    TemplateOut,
)
from apps.kuaiiot.services.tag_template_service import apply_template
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user

router = APIRouter(tags=["App - 星数采 - 预填"])


@router.get("/diagnostics", dependencies=[Depends(require_permission_codes("kuaiiot:device:display"))])
async def api_diagnostics(tenant_id: int = Depends(get_current_tenant)):
    from apps.kuaiiot.services.diagnostic_service import read_diagnostics
    return await read_diagnostics(tenant_id)


@router.get(
    "/tag-templates",
    response_model=list[TemplateOut],
    dependencies=[Depends(require_permission_codes("kuaiiot:template:display"))],
)
async def api_list_templates(tenant_id: int = Depends(get_current_tenant)):
    del tenant_id
    from apps.kuaiiot.tag_templates import TAG_TEMPLATES

    return [
        TemplateOut(code=code, name=item["name"], tags=list(item["tags"]))
        for code, item in TAG_TEMPLATES.items()
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
