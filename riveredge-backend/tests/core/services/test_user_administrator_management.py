from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.domain.security.password_policy import (
    default_simple_reset_password,
    password_policy_from_security,
    validate_login_password,
)
from core.schemas.user import UserUpdate
from core.services.user import user_service as service
from core.services.authorization.user_permission_service import UserPermissionService
from infra.exceptions.exceptions import AuthorizationError


@pytest.mark.parametrize("min_length", [6, 8, 14, 128])
def test_simple_reset_password_respects_tenant_minimum_length(min_length):
    policy = password_policy_from_security(
        {"password_mode": "simple", "password_min_length": min_length}
    )
    password = default_simple_reset_password(policy)
    assert len(password) >= min_length
    validate_login_password(password, policy)


def setup(monkeypatch, *, administrator=False, target_admin=False):
    target = SimpleNamespace(id=51, tenant_id=1, username="fixture", full_name="fixture",
        department_id=None, position_id=None, is_active=True, is_tenant_admin=target_admin,
        is_infra_admin=False, save=AsyncMock(), fetch_related=AsyncMock())
    actor = SimpleNamespace(id=50, tenant_id=1, username="operator", full_name="操作员",
        is_active=True, is_tenant_admin=administrator, is_infra_admin=False)
    query = MagicMock()
    query.first = AsyncMock(return_value=target)
    query.using_db.return_value = query
    monkeypatch.setattr(service.User, "filter", MagicMock(return_value=query))
    monkeypatch.setattr(service.User, "get_or_none", AsyncMock(return_value=actor))
    monkeypatch.setattr(UserPermissionService, "get_user_roles", AsyncMock(return_value=[]))
    @asynccontextmanager
    async def transaction():
        yield object()
    monkeypatch.setattr(service, "in_transaction", transaction)
    monkeypatch.setattr(service.PermissionVersionService, "bump", AsyncMock())
    return actor, target


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", ["is_tenant_admin", "is_infra_admin"])
async def test_user_editor_cannot_promote_administrator(monkeypatch, flag):
    _, target = setup(monkeypatch)
    with pytest.raises(AuthorizationError):
        await service.UserService.update_user(1, "fixture", UserUpdate(**{flag: True}), 50)
    target.save.assert_not_awaited()
    assert not getattr(target, flag)


@pytest.mark.asyncio
async def test_user_editor_cannot_reset_administrator_password(monkeypatch):
    _, target = setup(monkeypatch, target_admin=True)
    with pytest.raises(AuthorizationError):
        await service.UserService.update_user(1, "fixture", UserUpdate(password="fixture-password"), 50)
    target.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_tenant_administrator_can_promote_user(monkeypatch):
    _, target = setup(monkeypatch, administrator=True)
    await service.UserService.update_user(1, "fixture", UserUpdate(is_tenant_admin=True), 50)
    assert target.is_tenant_admin
    target.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_editor_can_update_regular_profile(monkeypatch):
    _, target = setup(monkeypatch)
    target.full_name = "旧姓名"
    await service.UserService.update_user(1, "fixture", UserUpdate(full_name="新姓名", is_tenant_admin=False), 50)
    assert target.full_name == "新姓名"
    assert not target.is_tenant_admin


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", ["is_tenant_admin", "is_infra_admin"])
async def test_user_creator_cannot_create_administrator(monkeypatch, flag):
    from core.schemas.user import UserCreate
    setup(monkeypatch)
    create = AsyncMock()
    monkeypatch.setattr(service.User, "create", create)
    with pytest.raises(AuthorizationError):
        await service.UserService.create_user(1, UserCreate(
            tenant_id=1, username="new-fixture", password="fixture-password", **{flag: True},
        ), 50)
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_tenant_administrator_cannot_set_platform_flag(monkeypatch):
    _, target = setup(monkeypatch, administrator=True)
    with pytest.raises(AuthorizationError):
        await service.UserService.update_user(1, "fixture", UserUpdate(is_infra_admin=True), 50)
    target.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_foreign_tenant_administrator_cannot_promote_user(monkeypatch):
    actor, target = setup(monkeypatch, administrator=True)
    actor.tenant_id = 2
    with pytest.raises(AuthorizationError):
        await service.UserService.update_user(1, "fixture", UserUpdate(is_tenant_admin=True), 50, current_user=actor)
    target.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_virtual_platform_administrator_keeps_its_authenticated_identity(monkeypatch):
    actor, target = setup(monkeypatch)
    actor.tenant_id, actor.is_infra_admin = None, True
    service.User.get_or_none.side_effect = AssertionError("平台身份不得按重叠数字 ID 重新查询租户账号")
    await service.UserService.update_user(1, "fixture", UserUpdate(is_tenant_admin=True), 50, current_user=actor)
    assert target.is_tenant_admin


