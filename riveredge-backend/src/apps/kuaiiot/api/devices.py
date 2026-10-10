"""IoT 设备 API。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from apps.kuaiiot.schemas.iot import (
    DeviceBatchCreate,
    DeviceBatchResponse,
    DeviceCommandCreate,
    DeviceCommandListResponse,
    DeviceCommandResponse,
    DeviceCreate,
    DeviceListResponse,
    DeviceResponse,
    DeviceUpdate,
    MessageLogListResponse,
    MessageLogResponse,
    TagHistoryListResponse,
    TagSnapshotResponse,
)
from apps.kuaiiot.services.command_service import CommandService
from apps.kuaiiot.services.device_service import DeviceService
from apps.kuaiiot.services.message_log_service import MessageLogService
from apps.kuaiiot.services.tag_history_store import TagHistoryStore
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant, get_current_user_id

router = APIRouter(prefix="/devices", tags=["App - KuaiIoT - Devices"])


@router.get("", response_model=DeviceListResponse, dependencies=[Depends(require_permission_codes("kuaiiot:device:read"))])
async def list_devices(
    tenant_id: int = Depends(get_current_tenant),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: Optional[str] = None,
    connection_id: Optional[int] = None,
    group_id: Optional[int] = None,
    is_online: Optional[bool] = None,
):
    items, total = await DeviceService.list_devices(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        q=q,
        connection_id=connection_id,
        group_id=group_id,
        is_online=is_online,
    )
    return DeviceListResponse(
        items=[DeviceResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission_codes("kuaiiot:device:create"))])
async def create_device(data: DeviceCreate, tenant_id: int = Depends(get_current_tenant)):
    item = await DeviceService.create(tenant_id, data)
    return DeviceResponse.model_validate(item)


@router.post("/batch", response_model=DeviceBatchResponse, dependencies=[Depends(require_permission_codes("kuaiiot:device:create"))])
async def batch_create_devices(data: DeviceBatchCreate, tenant_id: int = Depends(get_current_tenant)):
    return await DeviceService.batch_create(tenant_id, data)


@router.get("/{uuid}", response_model=DeviceResponse, dependencies=[Depends(require_permission_codes("kuaiiot:device:read"))])
async def get_device(uuid: str, tenant_id: int = Depends(get_current_tenant)):
    item = await DeviceService.get_by_uuid(tenant_id, uuid)
    return DeviceResponse.model_validate(item)


@router.put("/{uuid}", response_model=DeviceResponse, dependencies=[Depends(require_permission_codes("kuaiiot:device:update"))])
async def update_device(uuid: str, data: DeviceUpdate, tenant_id: int = Depends(get_current_tenant)):
    item = await DeviceService.update(tenant_id, uuid, data)
    return DeviceResponse.model_validate(item)


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission_codes("kuaiiot:device:delete"))])
async def delete_device(uuid: str, tenant_id: int = Depends(get_current_tenant)):
    await DeviceService.delete(tenant_id, uuid)


@router.post("/{uuid}/rotate-token", response_model=DeviceResponse, dependencies=[Depends(require_permission_codes("kuaiiot:device:update"))])
async def rotate_device_token(uuid: str, tenant_id: int = Depends(get_current_tenant)):
    item = await DeviceService.rotate_token(tenant_id, uuid)
    return DeviceResponse.model_validate(item)


@router.get("/{uuid}/snapshots", response_model=list[TagSnapshotResponse], dependencies=[Depends(require_permission_codes("kuaiiot:device:read"))])
async def list_device_snapshots(uuid: str, tenant_id: int = Depends(get_current_tenant)):
    device = await DeviceService.get_by_uuid(tenant_id, uuid)
    snapshots = await DeviceService.list_snapshots(tenant_id, device.id)
    return [TagSnapshotResponse.model_validate(item) for item in snapshots]


@router.get("/{uuid}/history", response_model=TagHistoryListResponse, dependencies=[Depends(require_permission_codes("kuaiiot:device:read"))])
async def list_device_history(
    uuid: str,
    tenant_id: int = Depends(get_current_tenant),
    tag_key: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
):
    device = await DeviceService.get_by_uuid(tenant_id, uuid)
    tsdb_configured = await TagHistoryStore.is_configured(tenant_id)
    items = await DeviceService.list_history(
        tenant_id=tenant_id,
        device_id=device.id,
        tag_key=tag_key,
        limit=limit,
    )
    return TagHistoryListResponse(items=items, tsdb_configured=tsdb_configured)


@router.post(
    "/{uuid}/commands",
    response_model=DeviceCommandResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:update"))],
)
async def create_device_command(
    uuid: str,
    data: DeviceCommandCreate,
    tenant_id: int = Depends(get_current_tenant),
    user_id: int = Depends(get_current_user_id),
):
    device = await DeviceService.get_by_uuid(tenant_id, uuid)
    item = await CommandService.create_command(tenant_id, device, data, requested_by=user_id)
    return DeviceCommandResponse.model_validate(item)


@router.get(
    "/{uuid}/commands",
    response_model=DeviceCommandListResponse,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:read"))],
)
async def list_device_commands(
    uuid: str,
    tenant_id: int = Depends(get_current_tenant),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    device = await DeviceService.get_by_uuid(tenant_id, uuid)
    items, total = await CommandService.list_commands(
        tenant_id=tenant_id,
        device_id=device.id,
        page=page,
        page_size=page_size,
    )
    return DeviceCommandListResponse(
        items=[DeviceCommandResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{uuid}/message-logs",
    response_model=MessageLogListResponse,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:read"))],
)
async def list_device_message_logs(
    uuid: str,
    tenant_id: int = Depends(get_current_tenant),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    direction: Optional[str] = None,
    msg_type: Optional[str] = None,
):
    device = await DeviceService.get_by_uuid(tenant_id, uuid)
    items, total = await MessageLogService.list_logs(
        tenant_id=tenant_id,
        device_id=device.id,
        page=page,
        page_size=page_size,
        direction=direction,
        msg_type=msg_type,
    )
    return MessageLogListResponse(
        items=[MessageLogResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
