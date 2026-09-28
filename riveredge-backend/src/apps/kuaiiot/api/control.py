"""控制面路由。凭据不出现在响应里。"""

from fastapi import APIRouter, Depends, status

from apps.kuaiiot.schemas.control import (
    ConnectionCreate,
    ConnectionOut,
    DeviceCreate,
    DeviceOut,
    SnapshotOut,
    TagCreate,
    TagOut,
)
from apps.kuaiiot.services import control_service
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user

router = APIRouter(tags=["App - 星数采 - 控制面"])


@router.post(
    "/connections",
    response_model=ConnectionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission_codes("kuaiiot:connection:create"))],
)
async def api_create_connection(
    payload: ConnectionCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await control_service.create_connection(
        tenant_id, payload, user_id=getattr(current_user, "id", None)
    )


@router.get(
    "/connections",
    response_model=list[ConnectionOut],
    dependencies=[Depends(require_permission_codes("kuaiiot:connection:display"))],
)
async def api_list_connections(tenant_id: int = Depends(get_current_tenant)):
    return await control_service.list_connections(tenant_id)


@router.post(
    "/devices",
    response_model=DeviceOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:create"))],
)
async def api_create_device(
    payload: DeviceCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await control_service.create_device(
        tenant_id, payload, user_id=getattr(current_user, "id", None)
    )


@router.get(
    "/devices",
    response_model=list[DeviceOut],
    dependencies=[Depends(require_permission_codes("kuaiiot:device:display"))],
)
async def api_list_devices(tenant_id: int = Depends(get_current_tenant)):
    return await control_service.list_devices(tenant_id)


@router.post(
    "/devices/{device_id}/rotate-token",
    response_model=DeviceOut,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:update"))],
)
async def api_rotate_device_token(
    device_id: int,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await control_service.rotate_device_token(
        tenant_id, device_id, user_id=getattr(current_user, "id", None)
    )


@router.post(
    "/devices/{device_id}/tags",
    response_model=TagOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission_codes("kuaiiot:tag:create"))],
)
async def api_create_tag(
    device_id: int,
    payload: TagCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await control_service.create_tag(
        tenant_id, device_id, payload, user_id=getattr(current_user, "id", None)
    )


@router.get(
    "/devices/{device_id}/snapshots",
    response_model=list[SnapshotOut],
    dependencies=[Depends(require_permission_codes("kuaiiot:snapshot:read"))],
)
async def api_list_snapshots(device_id: int, tenant_id: int = Depends(get_current_tenant)):
    return await control_service.list_device_snapshots(tenant_id, device_id)
