"""工位终端角色纯度与 STATION_TERMINAL 预设测试（纯 mock，不连库）。"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.schemas.role import RoleUpdate
from core.schemas.user import UserCreate, UserUpdate
from core.services.authorization import role_service as role_service_module
from core.services.authorization.permission_registry_service import (
    PermissionRegistryService,
)
from core.services.authorization.permission_sync_service import PermissionSyncService
from core.services.authorization.role_service import RoleService
from core.services.authorization.role_type_policy import (
    assert_pure_role_types,
    is_station_role_type,
)
from core.services.user import user_service as user_service_module
from core.services.user.user_service import UserService
from infra.exceptions.exceptions import ValidationError

STATION_HOME_PATH = "/apps/kuaizhizao/production-execution/station"


def _qs(**overrides) -> MagicMock:
    """可链式 mock 的 queryset：默认 all/first/values_list 返回空。"""
    qs = MagicMock()
    qs.all = AsyncMock(return_value=[])
    qs.first = AsyncMock(return_value=None)
    qs.exists = AsyncMock(return_value=False)
    qs.values_list = AsyncMock(return_value=[])
    qs.values = AsyncMock(return_value=[])
    qs.delete = AsyncMock(return_value=0)
    qs.using_db = MagicMock(return_value=qs)
    qs.exclude = MagicMock(return_value=qs)
    for key, value in overrides.items():
        setattr(qs, key, value)
    return qs


def _role(role_id: int, role_type: str, code: str = "R") -> MagicMock:
    role = MagicMock()
    role.id = role_id
    role.role_type = role_type
    role.code = code
    return role


# ---------------- 纯度纯函数 ----------------


def test_pure_role_types_all_station_ok():
    assert_pure_role_types(["station", "STATION", " station "])


def test_pure_role_types_all_non_station_ok():
    assert_pure_role_types(["internal", "external", None])


@pytest.mark.parametrize(
    "role_types",
    [
        ["station", "internal"],
        ["station", "external"],
        ["internal", "station", "external"],
    ],
)
def test_pure_role_types_mixed_rejected(role_types):
    with pytest.raises(ValidationError):
        assert_pure_role_types(role_types)


def test_is_station_role_type_normalizes():
    assert is_station_role_type("STATION")
    assert is_station_role_type(" station ")
    assert not is_station_role_type("internal")
    assert not is_station_role_type(None)


# ---------------- STATION_TERMINAL 预设加载 ----------------


def _install_load_preset_mocks(monkeypatch):
    existing_codes: set[str] = set()
    created: list[dict] = []

    def _role_filter(**kwargs):
        qs = _qs()
        code = kwargs.get("code")
        qs.exists = AsyncMock(return_value=(code in existing_codes) if code else False)
        return qs

    async def _role_create(**kwargs):
        existing_codes.add(kwargs["code"])
        created.append(kwargs)
        role = MagicMock()
        role.id = 100 + len(created)
        role.code = kwargs["code"]
        role.role_type = kwargs["role_type"]
        return role

    assign = AsyncMock()
    monkeypatch.setattr(role_service_module.Role, "filter", _role_filter)
    monkeypatch.setattr(
        role_service_module.Role, "create", AsyncMock(side_effect=_role_create)
    )
    monkeypatch.setattr(RoleService, "_assign_preset_permissions", assign)
    return existing_codes, created, assign


def test_station_terminal_preset_definition():
    item = next(i for i in RoleService.PRESET_ROLES if i["code"] == "STATION_TERMINAL")
    assert item["role_type"] == "station"
    assert item["home_path"] == STATION_HOME_PATH
    assert (
        RoleService.resolve_preset_functional_domain("STATION_TERMINAL") == "production"
    )
    explicit = RoleService.PRESET_ROLE_EXPLICIT_PERMISSION_CODES["STATION_TERMINAL"]
    assert "kuaizhizao:production-execution-reporting:assign" not in explicit
    assert "kuaizhizao:production-execution-terminal:read" in explicit
    assert "kuaizhizao:production-execution-terminal:execute" in explicit


@pytest.mark.asyncio
async def test_load_preset_creates_station_terminal(monkeypatch):
    _, created, assign = _install_load_preset_mocks(monkeypatch)

    count = await RoleService.load_preset_sme(
        tenant_id=1, current_user_id=1, codes=["STATION_TERMINAL"]
    )

    assert count == 1
    assert created[0]["code"] == "STATION_TERMINAL"
    assert created[0]["role_type"] == "station"
    assert created[0]["external_partner_type"] is None
    assert created[0]["functional_domain"] == "production"
    assert created[0]["home_path"] == STATION_HOME_PATH
    assign.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_preset_idempotent_second_call_creates_nothing(monkeypatch):
    _, created, _assign = _install_load_preset_mocks(monkeypatch)

    first = await RoleService.load_preset_sme(tenant_id=1, current_user_id=1)
    second = await RoleService.load_preset_sme(tenant_id=1, current_user_id=1)

    assert first == len(RoleService.PRESET_ROLES)
    assert second == 0
    assert {c["code"] for c in created} == {
        i["code"] for i in RoleService.PRESET_ROLES
    }


# ---------------- 预设显式权限（禁前缀扩权、禁 assign） ----------------


@pytest.mark.asyncio
async def test_station_preset_permissions_explicit_only(monkeypatch):
    defined = [
        "kuaizhizao:production-execution-terminal:read",
        "kuaizhizao:production-execution-terminal:execute",
        "kuaizhizao:production-execution-terminal:create",  # 未列举 → 不得授予
        "kuaizhizao:work-order:read",
        "kuaizhizao:work-order:create",  # 未列举 → 不得授予
        "kuaizhizao:production-execution-reporting:read",
        "kuaizhizao:production-execution-reporting:assign",  # 明令禁止
        "master-data:material:read",
        "master-data:factory:work-group:read",
        "master-data:factory:workstation:read",
        "master-data:factory:production-line:read",
        "system:user:display",
        *sorted(PermissionRegistryService.BASELINE_PERMISSION_CODES),
    ]
    perm_by_code = {c: MagicMock(id=i + 1, code=c) for i, c in enumerate(defined)}

    monkeypatch.setattr(
        PermissionRegistryService,
        "collect_definitions",
        AsyncMock(return_value={c: MagicMock(code=c) for c in defined}),
    )

    def _perm_filter(**kwargs):
        qs = _qs()
        wanted = set(kwargs.get("code__in") or [])
        qs.all = AsyncMock(
            return_value=[p for c, p in perm_by_code.items() if c in wanted]
        )
        return qs

    monkeypatch.setattr(role_service_module.Permission, "filter", _perm_filter)
    # RolePermission 未做 Tortoise 初始化时 FK _id 属性不可用，换成记录 kwargs 的工厂
    bulk_create = AsyncMock()

    def _fake_role_permission(**kwargs):
        return MagicMock(**kwargs)

    fake_role_permission_cls = MagicMock(side_effect=_fake_role_permission)
    fake_role_permission_cls.filter = MagicMock(side_effect=lambda **kw: _qs())
    fake_role_permission_cls.bulk_create = bulk_create
    monkeypatch.setattr(
        "core.models.role_permission.RolePermission", fake_role_permission_cls
    )
    monkeypatch.setattr(
        PermissionSyncService,
        "ensure_quality_inspection_execute_grants",
        AsyncMock(return_value=0),
    )

    role = _role(9, "station", code="STATION_TERMINAL")
    await RoleService._assign_preset_permissions(tenant_id=1, role=role)

    bulk_create.assert_awaited_once()
    granted_ids = {rp.permission_id for rp in bulk_create.await_args.args[0]}
    code_by_id = {p.id: p.code for p in perm_by_code.values()}
    granted_codes = {code_by_id[i] for i in granted_ids}
    assert granted_codes == {
        "kuaizhizao:production-execution-terminal:read",
        "kuaizhizao:production-execution-terminal:execute",
        "kuaizhizao:work-order:read",
        "kuaizhizao:production-execution-reporting:read",
        "master-data:material:read",
        "master-data:factory:work-group:read",
        "master-data:factory:workstation:read",
        "master-data:factory:production-line:read",
        "system:user:display",
        *PermissionRegistryService.BASELINE_PERMISSION_CODES,
    }


def _registered_permission_codes() -> set[str]:
    """全量已注册权限码：CORE + 所有应用 manifest.permissions + 引用 display 码。"""
    from core.services.authorization.reference_registry_service import (
        ReferenceRegistryService,
    )

    registered = {c.lower() for c in PermissionRegistryService.CORE_PERMISSION_CODES}
    apps_dir = PermissionRegistryService._get_apps_dir()
    for manifest_file in apps_dir.glob("*/manifest.json"):
        try:
            data = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        for raw in data.get("permissions") or []:
            code = str(raw).strip().lower()
            if code:
                registered.add(code)
    for code, _ in ReferenceRegistryService.collect_display_permission_codes():
        registered.add(str(code).strip().lower())
    return registered


def test_preset_explicit_permission_codes_all_registered():
    """预设显式集合中每个码都必须在注册定义中找到（防静默丢码回归）。"""
    registered = _registered_permission_codes()
    for role_code, explicit in RoleService.PRESET_ROLE_EXPLICIT_PERMISSION_CODES.items():
        missing = sorted(c for c in explicit if c not in registered)
        assert not missing, f"{role_code} 显式权限码未注册: {missing}"


# ---------------- 角色侧追加用户（bind 路径） ----------------


def _install_add_role_users_mocks(
    monkeypatch, *, role, users, bound_role_ids, role_types
):
    """bound_role_ids: {user_id: [role_id]}；role_types: {role_id: role_type}。"""
    monkeypatch.setattr(
        RoleService, "get_role_by_uuid", AsyncMock(return_value=role)
    )
    monkeypatch.setattr(
        RoleService, "_authorize_role_users_mutation", AsyncMock()
    )
    monkeypatch.setattr(
        RoleService,
        "list_role_users",
        AsyncMock(return_value={"items": [], "total": 0}),
    )
    monkeypatch.setattr(
        role_service_module.User,
        "filter",
        lambda **kw: _qs(all=AsyncMock(return_value=list(users))),
    )

    def _user_role_filter(**kwargs):
        qs = _qs()
        if "user_id__in" in kwargs:
            qs.values_list = AsyncMock(return_value=[])
        else:
            uid = kwargs.get("user_id")
            qs.values_list = AsyncMock(
                return_value=list(bound_role_ids.get(uid, []))
            )
        return qs

    monkeypatch.setattr(role_service_module.UserRole, "filter", _user_role_filter)
    bulk_create = AsyncMock()
    monkeypatch.setattr(role_service_module.UserRole, "bulk_create", bulk_create)
    monkeypatch.setattr(
        role_service_module.PermissionVersionService, "bump", AsyncMock()
    )

    def _role_filter(**kwargs):
        qs = _qs()
        ids = kwargs.get("id__in") or []
        qs.values_list = AsyncMock(
            return_value=[role_types[i] for i in ids if i in role_types]
        )
        return qs

    monkeypatch.setattr(role_service_module.Role, "filter", _role_filter)
    return bulk_create


@pytest.mark.asyncio
async def test_add_station_role_to_pure_station_user_passes(monkeypatch):
    role = _role(10, "station", code="STATION_TERMINAL")
    role.uuid = "role-uuid-station"
    user = MagicMock()
    user.id = 7
    bulk_create = _install_add_role_users_mocks(
        monkeypatch,
        role=role,
        users=[user],
        bound_role_ids={7: [30]},
        role_types={10: "station", 30: "station"},
    )

    result = await RoleService.add_role_users(
        tenant_id=1,
        role_uuid="role-uuid-station",
        user_uuids=["user-uuid-7"],
        current_user_id=1,
    )

    bulk_create.assert_awaited_once()
    assert result == {"items": [], "total": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize("bound_type", ["internal", "external"])
async def test_add_station_role_to_non_station_user_rejected(
    monkeypatch, bound_type
):
    role = _role(10, "station", code="STATION_TERMINAL")
    role.uuid = "role-uuid-station"
    user = MagicMock()
    user.id = 7
    bulk_create = _install_add_role_users_mocks(
        monkeypatch,
        role=role,
        users=[user],
        bound_role_ids={7: [30]},
        role_types={10: "station", 30: bound_type},
    )

    with pytest.raises(ValidationError):
        await RoleService.add_role_users(
            tenant_id=1,
            role_uuid="role-uuid-station",
            user_uuids=["user-uuid-7"],
            current_user_id=1,
        )
    bulk_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_internal_role_to_station_user_rejected(monkeypatch):
    role = _role(10, "internal", code="PRODUCTION_STAFF")
    role.uuid = "role-uuid-internal"
    user = MagicMock()
    user.id = 7
    bulk_create = _install_add_role_users_mocks(
        monkeypatch,
        role=role,
        users=[user],
        bound_role_ids={7: [30]},
        role_types={10: "internal", 30: "station"},
    )

    with pytest.raises(ValidationError):
        await RoleService.add_role_users(
            tenant_id=1,
            role_uuid="role-uuid-internal",
            user_uuids=["user-uuid-7"],
            current_user_id=1,
        )
    bulk_create.assert_not_awaited()


# ---------------- 用户侧改绑路径（create / update） ----------------


@pytest.mark.asyncio
async def test_create_user_rejects_station_plus_internal(monkeypatch):
    monkeypatch.setattr(
        user_service_module, "authorize_administrator_management", AsyncMock()
    )
    monkeypatch.setattr(
        user_service_module.User, "filter", lambda **kw: _qs()
    )
    roles = [_role(10, "station"), _role(20, "internal")]
    monkeypatch.setattr(
        user_service_module.Role,
        "filter",
        lambda **kw: _qs(all=AsyncMock(return_value=roles)),
    )

    data = UserCreate(
        username="station01",
        password="12345678",
        tenant_id=1,
        role_uuids=["r-station", "r-internal"],
    )
    with pytest.raises(ValidationError):
        await UserService.create_user(tenant_id=1, data=data, current_user_id=1)


@asynccontextmanager
async def _fake_in_transaction(*args, **kwargs):
    yield MagicMock()


@pytest.mark.asyncio
async def test_update_user_rejects_station_plus_external(monkeypatch):
    user = MagicMock()
    user.id = 7
    user.username = "station01"
    user.is_active = True
    user.department_id = None
    user.position_id = None
    user.save = AsyncMock()

    monkeypatch.setattr(
        user_service_module.User,
        "filter",
        lambda **kw: _qs(first=AsyncMock(return_value=user)),
    )
    monkeypatch.setattr(
        user_service_module, "authorize_administrator_management", AsyncMock()
    )
    monkeypatch.setattr(
        user_service_module, "in_transaction", _fake_in_transaction
    )
    monkeypatch.setattr(
        user_service_module.UserRole, "filter", lambda **kw: _qs()
    )
    bulk_create = AsyncMock()
    monkeypatch.setattr(user_service_module.UserRole, "bulk_create", bulk_create)

    roles = [_role(10, "station"), _role(20, "external")]
    monkeypatch.setattr(
        user_service_module.Role,
        "filter",
        lambda **kw: _qs(all=AsyncMock(return_value=roles)),
    )

    data = UserUpdate(role_uuids=["r-station", "r-external"])
    with pytest.raises(ValidationError):
        await UserService.update_user(
            tenant_id=1, user_uuid="user-uuid", data=data, current_user_id=1
        )
    bulk_create.assert_not_awaited()


# ---------------- 角色类型变更守卫 ----------------


@pytest.mark.asyncio
async def test_update_role_rejects_station_type_flip_when_bound(monkeypatch):
    role = _role(10, "station", code="STATION_TERMINAL")
    role.uuid = "role-uuid-station"
    role.is_system = False
    role.functional_domain = "production"
    role.external_partner_type = None
    role.save = AsyncMock()

    monkeypatch.setattr(
        role_service_module.Role,
        "filter",
        lambda **kw: _qs(first=AsyncMock(return_value=role)),
    )
    monkeypatch.setattr(
        role_service_module.UserRole,
        "filter",
        lambda **kw: _qs(exists=AsyncMock(return_value=True)),
    )

    with pytest.raises(ValidationError):
        await RoleService.update_role(
            tenant_id=1,
            role_uuid="role-uuid-station",
            data=RoleUpdate(role_type="internal"),
            current_user_id=1,
        )
    role.save.assert_not_awaited()
