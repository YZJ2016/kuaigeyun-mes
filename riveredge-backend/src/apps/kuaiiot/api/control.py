"""控制面路由。凭据只在建机/轮换当次响应里出现一次。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from apps.kuaiiot.schemas.control import (
    ConnectionCreate,
    ConnectionOut,
    ConnectionUpdate,
    DeviceCreate,
    DeviceOut,
    DeviceTokenOut,
    DeviceUpdate,
    SnapshotOut,
    TagCreate,
    TagOut,
    TagUpdate,
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


@router.get(
    "/connections/{connection_id}",
    response_model=ConnectionOut,
    dependencies=[Depends(require_permission_codes("kuaiiot:connection:display"))],
)
async def api_get_connection(connection_id: int, tenant_id: int = Depends(get_current_tenant)):
    return await control_service.get_connection(tenant_id, connection_id)


@router.put(
    "/connections/{connection_id}",
    response_model=ConnectionOut,
    dependencies=[Depends(require_permission_codes("kuaiiot:connection:create"))],
)
async def api_update_connection(
    connection_id: int,
    payload: ConnectionUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await control_service.update_connection(
        tenant_id, connection_id, payload, user_id=getattr(current_user, "id", None)
    )


@router.delete(
    "/connections/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission_codes("kuaiiot:connection:create"))],
)
async def api_delete_connection(
    connection_id: int,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    await control_service.delete_connection(
        tenant_id, connection_id, user_id=getattr(current_user, "id", None)
    )


@router.post(
    "/devices",
    response_model=DeviceTokenOut,
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


@router.get(
    "/devices/{device_id}",
    response_model=DeviceOut,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:display"))],
)
async def api_get_device(device_id: int, tenant_id: int = Depends(get_current_tenant)):
    return await control_service.get_device(tenant_id, device_id)


@router.delete(
    "/devices/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:update"))],
)
async def api_delete_device(
    device_id: int,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    await control_service.delete_device(
        tenant_id, device_id, user_id=getattr(current_user, "id", None)
    )


@router.put(
    "/devices/{device_id}",
    response_model=DeviceOut,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:update"))],
)
async def api_update_device(
    device_id: int,
    payload: DeviceUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await control_service.update_device(
        tenant_id, device_id, payload, user_id=getattr(current_user, "id", None)
    )


@router.post(
    "/devices/{device_id}/rotate-token",
    response_model=DeviceTokenOut,
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
    "/tags",
    response_model=list[TagOut],
    dependencies=[Depends(require_permission_codes("kuaiiot:tag:display"))],
)
async def api_list_tags(
    device_id: Optional[int] = Query(default=None),
    tenant_id: int = Depends(get_current_tenant),
):
    return await control_service.list_tags(tenant_id, device_id)


@router.get(
    "/tags/{tag_id}",
    response_model=TagOut,
    dependencies=[Depends(require_permission_codes("kuaiiot:tag:display"))],
)
async def api_get_tag(tag_id: int, tenant_id: int = Depends(get_current_tenant)):
    return await control_service.get_tag(tenant_id, tag_id)


@router.put(
    "/tags/{tag_id}",
    response_model=TagOut,
    dependencies=[Depends(require_permission_codes("kuaiiot:tag:create"))],
)
async def api_update_tag(
    tag_id: int,
    payload: TagUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await control_service.update_tag(
        tenant_id, tag_id, payload, user_id=getattr(current_user, "id", None)
    )


@router.delete(
    "/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission_codes("kuaiiot:tag:create"))],
)
async def api_delete_tag(
    tag_id: int,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    await control_service.delete_tag(
        tenant_id, tag_id, user_id=getattr(current_user, "id", None)
    )


@router.get(
    "/devices/{device_id}/snapshots",
    response_model=list[SnapshotOut],
    dependencies=[Depends(require_permission_codes("kuaiiot:snapshot:read"))],
)
async def api_list_snapshots(device_id: int, tenant_id: int = Depends(get_current_tenant)):
    return await control_service.list_device_snapshots(tenant_id, device_id)
