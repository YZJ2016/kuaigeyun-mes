"""KU-AI spec 186 集成验收补测（全部 mock，不触真库）。

补齐 181～185 单测未覆盖的整体验证点：

- T2 权限矩阵：/operations 全部 15 个端点的权限码 + require_all=True
  逐一比对 spec 181 矩阵；并以「仅 display 无 entry」「仅 entry 无
  display」「display 无写码」等错位主体直调真实 FastAPI 依赖链
  （require_permission_codes → ensure_permission_codes →
  AccessControlService.check_access），验证 403/放行。
- AC#4：core stats/audit 仅查既有 entry 码（契约未改），
  trust:display / insights:display 单码无法触达。
- T2 预设角色：PRESET_ROLE_ADDITIVE_PERMISSION_CODES 只含 EMPLOYEE
  三个 display 码；_assign_preset_permissions 行为级验证 EMPLOYEE
  获得三 display 而自定义角色不自动扩权。
- T3/T4 chat 守卫接线：extra.agent_key 触发 guard_scene_agent_key，
  守卫失败先于 assemble；无 agent_key 的普通对话不触发守卫；
  非法 capability_mode 在守卫前 422。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from tortoise.queryset import Q

import apps.kuaiai.services.chat_service as cs
from apps.kuaiai.api.router import router
from core.api.deps.access import AuthContext
from core.services.authorization.role_service import RoleService
from infra.exceptions.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    NotFoundError,
    ValidationError,
)

TENANT = 7
USER_ID = 5


def _user(uid: int = USER_ID):
    return SimpleNamespace(id=uid, full_name="测试用户", username="tester")


# ============================================================ T2 权限矩阵

# spec 181 权限矩阵 + 183/184/185 写码细分（设计 §11、需求 §7）
EXPECTED_MATRIX = {
    ("GET", "/operations/hub"): {"kuaiai:entry:read", "kuaiai:hub:display"},
    ("GET", "/operations/agent-library"): {
        "kuaiai:entry:read",
        "kuaiai:library:display",
    },
    ("PUT", "/operations/agent-library/instances/{instance_key}"): {
        "kuaiai:entry:read",
        "kuaiai:library:display",
        "kuaiai:library:manage",
    },
    ("POST", "/operations/agent-library/instances"): {
        "kuaiai:entry:read",
        "kuaiai:library:display",
        "kuaiai:library:manage",
        "kuaiai:agent:read",
        "kuaiai:agent:create",
    },
    ("GET", "/operations/pulse"): {
        "kuaiai:entry:read",
        "kuaiai:pulse:display",
    },
    ("GET", "/operations/settings"): {
        "kuaiai:entry:read",
        "kuaiai:settings:display",
    },
    ("PUT", "/operations/settings"): {
        "kuaiai:entry:read",
        "kuaiai:settings:display",
        "kuaiai:settings:update",
    },
    ("GET", "/operations/trust"): {
        "kuaiai:entry:read",
        "kuaiai:trust:display",
    },
    ("GET", "/operations/corpus"): {
        "kuaiai:entry:read",
        "kuaiai:corpus:display",
    },
    ("GET", "/operations/corpus/knowledge-options"): {
        "kuaiai:entry:read",
        "kuaiai:corpus:display",
    },
    ("POST", "/operations/corpus/faqs"): {
        "kuaiai:entry:read",
        "kuaiai:corpus:display",
        "kuaiai:corpus:create",
    },
    ("POST", "/operations/corpus/seed-faqs"): {
        "kuaiai:entry:read",
        "kuaiai:corpus:display",
        "kuaiai:corpus:create",
    },
    ("POST", "/operations/corpus/batch-index"): {
        "kuaiai:entry:read",
        "kuaiai:corpus:display",
        "kuaiai:corpus:update",
    },
    ("POST", "/operations/corpus/batch-delete"): {
        "kuaiai:entry:read",
        "kuaiai:corpus:display",
        "kuaiai:corpus:delete",
    },
    ("GET", "/operations/corpus/export.jsonl"): {
        "kuaiai:entry:read",
        "kuaiai:corpus:display",
        "kuaiai:corpus:export",
    },
}


def _dep_closure(dep_fn):
    """取 require_permission_codes 依赖闭包里的 codes / require_all。"""
    closure = getattr(dep_fn, "__closure__", None)
    out = {"codes": set(), "require_all": None}
    if closure is None:
        return out
    for name, cell in zip(dep_fn.__code__.co_freevars, closure):
        if name == "codes":
            out["codes"] = set(cell.cell_contents or [])
        elif name == "require_all":
            out["require_all"] = cell.cell_contents
    return out


def _route_table():
    """{(method, path): [dep_fn,...]} — 只取权限闭包依赖。"""
    table = {}
    for r in router.routes:
        if not isinstance(r, APIRoute):
            continue
        dep_fns = []
        for dep in r.dependencies or []:
            fn = getattr(dep, "dependency", None)
            if getattr(fn, "__closure__", None) is None:
                continue
            info = _dep_closure(fn)
            if info["codes"]:
                dep_fns.append((fn, info))
        for method in r.methods:
            table[(method, r.path)] = dep_fns
    return table


class TestOperationsPermissionMatrix:
    def test_all_operations_endpoints_match_matrix(self):
        table = _route_table()
        for key, expected_codes in EXPECTED_MATRIX.items():
            assert key in table, f"路由未注册: {key[0]} {key[1]}"
            dep_fns = table[key]
            assert len(dep_fns) == 1, f"{key} 权限依赖数异常: {len(dep_fns)}"
            _, info = dep_fns[0]
            assert info["codes"] == expected_codes, (
                f"{key} 权限码不符: {info['codes']} != {expected_codes}"
            )
            assert info["require_all"] is True, (
                f"{key} 未 require_all（任一缺失应 403）"
            )

    def test_every_operations_endpoint_requires_entry_read(self):
        for (method, path), expected in EXPECTED_MATRIX.items():
            assert "kuaiai:entry:read" in expected


# ============================================================ T2/AC4 依赖直调


def _request(method: str = "GET", path: str = "/api/v1/apps/kuaiai/operations/trust"):
    return SimpleNamespace(
        method=method,
        url=SimpleNamespace(path=path),
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(open_api_grants=None, open_api_app_id=False),
    )


def _auth():
    return AuthContext(
        user_id=USER_ID,
        tenant_id=TENANT,
        is_infra_admin=False,
        is_tenant_admin=False,
        request_id="req-1",
    )


def _perm_backend(user_codes: set):
    """真实 check_access 路径：只 mock 权限来源两侧，require_all 语义用真实现。"""

    async def _has_all(*, user_id, tenant_id, permission_codes):
        return set(permission_codes) <= set(user_codes)

    return [
        patch(
            "core.services.authorization.user_permission_service"
            ".UserPermissionService.is_admin_bypass_flags",
            AsyncMock(return_value=False),
        ),
        patch(
            "core.services.authorization.user_permission_service"
            ".UserPermissionService.has_all_permissions",
            AsyncMock(side_effect=_has_all),
        ),
    ]


@pytest.mark.asyncio
class TestDependencyEnforcement:
    async def _invoke(self, method, path, user_codes):
        table = _route_table()
        dep_fns = table[(method, path)]
        fn, _ = dep_fns[0]
        patches = _perm_backend(set(user_codes))
        for p in patches:
            p.start()
        try:
            return await fn(
                _request(method=method, path=f"/api/v1/apps/kuaiai{path}"),
                _auth(),
                TENANT,
            )
        finally:
            for p in patches:
                p.stop()

    async def test_display_only_without_entry_denied_all_reads(self):
        """仅 display 无 entry:read → 全部读端点 403（含 trust）。"""
        display_codes = {
            ("GET", "/operations/hub"): "kuaiai:hub:display",
            ("GET", "/operations/agent-library"): "kuaiai:library:display",
            ("GET", "/operations/pulse"): "kuaiai:pulse:display",
            ("GET", "/operations/corpus"): "kuaiai:corpus:display",
            ("GET", "/operations/trust"): "kuaiai:trust:display",
            ("GET", "/operations/settings"): "kuaiai:settings:display",
        }
        for (method, path), code in display_codes.items():
            with pytest.raises(HTTPException) as exc:
                await self._invoke(method, path, {code})
            assert exc.value.status_code == 403, f"{path} 未拒绝"

    async def test_entry_only_without_display_denied(self):
        """仅 entry:read → 各页读端点 403。"""
        for method, path in [
            ("GET", "/operations/hub"),
            ("GET", "/operations/trust"),
            ("GET", "/operations/settings"),
        ]:
            with pytest.raises(HTTPException) as exc:
                await self._invoke(method, path, {"kuaiai:entry:read"})
            assert exc.value.status_code == 403

    async def test_entry_plus_display_allowed(self):
        for method, path, extra in [
            ("GET", "/operations/hub", "kuaiai:hub:display"),
            ("GET", "/operations/trust", "kuaiai:trust:display"),
            ("GET", "/operations/settings", "kuaiai:settings:display"),
            ("GET", "/operations/corpus", "kuaiai:corpus:display"),
        ]:
            auth = await self._invoke(
                method, path, {"kuaiai:entry:read", extra}
            )
            assert auth.user_id == USER_ID

    async def test_write_endpoint_needs_write_code(self):
        """entry+display 但无写码 → 写端点仍 403。"""
        with pytest.raises(HTTPException) as exc:
            await self._invoke(
                "PUT",
                "/operations/settings",
                {"kuaiai:entry:read", "kuaiai:settings:display"},
            )
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await self._invoke(
                "POST",
                "/operations/corpus/faqs",
                {"kuaiai:entry:read", "kuaiai:corpus:display"},
            )
        assert exc.value.status_code == 403

    async def test_write_endpoint_full_codes_allowed(self):
        auth = await self._invoke(
            "PUT",
            "/operations/settings",
            {
                "kuaiai:entry:read",
                "kuaiai:settings:display",
                "kuaiai:settings:update",
            },
        )
        assert auth.user_id == USER_ID

    async def test_clone_endpoint_needs_all_five_codes(self):
        """克隆端点缺 agent:create → 403；五码齐 → 放行。"""
        base = {
            "kuaiai:entry:read",
            "kuaiai:library:display",
            "kuaiai:library:manage",
            "kuaiai:agent:read",
        }
        with pytest.raises(HTTPException) as exc:
            await self._invoke(
                "POST", "/operations/agent-library/instances", base
            )
        assert exc.value.status_code == 403
        auth = await self._invoke(
            "POST",
            "/operations/agent-library/instances",
            base | {"kuaiai:agent:create"},
        )
        assert auth.user_id == USER_ID


class TestCoreContractUnchanged:
    """AC#4：core stats/audit 仍只查既有 entry 码；chat 仍查 act 码。"""

    def test_stats_and_audit_require_only_entry(self):
        from core.api.ai import router as ai_router

        codes_map = {}
        for r in ai_router.router.routes:
            if not isinstance(r, APIRoute):
                continue
            codes = set()
            for dep in r.dependencies or []:
                fn = getattr(dep, "dependency", None)
                # require_ai_capability 的 _guard：权限码绑在默认值
                # __=Depends(require_permission_codes(permission)) 的子依赖闭包里
                for default in getattr(fn, "__defaults__", None) or []:
                    sub_fn = getattr(default, "dependency", None)
                    info = _dep_closure(sub_fn) if sub_fn else None
                    if info and info["codes"]:
                        codes.update(info["codes"])
            codes_map[r.path] = codes

        assert codes_map.get("/ai/stats/overview") == {"kuaiai:entry:read"}
        assert codes_map.get("/ai/audit/logs") == {"kuaiai:entry:read"}
        assert codes_map.get("/ai/chat/completions") == {
            "kuaiai:act:execute"
        }


