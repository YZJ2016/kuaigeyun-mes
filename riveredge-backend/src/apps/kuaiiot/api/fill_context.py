"""快数采业务填充上下文 API。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from apps.kuaiiot.schemas.iot import FillContextResponse
from apps.kuaiiot.services.fill_context_service import FillContextService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.exceptions.exceptions import ValidationError

router = APIRouter(prefix="/fill-context", tags=["App - KuaiIoT - Fill Context"])


@router.get("", response_model=FillContextResponse, dependencies=[Depends(require_permission_codes("kuaiiot:device:read"))])
async def get_fill_context(
    tenant_id: int = Depends(get_current_tenant),
    context: str = Query(..., pattern="^(reporting|spot_check)$"),
    equipment_uuid: Optional[str] = None,
    device_uuid: Optional[str] = None,
):
    if not equipment_uuid and not device_uuid:
        raise ValidationError("equipment_uuid 与 device_uuid 至少填写一项")
    return await FillContextService.get_fill_context(
        tenant_id=tenant_id,
        equipment_uuid=equipment_uuid,
        device_uuid=device_uuid,
        context=context,
    )
