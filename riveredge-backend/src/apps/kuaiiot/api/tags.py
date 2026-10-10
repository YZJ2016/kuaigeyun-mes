"""点位映射 API。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from apps.kuaiiot.schemas.iot import (
    TagDefinitionCreate,
    TagDefinitionListResponse,
    TagDefinitionResponse,
    TagDefinitionUpdate,
)
from apps.kuaiiot.services.tag_service import TagService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant

router = APIRouter(prefix="/tags", tags=["App - KuaiIoT - Tags"])


@router.get("", response_model=TagDefinitionListResponse, dependencies=[Depends(require_permission_codes("kuaiiot:tag:read"))])
async def list_tags(
    tenant_id: int = Depends(get_current_tenant),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    device_id: Optional[int] = None,
    q: Optional[str] = None,
):
    items, total = await TagService.list_tags(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        device_id=device_id,
        q=q,
    )
    return TagDefinitionListResponse(
        items=[TagDefinitionResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=TagDefinitionResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission_codes("kuaiiot:tag:create"))])
async def create_tag(data: TagDefinitionCreate, tenant_id: int = Depends(get_current_tenant)):
    item = await TagService.create(tenant_id, data)
    return TagDefinitionResponse.model_validate(item)


@router.get("/{uuid}", response_model=TagDefinitionResponse, dependencies=[Depends(require_permission_codes("kuaiiot:tag:read"))])
async def get_tag(uuid: str, tenant_id: int = Depends(get_current_tenant)):
    item = await TagService.get_by_uuid(tenant_id, uuid)
    return TagDefinitionResponse.model_validate(item)


@router.put("/{uuid}", response_model=TagDefinitionResponse, dependencies=[Depends(require_permission_codes("kuaiiot:tag:update"))])
async def update_tag(uuid: str, data: TagDefinitionUpdate, tenant_id: int = Depends(get_current_tenant)):
    item = await TagService.update(tenant_id, uuid, data)
    return TagDefinitionResponse.model_validate(item)


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission_codes("kuaiiot:tag:delete"))])
async def delete_tag(uuid: str, tenant_id: int = Depends(get_current_tenant)):
    await TagService.delete(tenant_id, uuid)