# ============================================================ T2 预设角色


def _perm_rows(codes):
    return [
        SimpleNamespace(id=i + 1, code=c, tenant_id=TENANT, deleted_at=None)
        for i, c in enumerate(sorted(codes))
    ]


class _PermQS:
    """Permission.filter 链 mock：code__in 与 endswith Q 语义近似。"""

    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, *args, **kwargs):
        rows = self._rows
        codes = kwargs.get("code__in")
        if codes is not None:
            allowed = set(codes)
            rows = [r for r in rows if r.code in allowed]
        if any(isinstance(a, Q) for a in args):
            # 本文件内唯一 Q 用法：read/view 兜底分支
            rows = [
                r
                for r in rows
                if r.code.endswith(":read") or r.code.endswith(":view")
            ]
        return _PermQS(rows)

    async def all(self):
        return list(self._rows)


class _RolePermQS:
    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, *args, **kwargs):
        return self

    async def all(self):
        return list(self._rows)


REGISTERED_CODES = {
    "kuaiai:entry:read",
    "kuaiai:hub:display",
    "kuaiai:library:display",
    "kuaiai:pulse:display",
    "kuaiai:corpus:display",
    "kuaiai:trust:display",
    "kuaiai:insights:display",
    "kuaiai:settings:display",
    "kuaiai:agent:read",
    "kuaiai:act:execute",
    "kuaiai:corpus:create",
    "system:user:read",
}


