"""星数采边缘配置（整型 id 寻址）。edge-runtime 端点由上游 edge_runtime 模块提供。"""

from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict

from apps.kuaiiot.services.edge_config_service import EdgeConfigService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user

router = APIRouter(tags=["App - 星数采 - 边缘配置"])


class EdgeConfigWrite(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str
    name: str
    device_id: int
    protocol: str
    config: dict[str, Any]
    is_enabled: bool = True


@router.get(
    "/edge-configs",
    dependencies=[Depends(require_permission_codes("kuaiiot:device:display"))],
)
async def api_list_edge_configs(tenant_id: int = Depends(get_current_tenant)) -> list[dict]:
    return await EdgeConfigService.list_config_dicts(tenant_id)


@router.get(
    "/edge-configs/{config_id}",
    dependencies=[Depends(require_permission_codes("kuaiiot:device:display"))],
)
async def api_get_edge_config(config_id: int, tenant_id: int = Depends(get_current_tenant)) -> dict:
    return await EdgeConfigService.get_config(tenant_id, config_id)


@router.put(
    "/edge-configs/{config_id}",
    dependencies=[Depends(require_permission_codes("kuaiiot:device:update"))],
)
async def api_update_edge_config(
    config_id: int,
    payload: EdgeConfigWrite,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
) -> dict:
    return await EdgeConfigService.update_config(
        tenant_id,
        config_id,
        code=payload.code,
        name=payload.name,
        device_id=payload.device_id,
        protocol=payload.protocol,
        config=payload.config,
        is_enabled=payload.is_enabled,
        user_id=getattr(current_user, "id", None),
    )


@router.delete(
    "/edge-configs/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:update"))],
)
async def api_delete_edge_config(
    config_id: int,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    await EdgeConfigService.delete_config(
        tenant_id, config_id, user_id=getattr(current_user, "id", None)
    )


@router.post("/edge-configs/{config_id}/trial", dependencies=[Depends(require_permission_codes("kuaiiot:device:update"))])
async def api_trial(config_id: int, tenant_id: int = Depends(get_current_tenant)) -> dict:
    return await EdgeConfigService.request_trial(tenant_id, config_id)


@router.post(
    "/edge-configs",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:update"))],
)
async def api_save_edge_config(
    payload: EdgeConfigWrite,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
) -> dict:
    return await EdgeConfigService.save_config(
        tenant_id,
        code=payload.code,
        name=payload.name,
        device_id=payload.device_id,
        protocol=payload.protocol,
        config=payload.config,
        is_enabled=payload.is_enabled,
        user_id=getattr(current_user, "id", None),
    )
