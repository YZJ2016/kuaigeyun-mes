"""连接源 API。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from apps.kuaiiot.schemas.iot import (
    ConnectionCreate,
    ConnectionListResponse,
    ConnectionRecentMessage,
    ConnectionRecentMessageListResponse,
    ConnectionResponse,
    ConnectionUpdate,
    DiscoveredMqttDevice,
    DiscoveredMqttDeviceListResponse,
)
from apps.kuaiiot.services.connection_service import ConnectionService
from apps.kuaiiot.services.mqtt_device_discovery import MqttDeviceDiscoveryService
from apps.kuaiiot.services.mqtt_message_buffer import MqttMessageBuffer
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant

router = APIRouter(prefix="/connections", tags=["App - KuaiIoT - Connections"])


@router.get("", response_model=ConnectionListResponse, dependencies=[Depends(require_permission_codes("kuaiiot:connection:read"))])
async def list_connections(
    tenant_id: int = Depends(get_current_tenant),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    q: Optional[str] = None,
    connection_type: Optional[str] = None,
):
    items, total = await ConnectionService.list_connections(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        q=q,
        connection_type=connection_type,
    )
    return ConnectionListResponse(
        items=[ConnectionResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/discovered-devices",
    response_model=DiscoveredMqttDeviceListResponse,
    dependencies=[Depends(require_permission_codes("kuaiiot:connection:read"))],
)
async def list_all_discovered_mqtt_devices(
    tenant_id: int = Depends(get_current_tenant),
    limit: int = Query(200, ge=1, le=200),
):
    """从 MQTT 现场设备名录中列出可选设备（报文 devices[] 抽出后持久化）。"""
    devices = await MqttDeviceDiscoveryService.list_discovered_devices(
        tenant_id,
        None,
        message_limit=limit,
    )
    return DiscoveredMqttDeviceListResponse(
        items=[DiscoveredMqttDevice.model_validate(device) for device in devices],
        total=len(devices),
    )


@router.post("", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission_codes("kuaiiot:connection:create"))])
async def create_connection(
    data: ConnectionCreate,
    tenant_id: int = Depends(get_current_tenant),
):
    item = await ConnectionService.create(tenant_id, data)
    return ConnectionResponse.model_validate(item)


@router.get("/{uuid}", response_model=ConnectionResponse, dependencies=[Depends(require_permission_codes("kuaiiot:connection:read"))])
async def get_connection(uuid: str, tenant_id: int = Depends(get_current_tenant)):
    item = await ConnectionService.get_by_uuid(tenant_id, uuid)
    return ConnectionResponse.model_validate(item)


@router.get(
    "/{uuid}/recent-messages",
    response_model=ConnectionRecentMessageListResponse,
    dependencies=[Depends(require_permission_codes("kuaiiot:connection:read"))],
)
async def list_connection_recent_messages(
    uuid: str,
    tenant_id: int = Depends(get_current_tenant),
    limit: int = Query(20, ge=1, le=50),
):
    """查看 MQTT 连接源最近收到的原始消息体。"""
    item = await ConnectionService.get_by_uuid(tenant_id, uuid)
    messages = await MqttMessageBuffer.list_persisted(tenant_id, item.id, limit=limit)
    return ConnectionRecentMessageListResponse(
        items=[ConnectionRecentMessage.model_validate(msg) for msg in messages],
        total=len(messages),
    )


@router.get(
    "/{uuid}/discovered-devices",
    response_model=DiscoveredMqttDeviceListResponse,
    dependencies=[Depends(require_permission_codes("kuaiiot:connection:read"))],
)
async def list_connection_discovered_devices(
    uuid: str,
    tenant_id: int = Depends(get_current_tenant),
    limit: int = Query(50, ge=1, le=50),
):
    """从 MQTT 现场设备名录列出可选设备。"""
    item = await ConnectionService.get_by_uuid(tenant_id, uuid)
    devices = await MqttDeviceDiscoveryService.list_discovered_devices(
        tenant_id,
        item.id,
        message_limit=limit,
    )
    return DiscoveredMqttDeviceListResponse(
        items=[DiscoveredMqttDevice.model_validate(device) for device in devices],
        total=len(devices),
    )


@router.put("/{uuid}", response_model=ConnectionResponse, dependencies=[Depends(require_permission_codes("kuaiiot:connection:update"))])
async def update_connection(
    uuid: str,
    data: ConnectionUpdate,
    tenant_id: int = Depends(get_current_tenant),
):
    item = await ConnectionService.update(tenant_id, uuid, data)
    return ConnectionResponse.model_validate(item)


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission_codes("kuaiiot:connection:delete"))])
async def delete_connection(uuid: str, tenant_id: int = Depends(get_current_tenant)):
    await ConnectionService.delete(tenant_id, uuid)