def _definitions(codes):
    return {c: SimpleNamespace(code=c) for c in codes}


@pytest.mark.asyncio
class TestPresetRoleAdditive:
    async def test_additive_map_exactly_employee_three_displays(self):
        assert set(
            RoleService.PRESET_ROLE_ADDITIVE_PERMISSION_CODES.keys()
        ) == {"EMPLOYEE"}
        assert RoleService.PRESET_ROLE_ADDITIVE_PERMISSION_CODES[
            "EMPLOYEE"
        ] == frozenset(
            {
                "kuaiai:hub:display",
                "kuaiai:library:display",
                "kuaiai:pulse:display",
            }
        )

    async def _assign(self, role_code):
        """真实 _assign_preset_permissions：mock 仅存储层。

        RolePermission 以 MagicMock 替身注入：Tortoise ``__init__`` 会静默
        丢弃 ``role_id``/``permission_id`` kwargs（非字段名），构造器侧
        用 SimpleNamespace 保留传入键便于断言。
        """
        perms = _perm_rows(REGISTERED_CODES)
        role = SimpleNamespace(id=99, code=role_code)
        created = []

        async def _bulk(objs, ignore_conflicts=False):
            created.extend(objs)

        def _filter(*args, **kwargs):
            return _PermQS(perms).filter(*args, **kwargs)

        fake_rp = MagicMock(
            side_effect=lambda **kw: SimpleNamespace(**kw)
        )
        fake_rp.filter = MagicMock(return_value=_RolePermQS([]))
        fake_rp.bulk_create = AsyncMock(side_effect=_bulk)

        with patch(
            "core.services.authorization.permission_registry_service"
            ".PermissionRegistryService.collect_definitions",
            AsyncMock(return_value=_definitions(REGISTERED_CODES)),
        ), patch(
            "core.models.permission.Permission.filter",
            MagicMock(side_effect=_filter),
        ), patch(
            "core.models.role_permission.RolePermission",
            fake_rp,
        ), patch(
            "core.services.authorization.permission_sync_service"
            ".PermissionSyncService.ensure_quality_inspection_execute_grants",
            AsyncMock(),
        ):
            await RoleService._assign_preset_permissions(TENANT, role)

        return {
            next(r.code for r in perms if r.id == p.permission_id)
            for p in created
        }

    async def test_employee_gets_three_displays_not_governance(self):
        codes = await self._assign("EMPLOYEE")
        assert {
            "kuaiai:hub:display",
            "kuaiai:library:display",
            "kuaiai:pulse:display",
        } <= codes
        # 治理层 display 不自动授予
        for denied in (
            "kuaiai:corpus:display",
            "kuaiai:trust:display",
            "kuaiai:insights:display",
            "kuaiai:settings:display",
            "kuaiai:corpus:create",
            "kuaiai:act:execute",
        ):
            assert denied not in codes
        # :read 兜底分支仍生效
        assert "kuaiai:entry:read" in codes

    async def test_custom_role_no_additive_expansion(self):
        """非预设 code：additive 不生效，无任何 display 码自动授予。"""
        codes = await self._assign("CUSTOM_KNOWLEDGE_OPS")
        assert not any(c.endswith(":display") for c in codes)
        assert "kuaiai:entry:read" in codes
        assert "kuaiai:hub:display" not in codes


