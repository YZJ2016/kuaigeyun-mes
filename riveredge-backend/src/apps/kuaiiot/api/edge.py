"""边缘运行时。凭据只出现在路径上，响应不带回显字段。"""

from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict

from apps.kuaiiot.schemas.command import CommandResultIn
from apps.kuaiiot.services.command_service import submit_command_result
from apps.kuaiiot.services.edge_config_service import EdgeConfigService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user

router = APIRouter(tags=["App - 星数采 - 边缘运行时"])


class HeartbeatIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    edge_config_code: str
    config_version: int
    agent_version: str
    buffer_pending_count: int
    status: str
    trial_result: dict | None = None


class EdgeConfigWrite(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str
    name: str
    device_id: int
    protocol: str
    config: dict[str, Any]
    is_enabled: bool = True


@router.get("/edge-runtime/{device_token}/config/{edge_config_code}")
async def api_pull_runtime_config(device_token: str, edge_config_code: str) -> dict:
    return await EdgeConfigService.pull_runtime_config(device_token, edge_config_code)


@router.post("/edge-runtime/{device_token}/heartbeat")
async def api_edge_heartbeat(device_token: str, body: HeartbeatIn) -> dict:
    return await EdgeConfigService.record_heartbeat(
        device_token,
        edge_config_code=body.edge_config_code,
        config_version=body.config_version,
        agent_version=body.agent_version,
        buffer_pending_count=body.buffer_pending_count,
        status=body.status,
        trial_result=body.trial_result,
    )


@router.post("/edge-runtime/{device_token}/command-result")
async def api_command_result(device_token: str, body: CommandResultIn) -> dict:
    return await submit_command_result(
        device_token,
        command_uuid=body.command_uuid,
        success=body.success,
        result=body.result,
        error_message=body.error_message,
    )


@router.get(
    "/edge-configs",
    dependencies=[Depends(require_permission_codes("kuaiiot:device:display"))],
)
async def api_list_edge_configs(tenant_id: int = Depends(get_current_tenant)) -> list[dict]:
    return await EdgeConfigService.list_configs(tenant_id)


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