@pytest.mark.asyncio
@pytest.mark.parametrize("by_name", [False, True])
async def test_user_editor_cannot_grant_administrator_role(monkeypatch, by_name):
    from core.services.user import user_administrator_guard as guard
    _, target = setup(monkeypatch)
    role = SimpleNamespace(code="ordinary" if by_name else "ADMIN", name="系统管理员" if by_name else "fixture")
    query = MagicMock()
    query.all = AsyncMock(return_value=[role])
    monkeypatch.setattr(guard.Role, "filter", MagicMock(return_value=query))
    with pytest.raises(AuthorizationError):
        await service.UserService.update_user(1, "fixture", UserUpdate(role_uuids=["fixture-role"]), 50)
    target.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_editor_cannot_reset_role_administrator(monkeypatch):
    _, target = setup(monkeypatch)
    role = SimpleNamespace(code="ADMIN", name="fixture")
    monkeypatch.setattr(UserPermissionService, "get_user_roles", AsyncMock(side_effect=lambda user_id, tenant_id: [role] if user_id == 51 else []))
    with pytest.raises(AuthorizationError):
        await service.UserService.update_user(1, "fixture", UserUpdate(password="fixture-password"), 50)
    target.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_system_administrator_role_can_manage_admins(monkeypatch):
    _, target = setup(monkeypatch)
    role = SimpleNamespace(code="ADMIN", name="fixture")
    monkeypatch.setattr(UserPermissionService, "get_user_roles", AsyncMock(side_effect=lambda user_id, tenant_id: [role] if user_id == 50 else []))
    await service.UserService.update_user(1, "fixture", UserUpdate(is_tenant_admin=True), 50)
    assert target.is_tenant_admin


@pytest.mark.asyncio
async def test_http_user_edit_permission_does_not_grant_admin_management(monkeypatch):
    import httpx
    from fastapi import FastAPI
    from core.api.users import users as api
    from core.services.authorization.access_control_service import AccessControlService
    actor, target = setup(monkeypatch)
    monkeypatch.setattr(AccessControlService, "check_access", AsyncMock(return_value=SimpleNamespace(allowed=True)))
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.soil_get_current_user] = lambda: actor
    app.dependency_overrides[api.get_current_tenant] = lambda: 1
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        result = await client.put("/users/fixture", json={"is_tenant_admin": True})
    assert result.status_code == 403, result.text
    target.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_service_adapter_preserves_authenticated_platform_actor(monkeypatch):
    from core.services.interfaces.implementations.user_service_impl import UserServiceImpl
    actor, _ = setup(monkeypatch)
    create = AsyncMock()
    monkeypatch.setattr(service.UserService, "create_user", create)
    await UserServiceImpl().create_user(1, object(), 50, current_user=actor)
    assert create.call_args.kwargs["current_user"] is actor


@pytest.mark.asyncio
async def test_audit_actor_resolves_platform_administrator(monkeypatch):
    """resolve_audit_actor：租户过滤 miss 时放行 NULL 租户 + is_infra_admin 的平台管理员。"""
    from core.utils import model_audit

    platform_admin = SimpleNamespace(
        id=1, tenant_id=None, is_infra_admin=True, username="sa", full_name="平台管理员",
    )

    def _fake_filter(**kwargs):
        q = MagicMock()
        q.first = AsyncMock(
            return_value=platform_admin if kwargs.get("tenant_id__isnull") else None
        )
        return q

    monkeypatch.setattr(model_audit.User, "filter", _fake_filter)
    user_id, name = await model_audit.resolve_audit_actor(5, 1)
    assert (user_id, name) == (1, "平台管理员")


@pytest.mark.asyncio
async def test_audit_actor_rejects_plain_null_tenant_user(monkeypatch):
    """resolve_audit_actor：tenant_id 为 NULL 但非 is_infra_admin 的用户不得逃逸租户过滤。"""
    from core.utils import model_audit

    monkeypatch.setattr(
        model_audit.User,
        "filter",
        lambda **_kwargs: MagicMock(first=AsyncMock(return_value=None)),
    )
    with pytest.raises(ValueError):
        await model_audit.resolve_audit_actor(5, 1)
