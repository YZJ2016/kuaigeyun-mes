"""快数采产品物模型 API。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from apps.kuaiiot.schemas.iot import (
    LoadBuiltinProductPresetsResponse,
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)
from apps.kuaiiot.services.product_service import ProductService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant

router = APIRouter(prefix="/products", tags=["App - KuaiIoT - Products"])


@router.get("", response_model=ProductListResponse, dependencies=[Depends(require_permission_codes("kuaiiot:product:read"))])
async def list_products(
    tenant_id: int = Depends(get_current_tenant),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    q: Optional[str] = None,
):
    items, total = await ProductService.list_products(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        q=q,
    )
    return ProductListResponse(
        items=[ProductResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/load-builtin-presets",
    response_model=LoadBuiltinProductPresetsResponse,
    dependencies=[Depends(require_permission_codes("kuaiiot:product:create"))],
)
async def load_builtin_product_presets(tenant_id: int = Depends(get_current_tenant)):
    return await ProductService.load_builtin_presets(tenant_id)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission_codes("kuaiiot:product:create"))])
async def create_product(data: ProductCreate, tenant_id: int = Depends(get_current_tenant)):
    item = await ProductService.create(tenant_id, data)
    return ProductResponse.model_validate(item)


@router.get("/{uuid}", response_model=ProductResponse, dependencies=[Depends(require_permission_codes("kuaiiot:product:read"))])
async def get_product(uuid: str, tenant_id: int = Depends(get_current_tenant)):
    item = await ProductService.get_by_uuid(tenant_id, uuid)
    return ProductResponse.model_validate(item)


@router.put("/{uuid}", response_model=ProductResponse, dependencies=[Depends(require_permission_codes("kuaiiot:product:update"))])
async def update_product(uuid: str, data: ProductUpdate, tenant_id: int = Depends(get_current_tenant)):
    item = await ProductService.update(tenant_id, uuid, data)
    return ProductResponse.model_validate(item)


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission_codes("kuaiiot:product:delete"))])
async def delete_product(uuid: str, tenant_id: int = Depends(get_current_tenant)):
    await ProductService.delete(tenant_id, uuid)
