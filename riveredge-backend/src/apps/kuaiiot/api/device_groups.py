"""快数采设备分组 API。"""

from typing import Optional

from fastapi import APIRouter, Depends, status

from apps.kuaiiot.schemas.iot import (
    DeviceGroupCreate,
    DeviceGroupListResponse,
    DeviceGroupResponse,
    DeviceGroupTreeResponse,
    DeviceGroupUpdate,
)
from apps.kuaiiot.services.device_group_service import DeviceGroupService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant

router = APIRouter(prefix="/device-groups", tags=["App - KuaiIoT - Device Groups"])


@router.get("", response_model=DeviceGroupListResponse, dependencies=[Depends(require_permission_codes("kuaiiot:device-group:read"))])
async def list_device_groups(tenant_id: int = Depends(get_current_tenant)):
    items = await DeviceGroupService.list_groups(tenant_id)
    return DeviceGroupListResponse(
        items=[DeviceGroupResponse.model_validate(item) for item in items],
        total=len(items),
    )


@router.get("/tree", response_model=DeviceGroupTreeResponse, dependencies=[Depends(require_permission_codes("kuaiiot:device-group:read"))])
async def get_device_group_tree(tenant_id: int = Depends(get_current_tenant)):
    groups = await DeviceGroupService.list_groups(tenant_id)
    return DeviceGroupTreeResponse(items=DeviceGroupService.build_tree(groups))


@router.post(
    "",
    response_model=DeviceGroupResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission_codes("kuaiiot:device-group:create"))],
)
async def create_device_group(data: DeviceGroupCreate, tenant_id: int = Depends(get_current_tenant)):
    item = await DeviceGroupService.create(tenant_id, data)
    return DeviceGroupResponse.model_validate(item)


@router.get("/{uuid}", response_model=DeviceGroupResponse, dependencies=[Depends(require_permission_codes("kuaiiot:device-group:read"))])
async def get_device_group(uuid: str, tenant_id: int = Depends(get_current_tenant)):
    item = await DeviceGroupService.get_by_uuid(tenant_id, uuid)
    return DeviceGroupResponse.model_validate(item)


@router.put("/{uuid}", response_model=DeviceGroupResponse, dependencies=[Depends(require_permission_codes("kuaiiot:device-group:update"))])
async def update_device_group(uuid: str, data: DeviceGroupUpdate, tenant_id: int = Depends(get_current_tenant)):
    item = await DeviceGroupService.update(tenant_id, uuid, data)
    return DeviceGroupResponse.model_validate(item)


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission_codes("kuaiiot:device-group:delete"))])
async def delete_device_group(uuid: str, tenant_id: int = Depends(get_current_tenant)):
    await DeviceGroupService.delete(tenant_id, uuid)
