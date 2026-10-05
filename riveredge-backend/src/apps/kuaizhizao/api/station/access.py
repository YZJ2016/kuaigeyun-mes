"""工位终端：触屏专用角色 / 设备设置管理员。"""

from fastapi import Depends, HTTPException

from core.api.deps import get_current_user, get_current_tenant
from core.services.authorization.data_scope_service import DataScopeService
from core.services.authorization.user_permission_service import UserPermissionService
from infra.models.user import User


async def user_has_station_role(user_id: int, tenant_id: int) -> bool:
    roles = await DataScopeService.serialize_active_roles(user_id, tenant_id)
    return any((r.get("role_type") or "") == "station" for r in roles)


async def require_station_role(
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> User:
    if not await user_has_station_role(current_user.id, tenant_id):
        raise HTTPException(status_code=403, detail="仅触屏专用角色可使用工位终端")
    return current_user


async def require_station_settings(
    current_user: User = Depends(require_station_role),
    tenant_id: int = Depends(get_current_tenant),
) -> User:
    if not await UserPermissionService.is_admin_bypass(current_user, tenant_id):
        raise HTTPException(status_code=403, detail="设备设置需要管理员且具备触屏专用角色")
    return current_user
