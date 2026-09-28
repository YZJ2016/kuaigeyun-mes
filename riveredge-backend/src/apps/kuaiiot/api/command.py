"""操作员下发指令。回执在边缘路由上，凭据只出现在路径里。"""

from fastapi import APIRouter, Depends, status

from apps.kuaiiot.schemas.command import CommandCreate, CommandOut
from apps.kuaiiot.services import command_service
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user

router = APIRouter(tags=["App - 星数采 - 指令"])


@router.post(
    "/devices/{device_id}/commands",
    response_model=CommandOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:update"))],
)
async def api_create_command(
    device_id: int,
    payload: CommandCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await command_service.create_command(
        tenant_id,
        device_id,
        function_key=payload.function_key,
        params=payload.params,
        user_id=getattr(current_user, "id", None),
    )


@router.get(
    "/devices/{device_id}/commands",
    response_model=list[CommandOut],
    dependencies=[Depends(require_permission_codes("kuaiiot:device:display"))],
)
async def api_list_commands(device_id: int, tenant_id: int = Depends(get_current_tenant)):
    return await command_service.list_commands(tenant_id, device_id)
