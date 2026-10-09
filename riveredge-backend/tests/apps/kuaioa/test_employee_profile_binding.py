"""员工档案绑定登录账号：user_id 有效性、一账号一档案、一键创建账号。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.kuaioa.schemas.employee import (
    EmployeeAccountQuickCreateRequest,
    EmployeeProfileCreate,
    EmployeeProfileUpdate,
)
from apps.kuaioa.services import employee_service as svc_mod
from apps.kuaioa.services.employee_service import EmployeeProfileService
from infra.exceptions.exceptions import BusinessLogicError


def _query_stub(*, first=None, exists=False):
    query = MagicMock()
    query.first = AsyncMock(return_value=first)
    query.exists = AsyncMock(return_value=exists)
    query.exclude = MagicMock(return_value=query)
    return query


@pytest.mark.asyncio
async def test_validate_linked_user_ok(monkeypatch):
    svc = EmployeeProfileService()
    monkeypatch.setattr(
        svc_mod.User,
        "filter",
        MagicMock(return_value=_query_stub(first=SimpleNamespace(id=9))),
    )
    monkeypatch.setattr(
        svc_mod.KuaioaEmployeeProfile,
        "filter",
        MagicMock(return_value=_query_stub(exists=False)),
    )
    await svc._validate_linked_user(1, 9)


@pytest.mark.asyncio
async def test_validate_linked_user_missing_or_inactive(monkeypatch):
    svc = EmployeeProfileService()
    monkeypatch.setattr(
        svc_mod.User, "filter", MagicMock(return_value=_query_stub(first=None))
    )
    with pytest.raises(BusinessLogicError):
        await svc._validate_linked_user(1, 999)


@pytest.mark.asyncio
async def test_validate_linked_user_already_bound(monkeypatch):
    svc = EmployeeProfileService()
    monkeypatch.setattr(
        svc_mod.User,
        "filter",
        MagicMock(return_value=_query_stub(first=SimpleNamespace(id=9))),
    )
    profile_query = _query_stub(exists=True)
    monkeypatch.setattr(
        svc_mod.KuaioaEmployeeProfile,
        "filter",
        MagicMock(return_value=profile_query),
    )
    with pytest.raises(BusinessLogicError):
        await svc._validate_linked_user(1, 9)


@pytest.mark.asyncio
async def test_validate_linked_user_excludes_self_profile(monkeypatch):
    svc = EmployeeProfileService()
    monkeypatch.setattr(
        svc_mod.User,
        "filter",
        MagicMock(return_value=_query_stub(first=SimpleNamespace(id=9))),
    )
    profile_query = _query_stub(exists=False)
    profile_filter = MagicMock(return_value=profile_query)
    monkeypatch.setattr(svc_mod.KuaioaEmployeeProfile, "filter", profile_filter)
    await svc._validate_linked_user(1, 9, exclude_profile_id=21)
    profile_query.exclude.assert_called_once_with(id=21)


@pytest.mark.asyncio
async def test_create_profile_rejects_unknown_user(monkeypatch):
    svc = EmployeeProfileService()
    monkeypatch.setattr(
        svc_mod.User, "filter", MagicMock(return_value=_query_stub(first=None))
    )
    data = EmployeeProfileCreate(full_name="张三", user_id=999)
    with pytest.raises(BusinessLogicError):
        await svc.create_profile(1, data, 1)


@pytest.mark.asyncio
async def test_update_profile_unbind_user_id(monkeypatch):
    svc = EmployeeProfileService()
    row = SimpleNamespace(
        leave_date=None, status="active", user_id=9, save=AsyncMock()
    )
    monkeypatch.setattr(
        svc_mod.KuaioaEmployeeProfile,
        "get_or_none",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(svc_mod, "touch_updated", AsyncMock())
    monkeypatch.setattr(svc_mod, "model_to_dict", lambda r: {"user_id": r.user_id})
    result = await svc.update_profile(
        1, 21, EmployeeProfileUpdate(user_id=None), 1
    )
    assert result["user_id"] is None


@pytest.mark.asyncio
async def test_create_linked_account_auto_username(monkeypatch):
    svc = EmployeeProfileService()
    captured: dict = {}

    async def fake_create_user(*, tenant_id, data, current_user_id):
        captured["data"] = data
        captured["tenant_id"] = tenant_id
        return SimpleNamespace(id=77, username=data.username)

    monkeypatch.setattr(svc_mod.UserService, "create_user", fake_create_user)
    monkeypatch.setattr(
        svc_mod.User, "filter", MagicMock(return_value=_query_stub(exists=False))
    )
    result = await svc.create_linked_account(
        1,
        EmployeeAccountQuickCreateRequest(full_name="张三"),
        operator_user_id=1,
    )
    assert result["user_id"] == 77
    assert result["username"] == "zhangsan"
    assert len(result["initial_password"]) >= 8
    assert captured["tenant_id"] == 1
    assert captured["data"].role_uuids in (None, [])
    assert captured["data"].is_active is True


@pytest.mark.asyncio
async def test_create_linked_account_explicit_username(monkeypatch):
    svc = EmployeeProfileService()
    captured: dict = {}

    async def fake_create_user(*, tenant_id, data, current_user_id):
        captured["data"] = data
        return SimpleNamespace(id=78, username=data.username)

    monkeypatch.setattr(svc_mod.UserService, "create_user", fake_create_user)
    result = await svc.create_linked_account(
        1,
        EmployeeAccountQuickCreateRequest(full_name="李四", username="lisi01"),
        operator_user_id=1,
    )
    assert result["username"] == "lisi01"
    assert captured["data"].username == "lisi01"


@pytest.mark.asyncio
async def test_suggest_username_suffixes_on_collision(monkeypatch):
    svc = EmployeeProfileService()
    query = _query_stub()
    query.exists = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(svc_mod.User, "filter", MagicMock(return_value=query))
    assert await svc._suggest_username(1, "张三") == "zhangsan2"