# ============================================================ T3/T4 chat 守卫接线


class _FakeChat:
    def __init__(self, model_name="fb-chat"):
        self.model_name = model_name

    def bind(self, **kwargs):
        return self

    async def ainvoke(self, messages):
        return SimpleNamespace(
            content="路径A回答",
            id="chatcmpl-fake",
            usage_metadata={
                "input_tokens": 3,
                "output_tokens": 2,
                "total_tokens": 5,
            },
            response_metadata={"finish_reason": "stop"},
        )


def _runtime_config(**over):
    base = dict(
        chat_api_key="fake-key",
        chat_base_url="https://llm.example.invalid",
        chat_model="fb-chat",
        custom_system_prompt=None,
        stream_enabled=True,
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
class TestChatSceneGuardWiring:
    """create_chat_completion → extra.agent_key → guard_scene_agent_key。"""

    def _base_patches(self, guard_side_effect=None):
        """返回 (patches, guard_mock)：guard 替身可在断言期持有。"""
        guard = AsyncMock(side_effect=guard_side_effect)
        patches = [
            patch.object(
                cs, "_resolve_catalog_source", AsyncMock(return_value=None)
            ),
            patch(
                "apps.kuaiai.services.agent_scene_service"
                ".guard_scene_agent_key",
                guard,
            ),
            patch.object(
                cs, "assemble", AsyncMock(return_value=None)
            ),
            patch.object(
                cs,
                "build_chat_model",
                AsyncMock(return_value=_FakeChat()),
            ),
            patch.object(
                cs.AiRuntimeConfig,
                "load",
                AsyncMock(return_value=_runtime_config()),
            ),
        ]
        return patches, guard

    async def test_agent_key_invokes_guard_then_plain_path(self):
        patches, guard = self._base_patches()
        for p in patches:
            p.start()
        try:
            result = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "查询缺料库存"}],
                user=_user(),
                context={
                    "agent_id": "11",
                    "extra": {
                        "agent_key": "inventory-insight",
                        "capability_mode": "query",
                    },
                },
            )
            guard.assert_awaited_once()
            args = guard.await_args.args
            assert args[0] == TENANT
            assert args[1] == "inventory-insight"
            assert args[2] == 11
            assert result["object"] == "chat.completion"
        finally:
            for p in patches:
                p.stop()

    async def test_guard_rejection_blocks_before_assemble(self):
        patches, _ = self._base_patches(
            guard_side_effect=AuthorizationError("无该 Agent 档案使用权")
        )
        for p in patches:
            p.start()
        try:
            with pytest.raises(AuthorizationError):
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    user=_user(),
                    context={
                        "agent_id": "11",
                        "extra": {"agent_key": "forged-key"},
                    },
                )
            cs.assemble.assert_not_awaited()
            cs.build_chat_model.assert_not_awaited()
        finally:
            for p in patches:
                p.stop()

    async def test_plain_chat_does_not_call_guard(self):
        """无 agent_key 的普通对话：守卫不触发，模板开关不全局禁用。"""
        patches, guard = self._base_patches()
        for p in patches:
            p.start()
        try:
            result = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "hi"}],
                user=_user(),
                context=None,
            )
            guard.assert_not_awaited()
            assert result["object"] == "chat.completion"
        finally:
            for p in patches:
                p.stop()

    async def test_invalid_capability_mode_rejected_before_guard(self):
        patches, guard = self._base_patches()
        for p in patches:
            p.start()
        try:
            with pytest.raises(ValidationError):
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    user=_user(),
                    context={
                        "agent_id": "11",
                        "extra": {
                            "agent_key": "inventory-insight",
                            "capability_mode": "evil",
                        },
                    },
                )
            guard.assert_not_awaited()
            cs.assemble.assert_not_awaited()
        finally:
            for p in patches:
                p.stop()

    async def test_forged_agent_key_404_via_real_guard(self):
        """真实守卫：伪造 agent_key（场景不存在）→ 404，先于 assemble。"""
        from apps.kuaiai.models.agent_scene import KuaiaiAgentScene

        with patch.object(
            KuaiaiAgentScene, "get_or_none", AsyncMock(return_value=None)
        ), patch.object(
            cs, "assemble", AsyncMock()
        ) as mock_assemble, patch.object(
            cs, "_resolve_catalog_source", AsyncMock(return_value=None)
        ):
            with pytest.raises(Exception):
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    user=_user(),
                    context={
                        "agent_id": "11",
                        "extra": {"agent_key": "no-such-scene"},
                    },
                )
            mock_assemble.assert_not_awaited()


