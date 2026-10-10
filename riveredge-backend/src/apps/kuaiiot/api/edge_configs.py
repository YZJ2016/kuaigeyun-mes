"""快数采边缘 Agent 配置 API。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from apps.kuaiiot.schemas.iot import (
    EdgeAgentSpecResponse,
    EdgeConfigCreate,
    EdgeConfigListResponse,
    EdgeConfigResponse,
    EdgeConfigUpdate,
)
from apps.kuaiiot.services.edge_config_service import EdgeConfigService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant

router = APIRouter(prefix="/edge-configs", tags=["App - KuaiIoT - Edge Configs"])


@router.get("", response_model=EdgeConfigListResponse, dependencies=[Depends(require_permission_codes("kuaiiot:edge-config:read"))])
async def list_edge_configs(
    tenant_id: int = Depends(get_current_tenant),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    device_id: Optional[int] = None,
    q: Optional[str] = None,
):
    items, total = await EdgeConfigService.list_configs(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        device_id=device_id,
        q=q,
    )
    return EdgeConfigListResponse(
        items=[EdgeConfigResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=EdgeConfigResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission_codes("kuaiiot:edge-config:create"))],
)
async def create_edge_config(data: EdgeConfigCreate, tenant_id: int = Depends(get_current_tenant)):
    item = await EdgeConfigService.create(tenant_id, data)
    return EdgeConfigResponse.model_validate(item)


@router.get("/{uuid}", response_model=EdgeConfigResponse, dependencies=[Depends(require_permission_codes("kuaiiot:edge-config:read"))])
async def get_edge_config(uuid: str, tenant_id: int = Depends(get_current_tenant)):
    item = await EdgeConfigService.get_by_uuid(tenant_id, uuid)
    return EdgeConfigResponse.model_validate(item)


@router.put("/{uuid}", response_model=EdgeConfigResponse, dependencies=[Depends(require_permission_codes("kuaiiot:edge-config:update"))])
async def update_edge_config(uuid: str, data: EdgeConfigUpdate, tenant_id: int = Depends(get_current_tenant)):
    item = await EdgeConfigService.update(tenant_id, uuid, data)
    return EdgeConfigResponse.model_validate(item)


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission_codes("kuaiiot:edge-config:delete"))])
async def delete_edge_config(uuid: str, tenant_id: int = Depends(get_current_tenant)):
    await EdgeConfigService.delete(tenant_id, uuid)


@router.get(
    "/{uuid}/agent-spec",
    response_model=EdgeAgentSpecResponse,
    dependencies=[Depends(require_permission_codes("kuaiiot:edge-config:read"))],
)
async def export_edge_agent_spec(uuid: str, tenant_id: int = Depends(get_current_tenant)):
    return EdgeAgentSpecResponse.model_validate(await EdgeConfigService.export_agent_spec(tenant_id, uuid))
