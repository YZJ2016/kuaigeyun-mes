"""BaseModel 审计字段写入（创建人/更新人 ID + 姓名快照）。"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from infra.models.user import User


def user_audit_display_name(user: User) -> str:
    name = (user.full_name or "").strip()
    if name:
        return name
    return (user.username or "").strip() or str(user.id)


def _infra_admin_display_name(*, full_name: str | None, username: str | None, admin_id: int) -> str:
    name = (full_name or "").strip()
    if name:
        return name
    uname = (username or "").strip()
    if uname:
        return uname
    return f"平台超级管理员#{admin_id}"


async def resolve_audit_actor(tenant_id: int, user_id: int) -> Tuple[int, str]:
    """解析写审计字段的操作人。

    优先当前租户内用户；平台超管跨租户操作时回落到
    ``core_users.is_infra_admin`` 或 ``infra_superadmin``（不要求属于目标租户）。
    """
    user = await User.filter(
        id=user_id,
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    ).first()
    if user:
        return user.id, user_audit_display_name(user)

    platform_user = await User.filter(
        id=user_id,
        is_infra_admin=True,
        deleted_at__isnull=True,
    ).first()
    if platform_user:
        return platform_user.id, user_audit_display_name(platform_user)

    from infra.models.infra_superadmin import InfraSuperAdmin

    admin = await InfraSuperAdmin.filter(id=user_id, is_active=True).first()
    if admin:
        return admin.id, _infra_admin_display_name(
            full_name=admin.full_name,
            username=admin.username,
            admin_id=admin.id,
        )

    raise ValueError(f"操作用户不存在: id={user_id}, tenant_id={tenant_id}")


def audit_fields_for_create(user_id: int, display_name: str) -> Dict[str, Any]:
    return {
        "created_by": user_id,
        "created_by_name": display_name,
        "updated_by": user_id,
        "updated_by_name": display_name,
    }


def audit_fields_for_update(user_id: int, display_name: str) -> Dict[str, Any]:
    return {
        "updated_by": user_id,
        "updated_by_name": display_name,
    }


async def load_audit_fields_for_create(
    tenant_id: int,
    current_user_id: int,
) -> Dict[str, Any]:
    user_id, name = await resolve_audit_actor(tenant_id, current_user_id)
    return audit_fields_for_create(user_id, name)


async def load_audit_fields_for_update(
    tenant_id: int,
    current_user_id: int,
) -> Dict[str, Any]:
    user_id, name = await resolve_audit_actor(tenant_id, current_user_id)
    return audit_fields_for_update(user_id, name)
