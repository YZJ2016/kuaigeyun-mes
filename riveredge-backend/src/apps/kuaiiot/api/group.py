"""设备分组。不改星制造设备台账。"""

from fastapi import APIRouter, Depends, status

from apps.kuaiiot.schemas.group import DeviceGroupAssign, GroupCreate, GroupOut, GroupUpdate
from apps.kuaiiot.services import group_service
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user

router = APIRouter(tags=["App - 星数采 - 分组"])


@router.post(
    "/device-groups",
    response_model=GroupOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:update"))],
)
async def api_create_group(
    payload: GroupCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await group_service.create_group(
        tenant_id,
        code=payload.code,
        name=payload.name,
        parent_id=payload.parent_id,
        sort_order=payload.sort_order,
        remark=payload.remark,
        user_id=getattr(current_user, "id", None),
    )


@router.get(
    "/device-groups",
    response_model=list[GroupOut],
    dependencies=[Depends(require_permission_codes("kuaiiot:device:display"))],
)
async def api_list_groups(tenant_id: int = Depends(get_current_tenant)):
    return await group_service.list_groups(tenant_id)


@router.put(
    "/device-groups/{group_id}",
    response_model=GroupOut,
    dependencies=[Depends(require_permission_codes("kuaiiot:device:update"))],
)
async def api_update_group(
    group_id: int,
    payload: GroupUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    fields = payload.model_fields_set
    return await group_service.update_group(
        tenant_id,
        group_id,
        name=payload.name,
        parent_id=payload.parent_id,
        parent_set="parent_id" in fields,
        sort_order=payload.sort_order,
        remark=payload.remark,
        user_id=getattr(current_user, "id", None),
    )


@router.put(
    "/devices/{device_id}/group",
    dependencies=[Depends(require_permission_codes("kuaiiot:device:update"))],
)
async def api_assign_device_group(
    device_id: int,
    payload: DeviceGroupAssign,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
) -> dict:
    device = await group_service.assign_device_group(
        tenant_id,
        device_id,
        payload.group_id,
        user_id=getattr(current_user, "id", None),
    )
    return {"device_id": device.id, "group_id": device.group_id}