@pytest.mark.asyncio
class TestChatSceneGuardFlattenedContext:
    """真实 HTTP 形态回归（review 修复，spec 181 T9）。

    ``POST /core/ai/chat/completions`` 的 ``normalized_context()`` 经
    ``AiBusinessContext.to_broker_dict`` 把 ``extra.*`` 摊平为顶层键，
    生产请求里不存在 ``context["extra"]``；守卫必须对摊平形态同样生效。
    """

    def _flattened(self, agent_id="11", **extra):
        from core.ai.schemas.chat import ChatCompletionRequest
        from core.ai.schemas.context import AiBusinessContext

        return ChatCompletionRequest(
            messages=[{"role": "user", "content": "hi"}],
            context=AiBusinessContext(agent_id=agent_id, extra=extra),
        ).normalized_context()

    def _scene(self, **kw):
        base = dict(
            tenant_id=TENANT,
            instance_key="inventory-insight",
            template_key="inventory-insight",
            agent_profile_id=11,
            enabled=True,
        )
        base.update(kw)
        return SimpleNamespace(**base)

    def _profile(self, **kw):
        base = dict(id=11, tenant_id=TENANT, status="启用", deleted_at=None)
        base.update(kw)
        return SimpleNamespace(**base)

    def _guard_patches(self, *, scene, profile=None, grant=True, chat_ready=True):
        """真实 guard_scene_agent_key：只替换其存储/权限/就绪依赖。"""
        from apps.kuaiai.models.agent_scene import KuaiaiAgentScene
        from apps.kuaiai.services import agent_scene_service as scene_svc

        return [
            patch.object(
                KuaiaiAgentScene,
                "get_or_none",
                AsyncMock(return_value=scene),
            ),
            patch.object(
                scene_svc,
                "agent_switches",
                AsyncMock(return_value={"inventory-insight": True}),
            ),
            patch.object(
                scene_svc.KuaiaiAgentProfile,
                "get_or_none",
                AsyncMock(return_value=profile),
            ),
            patch.object(
                scene_svc.grant_service,
                "check_use_grant",
                AsyncMock(return_value=grant),
            ),
            patch.object(
                scene_svc,
                "is_chat_ready",
                AsyncMock(return_value=chat_ready),
            ),
            patch.object(cs, "assemble", AsyncMock(return_value=None)),
            patch.object(
                cs, "_resolve_catalog_source", AsyncMock(return_value=None)
            ),
            patch.object(
                cs,
                "build_chat_model",
                AsyncMock(return_value=_FakeChat()),
            ),
            patch.object(
                cs.AiRuntimeConfig,
                "load",
                AsyncMock(return_value=_runtime_config()),
            ),
        ]

    async def test_flattened_valid_key_passes_guard_then_plain_path(self):
        context = self._flattened(
            agent_key="inventory-insight", capability_mode="query"
        )
        assert "extra" not in context  # 生产形态：无嵌套 extra
        patches = self._guard_patches(
            scene=self._scene(), profile=self._profile()
        )
        for p in patches:
            p.start()
        try:
            result = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "hi"}],
                user=_user(),
                context=context,
            )
            cs.assemble.assert_awaited_once()
            assert result["object"] == "chat.completion"
        finally:
            for p in patches:
                p.stop()

    async def test_flattened_forged_key_rejected(self):
        context = self._flattened(agent_key="no-such-scene")
        patches = self._guard_patches(scene=None)
        for p in patches:
            p.start()
        try:
            with pytest.raises(NotFoundError):
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    user=_user(),
                    context=context,
                )
            cs.assemble.assert_not_awaited()
        finally:
            for p in patches:
                p.stop()

    async def test_flattened_disabled_instance_rejected(self):
        context = self._flattened(
            agent_key="inventory-insight", capability_mode="query"
        )
        patches = self._guard_patches(
            scene=self._scene(enabled=False), profile=self._profile()
        )
        for p in patches:
            p.start()
        try:
            with pytest.raises(BusinessLogicError):
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    user=_user(),
                    context=context,
                )
            cs.assemble.assert_not_awaited()
        finally:
            for p in patches:
                p.stop()

    async def test_flattened_agent_id_mismatch_rejected(self):
        context = self._flattened(agent_key="inventory-insight")
        patches = self._guard_patches(
            scene=self._scene(agent_profile_id=99),
            profile=self._profile(),
        )
        for p in patches:
            p.start()
        try:
            with pytest.raises(BusinessLogicError):
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    user=_user(),
                    context=context,
                )
            cs.assemble.assert_not_awaited()
        finally:
            for p in patches:
                p.stop()

    async def test_flattened_invalid_capability_mode_without_key(self):
        """capability_mode 闭集不再以 agent_key 为前提：非法值直接 400。"""
        context = self._flattened(capability_mode="evil")
        patches = self._guard_patches(scene=None)
        for p in patches:
            p.start()
        try:
            with pytest.raises(ValidationError):
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    user=_user(),
                    context=context,
                )
            cs.assemble.assert_not_awaited()
        finally:
            for p in patches:
                p.stop()

    async def test_flattened_agent_marker_still_triggers_agent_path(self):
        """capability_mode=agent 是 spec 135 agent 路径合法标记，不误拒。"""
        context = self._flattened(agent_id=None, capability_mode="agent")
        patches = self._guard_patches(scene=None)
        for p in patches:
            p.start()
        try:
            result = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "hi"}],
                user=_user(),
                context=context,
            )
            cs.assemble.assert_awaited_once()
            assert cs.assemble.await_args.kwargs["agent_path"] is True
            assert result["object"] == "chat.completion"
        finally:
            for p in patches:
                p.stop()
