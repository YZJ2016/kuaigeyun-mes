"""产品物模型、批量建设备、离线规则与趋势。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from apps.kuaiiot.schemas.prefill import AlertRuleOut
from apps.kuaiiot.schemas.product import (
    BatchDeviceOut,
    DeviceBatchCreate,
    OfflineRuleCreate,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    TrendPointOut,
    TrendWrite,
)
from apps.kuaiiot.services import offline_alert_service, product_service, trend_service
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user

router = APIRouter(tags=["App - 星数采 - 物模型"])


@router.post(
    "/products",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:create"))],
)
async def api_create_product(
    payload: ProductCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    row = await product_service.create_product(
        tenant_id, payload, user_id=getattr(current_user, "id", None)
    )
    return ProductOut.model_validate(row)


@router.get(
    "/products",
    response_model=list[ProductOut],
    dependencies=[Depends(require_permission_codes("kuaiiot:device:display"))],
)
async def api_list_products(tenant_id: int = Depends(get_current_tenant)):
    rows = await product_service.list_products(tenant_id)
    return [ProductOut.model_validate(row) for row in rows]


@router.post(
    "/products/load-builtin",
    response_model=dict[str, int],
    dependencies=[Depends(require_permission_codes("kuaiiot:device:create"))],
)
async def api_load_builtin_products(
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await product_service.load_builtin_products(tenant_id, user_id=getattr(current_user, "id", None))


@router.get(
    "/products/{product_id}",
    response_model=ProductOut,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:display"))],
)
async def api_get_product(product_id: int, tenant_id: int = Depends(get_current_tenant)):
    row = await product_service.get_product(tenant_id, product_id)
    return ProductOut.model_validate(row)


@router.put(
    "/products/{product_id}",
    response_model=ProductOut,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:update"))],
)
async def api_update_product(
    product_id: int,
    payload: ProductUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    row = await product_service.update_product(
        tenant_id, product_id, payload, user_id=getattr(current_user, "id", None)
    )
    return ProductOut.model_validate(row)


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:update"))],
)
async def api_delete_product(
    product_id: int,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    await product_service.delete_product(
        tenant_id, product_id, user_id=getattr(current_user, "id", None)
    )


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
    "/offline-rules",
    response_model=AlertRuleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission_codes("kuaiiot:alert:create"))],
)
async def api_create_offline_rule(
    payload: OfflineRuleCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    rule = await offline_alert_service.create_offline_rule(
        tenant_id,
        code=payload.code,
        name=payload.name,
        device_id=payload.device_id,
        severity=payload.severity,
        user_id=getattr(current_user, "id", None),
    )
    return AlertRuleOut.model_validate(rule)


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
