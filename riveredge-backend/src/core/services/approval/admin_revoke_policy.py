"""系统管理员全单据反审旁路（业务参数 parameters.common.admin_revoke_all_documents，默认关）。"""

from __future__ import annotations

from typing import Any, Optional

from infra.models.user import User


async def resolve_admin_revoke_bypass(
    *,
    tenant_id: int,
    user_id: Optional[int] = None,
    user: Optional[User] = None,
) -> bool:
    """组织/平台管理员或系统管理员角色，且业务配置开启时，允许反审全单据。"""
    from core.services.authorization.user_permission_service import UserPermissionService
    from infra.services.business_config_service import BusinessConfigService

    resolved_user = user
    if resolved_user is None and user_id is not None:
        resolved_user = await User.get_or_none(id=int(user_id))
    if resolved_user is None:
        return False
    if not await UserPermissionService.is_admin_bypass(resolved_user, tenant_id):
        return False
    return await BusinessConfigService().get_admin_revoke_all_documents(tenant_id)