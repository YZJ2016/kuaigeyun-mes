"""数值点位趋势（产品/批量/离线规则走上游 uuid 版端点）。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from apps.kuaiiot.schemas.product import BatchDeviceOut, DeviceBatchCreate, TrendPointOut, TrendWrite
from apps.kuaiiot.services import product_service, trend_service
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user

router = APIRouter(tags=["App - 星数采 - 物模型"])


@router.post(
    "/device-batches",
    response_model=list[BatchDeviceOut],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:create"))],
)
async def api_batch_create_devices(
    payload: DeviceBatchCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await product_service.batch_create_devices(
        tenant_id, payload, user_id=getattr(current_user, "id", None)
    )


@router.post(
    "/trends",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission_codes("kuaiiot:tag:create"))],
)
async def api_write_trend(
    payload: TrendWrite,
    tenant_id: int = Depends(get_current_tenant),
):
    await trend_service.write_trend(
        tenant_id,
        device_id=payload.device_id,
        tag_key=payload.tag_key,
        value=payload.value,
        sampled_at=payload.sampled_at,
    )


@router.get(
    "/trends",
    response_model=list[TrendPointOut],
    dependencies=[Depends(require_permission_codes("kuaiiot:snapshot:read"))],
)
async def api_query_trend(
    device_id: int = Query(...),
    tag_key: str = Query(..., min_length=1),
    start: datetime = Query(...),
    stop: datetime = Query(...),
    tenant_id: int = Depends(get_current_tenant),
):
    return await trend_service.query_trend(
        tenant_id,
        device_id=device_id,
        tag_key=tag_key,
        start=start,
        stop=stop,
    )
