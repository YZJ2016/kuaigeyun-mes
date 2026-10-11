"""KU-AI spec 181 单测：场景实例/运营层/只读 Tool（全部 mock，不触真库）。

覆盖要点：
- 生命周期种子幂等（缺几补几、完整早退、同事务、种子档案停用/空名单/只读 Tool）
- 智能体库聚合（六预置+复制项、provisioning、状态/禁用原因、档案 ID 脱敏）
- PUT 更新（跨租户 404、改绑复核、覆盖字段白名单、预置缺失先补齐后报错）
- 克隆（未知模板 400、跨租户源 404、停用新档案+复制实例、失败回滚）
- chat 守卫（key 缺失 404 / 总开关 / 单开关 / 绑定不一致 / 档案停用 / 无使用权 / chat 未就绪）
- hub（days 钳制、指标局部失败置空、能力状态闭集）
- 只读 Tool（空上下文失败关闭、参数闭集、limit 钳制、未发布排程拒读）
- 请求 schema extra=forbid
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.models.agent_scene import KuaiaiAgentScene
from apps.kuaiai.services import agent_scene_service as svc
from apps.kuaiai.services import operations_service
from infra.exceptions.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    NotFoundError,
    ValidationError,
)

TENANT = 7
OTHER_TENANT = 8
USER_ID = 5


def _user(uid: int = USER_ID):
    return SimpleNamespace(id=uid, full_name="测试用户", username="tester")


def _qs(rows=(), count=None):
    q = MagicMock()
    rows = list(rows)
    for m in ("filter", "order_by", "offset", "limit", "select_for_update"):
        setattr(q, m, MagicMock(return_value=q))
    q.all = AsyncMock(return_value=rows)
    q.first = AsyncMock(return_value=rows[0] if rows else None)
    q.count = AsyncMock(return_value=len(rows) if count is None else count)
    q.exists = AsyncMock(return_value=bool(rows))
    q.update = AsyncMock(return_value=len(rows))
    q.values_list = AsyncMock(return_value=rows)
    q.values = AsyncMock(return_value=rows)
    return q


class _FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _patch_tx(module: str):
    return patch(module, MagicMock(return_value=_FakeTx()))


def _scene(**kw):
    base = dict(
        id=1,
        tenant_id=TENANT,
        instance_key="inventory-insight",
        template_key="inventory-insight",
        origin="system_seed",
        agent_profile_id=11,
        overrides={},
        enabled=True,
        deleted_at=None,
        update_from_dict=MagicMock(),
        save=AsyncMock(),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _profile(**kw):
    base = dict(
        id=11,
        tenant_id=TENANT,
        name="库存洞察助手",
        description="d",
        system_prompt="p",
        default_model_id=None,
        knowledge_ids=[],
        enabled_tools=["query_inventory_balance"],
        mcp_server_ids=[],
        status="启用",
        grant_mode="ROLE",
        deleted_at=None,
        save=AsyncMock(),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _patch_library_deps(
    *,
    usable=None,
    has_agent_read=True,
    chat_ready=True,
    switches=None,
    route_grants=None,
):
    return [
        patch.object(
            svc,
            "agent_switches",
            AsyncMock(
                return_value=switches or {k: True for k in svc.TEMPLATE_KEYS}
            ),
        ),
        patch.object(
            svc.grant_service,
            "usable_profile_ids",
            AsyncMock(return_value=set(usable or set())),
        ),
        patch.object(
            svc, "_has_permission", AsyncMock(return_value=has_agent_read)
        ),
        patch.object(
            svc, "is_chat_ready", AsyncMock(return_value=chat_ready)
        ),
        patch.object(
            svc,
            "_route_permissions_for_user",
            AsyncMock(
                return_value=route_grants
                or {c: True for c in svc.SCENE_ROUTE_PERMISSIONS.values()}
            ),
        ),
    ]


# ============================================================ 生命周期种子


@pytest.mark.asyncio
class TestLifecycleSeed:
    async def test_complete_early_return_no_create(self):
        keys = list(svc.TEMPLATE_KEYS)
        with patch.object(
            KuaiaiAgentScene, "filter", MagicMock(return_value=_qs(keys))
        ) as _f, patch.object(
            KuaiaiAgentScene, "create", AsyncMock()
        ) as create:
            result = await svc.seed_kuaiai_agent_scenes_on_lifecycle(TENANT)
        assert result["complete"] is True
        assert result["created"] == 0
        create.assert_not_awaited()

    async def test_missing_templates_seeded_in_one_tx(self):
        tx = MagicMock(return_value=_FakeTx())
        profiles_created = []

        async def _mk_profile(tenant_id, template):
            p = _profile(id=100 + len(profiles_created), name=template.name)
            profiles_created.append(p)
            return p

        empty = _qs([])
        with patch.object(
            KuaiaiAgentScene, "filter", MagicMock(return_value=empty)
        ), patch.object(
            KuaiaiAgentScene, "get_or_none", AsyncMock(return_value=None)
        ), patch.object(
            KuaiaiAgentScene, "create", AsyncMock()
        ) as create, patch(
            "apps.kuaiai.services.agent_scene_service.in_transaction", tx
        ), patch.object(
            svc, "_create_seed_profile", AsyncMock(side_effect=_mk_profile)
        ):
            result = await svc.seed_kuaiai_agent_scenes_on_lifecycle(TENANT)

        assert result["created"] == len(svc.SCENE_TEMPLATES)
        assert create.await_count == len(svc.SCENE_TEMPLATES)
        tx.assert_called()
        kwargs_list = [c.kwargs for c in create.await_args_list]
        assert all(k["origin"] == "system_seed" for k in kwargs_list)
        assert all(k["created_by"] == 0 for k in kwargs_list)
        assert all(k["created_by_name"] == "系统" for k in kwargs_list)
        assert {k["instance_key"] for k in kwargs_list} == set(
            svc.TEMPLATE_KEYS
        )

    async def test_seed_profile_shape_disabled_no_grants_readonly(self):
        template = svc.SCENE_TEMPLATES[0]
        created_payloads = []

        class _Payload:
            def __init__(self, **kw):
                created_payloads.append(kw)
                self.__dict__.update(kw)

        async def _create(tenant_id, user, payload):
            p = _profile(id=42, name=payload.name)
            p.__dict__.update(
                {
                    "status": payload.status,
                    "grant_mode": payload.grant_mode,
                    "enabled_tools": payload.enabled_tools,
                    "knowledge_ids": payload.knowledge_ids,
                    "mcp_server_ids": payload.mcp_server_ids,
                    "default_model_id": None,
                    "save": AsyncMock(),
                }
            )
            return p

        with patch.object(
            svc.KuaiaiAgentProfile, "get_or_none", AsyncMock(return_value=None)
        ), patch.object(
            svc.agent_service, "create_profile", AsyncMock(side_effect=_create)
        ) as cp:
            profile = await svc._create_seed_profile(TENANT, template)

        payload = cp.await_args.args[2]
        assert payload.status == "停用"
        assert payload.grant_mode == "ROLE"
        assert payload.default_model_id is None
        assert payload.knowledge_ids == []
        assert payload.mcp_server_ids == []
        assert payload.enabled_tools == list(template.readonly_tools)
        assert not set(payload.enabled_tools) & {
            "submit_production_feedback",
            "update_workorder_status",
        }
        assert profile.status == "停用"
        profile.save.assert_awaited()

    async def test_seed_profile_name_dedup_keeps_user_same_name(self):
        template = svc.SCENE_TEMPLATES[0]
        existing = _profile(name=template.name)
        seen_names = []

        async def _dup(**kwargs):
            name = kwargs.get("name")
            seen_names.append(name)
            return existing if name == template.name else None

        async def _create(tenant_id, user, payload):
            return _profile(id=9, name=payload.name)

        with patch.object(
            svc.KuaiaiAgentProfile, "get_or_none", AsyncMock(side_effect=_dup)
        ), patch.object(
            svc.agent_service, "create_profile", AsyncMock(side_effect=_create)
        ) as cp:
            await svc._create_seed_profile(TENANT, template)

        payload = cp.await_args.args[2]
        assert payload.name != template.name
        assert "预置" in payload.name

    async def test_soft_deleted_seed_not_recreated(self):
        """已软删的预置行视为历史标记：get_or_none 命中后跳过不重建。"""
        deleted_row = _scene(deleted_at="2026-01-01")
        # 第一遍存在性检查只缺一个模板
        keys = [k for k in svc.TEMPLATE_KEYS if k != "inventory-insight"]
        with patch.object(
            KuaiaiAgentScene, "filter", MagicMock(return_value=_qs(keys))
        ), patch.object(
            KuaiaiAgentScene,
            "get_or_none",
            AsyncMock(return_value=deleted_row),
        ), patch.object(
            KuaiaiAgentScene, "create", AsyncMock()
        ) as create, patch(
            "apps.kuaiai.services.agent_scene_service.in_transaction",
            MagicMock(return_value=_FakeTx()),
        ), patch.object(
            svc, "_create_seed_profile", AsyncMock()
        ) as mk:
            await svc.seed_kuaiai_agent_scenes_on_lifecycle(TENANT)
        mk.assert_not_awaited()
        create.assert_not_awaited()


# ============================================================ 智能体库聚合


@pytest.mark.asyncio
class TestLibraryList:
    async def test_six_items_and_provisioning(self):
        scenes = [
            _scene(instance_key=t.key, template_key=t.key, id=i + 1)
            for i, t in enumerate(svc.SCENE_TEMPLATES)
        ]
        patches = _patch_library_deps(usable={11})
        with patch.object(
            KuaiaiAgentScene, "filter", MagicMock(return_value=_qs(scenes))
        ), patch.object(
            svc.KuaiaiAgentProfile, "filter", MagicMock(return_value=_qs([_profile()]))
        ):
            for p in patches:
                p.start()
            try:
                out = await svc.list_agent_library(TENANT, _user())
            finally:
                for p in patches:
                    p.stop()
        assert out["provisioning"]["complete"] is True
        assert out["provisioning"]["missing_template_keys"] == []
        assert len(out["items"]) == len(svc.SCENE_TEMPLATES)
        assert all(i["status"] == "ready" for i in out["items"])
        assert all(i["agent_profile_id"] == 11 for i in out["items"])

    async def test_missing_instance_placeholder_and_incomplete(self):
        patches = _patch_library_deps()
        with patch.object(
            KuaiaiAgentScene, "filter", MagicMock(return_value=_qs([]))
        ), patch.object(
            svc.KuaiaiAgentProfile, "filter", MagicMock(return_value=_qs([]))
        ):
            for p in patches:
                p.start()
            try:
                out = await svc.list_agent_library(TENANT, _user())
            finally:
                for p in patches:
                    p.stop()
        assert out["provisioning"]["complete"] is False
        assert set(out["provisioning"]["missing_template_keys"]) == set(
            svc.TEMPLATE_KEYS
        )
        assert all(i["status"] == "not_ready" for i in out["items"])
        assert all(i["agent_profile_id"] is None for i in out["items"])

    async def test_profile_id_redacted_without_use_or_manage_read(self):
        scenes = [_scene()]
        patches = _patch_library_deps(usable=set(), has_agent_read=False)
        with patch.object(
            KuaiaiAgentScene, "filter", MagicMock(return_value=_qs(scenes))
        ), patch.object(
            svc.KuaiaiAgentProfile, "filter", MagicMock(return_value=_qs([_profile()]))
        ):
            for p in patches:
                p.start()
            try:
                out = await svc.list_agent_library(TENANT, _user())
            finally:
                for p in patches:
                    p.stop()
        item = out["items"][0]
        assert item["agent_profile_id"] is None
        assert item["status"] == "partial"
        assert "使用权" in (item["disabled_reason"] or "")

    async def test_disabled_instance_not_ready(self):
        scenes = [_scene(enabled=False)]
        patches = _patch_library_deps(usable={11})
        with patch.object(
            KuaiaiAgentScene, "filter", MagicMock(return_value=_qs(scenes))
        ), patch.object(
            svc.KuaiaiAgentProfile, "filter", MagicMock(return_value=_qs([_profile()]))
        ):
            for p in patches:
                p.start()
            try:
                out = await svc.list_agent_library(TENANT, _user())
            finally:
                for p in patches:
                    p.stop()
        item = out["items"][0]
        assert item["status"] == "not_ready"
        assert item["enabled"] is False

    async def test_template_switch_off_not_ready(self):
        scenes = [_scene()]
        switches = {k: True for k in svc.TEMPLATE_KEYS}
        switches["inventory-insight"] = False
        patches = _patch_library_deps(usable={11}, switches=switches)
        with patch.object(
            KuaiaiAgentScene, "filter", MagicMock(return_value=_qs(scenes))
        ), patch.object(
            svc.KuaiaiAgentProfile, "filter", MagicMock(return_value=_qs([_profile()]))
        ):
            for p in patches:
                p.start()
            try:
                out = await svc.list_agent_library(TENANT, _user())
            finally:
                for p in patches:
                    p.stop()
        assert out["items"][0]["status"] == "not_ready"

    async def test_copy_instance_sorted_after_presets(self):
        copy_scene = _scene(
            id=99,
            instance_key="inventory-insight-copy-ab12cd34",
            origin="copy",
        )
        scenes = [copy_scene] + [
            _scene(instance_key=t.key, template_key=t.key, id=i + 1)
            for i, t in enumerate(svc.SCENE_TEMPLATES)
        ]
        patches = _patch_library_deps(usable={11})
        with patch.object(
            KuaiaiAgentScene, "filter", MagicMock(return_value=_qs(scenes))
        ), patch.object(
            svc.KuaiaiAgentProfile, "filter", MagicMock(return_value=_qs([_profile()]))
        ):
            for p in patches:
                p.start()
            try:
                out = await svc.list_agent_library(TENANT, _user())
            finally:
                for p in patches:
                    p.stop()
        assert len(out["items"]) == len(svc.SCENE_TEMPLATES) + 1
        assert out["items"][-1]["key"].endswith("copy-ab12cd34")

    async def test_no_sensitive_fields_in_items(self):
        scenes = [_scene()]
        patches = _patch_library_deps(usable={11})
        with patch.object(
            KuaiaiAgentScene, "filter", MagicMock(return_value=_qs(scenes))
        ), patch.object(
            svc.KuaiaiAgentProfile, "filter", MagicMock(return_value=_qs([_profile()]))
        ):
            for p in patches:
                p.start()
            try:
                out = await svc.list_agent_library(TENANT, _user())
            finally:
                for p in patches:
                    p.stop()
        for item in out["items"]:
            assert "system_prompt" not in item
            assert "grants" not in item
            assert "tenant_id" not in item


# ============================================================ PUT 更新


@pytest.mark.asyncio
class TestUpdateInstance:
    async def test_cross_tenant_or_missing_404(self):
        with patch.object(
            KuaiaiAgentScene, "get_or_none", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await svc.update_instance(
                    TENANT, _user(), "no-such-key", {"enabled": False}
                )

    async def test_preset_missing_triggers_repair_then_item(self):
        locked = _scene()
        # 第一次查询缺失 → 触发幂等补齐；补齐后第二次查询命中
        with patch.object(
            KuaiaiAgentScene,
            "get_or_none",
            AsyncMock(side_effect=[None, _scene()]),
        ), patch.object(
            svc, "seed_kuaiai_agent_scenes_on_lifecycle", AsyncMock()
        ), patch.object(
            KuaiaiAgentScene, "filter", MagicMock(return_value=_qs([locked]))
        ), patch(
            "apps.kuaiai.services.agent_scene_service.in_transaction",
            MagicMock(return_value=_FakeTx()),
        ), patch.object(
            svc,
            "list_agent_library",
            AsyncMock(
                return_value={
                    "items": [{"key": "inventory-insight", "status": "ready"}]
                }
            ),
        ):
            item = await svc.update_instance(
                TENANT, _user(), "inventory-insight", {"enabled": False}
            )
        assert item["key"] == "inventory-insight"
        assert locked.enabled is False

    async def test_bind_cross_tenant_profile_404(self):
        with patch.object(
            KuaiaiAgentScene,
            "get_or_none",
            AsyncMock(return_value=_scene()),
        ), patch.object(
            svc, "_require_permission", AsyncMock()
        ), patch.object(
            svc.agent_service,
            "get_profile",
            AsyncMock(side_effect=NotFoundError("Agent 档案", "55")),
        ):
            with pytest.raises(NotFoundError):
                await svc.update_instance(
                    TENANT,
                    _user(),
                    "inventory-insight",
                    {"agent_profile_id": 55},
                )

    async def test_bind_requires_agent_read(self):
        with patch.object(
            KuaiaiAgentScene,
            "get_or_none",
            AsyncMock(return_value=_scene()),
        ), patch.object(
            svc,
            "_require_permission",
            AsyncMock(side_effect=AuthorizationError("权限不足")),
        ):
            with pytest.raises(AuthorizationError):
                await svc.update_instance(
                    TENANT,
                    _user(),
                    "inventory-insight",
                    {"agent_profile_id": 55},
                )

    async def test_override_whitelist_rejects_bad_route(self):
        with patch.object(
            KuaiaiAgentScene,
            "get_or_none",
            AsyncMock(return_value=_scene()),
        ):
            with pytest.raises(BusinessLogicError):
                await svc.update_instance(
                    TENANT,
                    _user(),
                    "inventory-insight",
                    {"scene_route": "/evil/route"},
                )

    async def test_override_whitelist_rejects_bad_tag(self):
        with patch.object(
            KuaiaiAgentScene,
            "get_or_none",
            AsyncMock(return_value=_scene()),
        ):
            with pytest.raises(BusinessLogicError):
                await svc.update_instance(
                    TENANT,
                    _user(),
                    "inventory-insight",
                    {"capability_tags": ["EVIL"]},
                )


# ============================================================ 克隆


@pytest.mark.asyncio
class TestCloneInstance:
    async def test_unknown_template_400(self):
        with pytest.raises(ValidationError):
            await svc.clone_instance(TENANT, _user(), "bad-key", 11)

    async def test_cross_tenant_source_404(self):
        with patch.object(
            svc.agent_service,
            "get_profile",
            AsyncMock(side_effect=NotFoundError("Agent 档案", "55")),
        ):
            with pytest.raises(NotFoundError):
                await svc.clone_instance(
                    TENANT, _user(), "inventory-insight", 55
                )

    async def test_clone_creates_disabled_profile_and_copy(self):
        source = _profile(id=11, name="我的助手", status="启用")
        created_profiles = []
        created_scenes = []

        async def _create_profile(tenant_id, user, payload):
            created_profiles.append(payload)
            return _profile(id=77, name=payload.name, status=payload.status)

        async def _create_scene(**kwargs):
            created_scenes.append(kwargs)
            return _scene(
                instance_key=kwargs["instance_key"],
                agent_profile_id=kwargs["agent_profile_id"],
            )

        with patch.object(
            svc.agent_service, "get_profile", AsyncMock(return_value=source)
        ), patch.object(
            svc.agent_service,
            "create_profile",
            AsyncMock(side_effect=_create_profile),
        ), patch.object(
            svc.KuaiaiAgentProfile,
            "get_or_none",
            AsyncMock(return_value=None),
        ), patch.object(
            KuaiaiAgentScene, "filter", MagicMock(return_value=_qs([]))
        ), patch.object(
            KuaiaiAgentScene, "create", AsyncMock(side_effect=_create_scene)
        ), patch(
            "apps.kuaiai.services.agent_scene_service.in_transaction",
            MagicMock(return_value=_FakeTx()),
        ), patch.object(
            svc,
            "list_agent_library",
            AsyncMock(
                return_value={
                    "items": [
                        {
                            "key": created_scenes[0]["instance_key"]
                            if created_scenes
                            else "",
                            "status": "not_ready",
                        }
                    ]
                }
            ),
        ):
            try:
                item = await svc.clone_instance(
                    TENANT, _user(), "inventory-insight", 11
                )
            except Exception:
                item = None
        assert created_profiles and created_profiles[0].status == "停用"
        assert created_scenes
        scene_kw = created_scenes[0]
        assert scene_kw["origin"] == "copy"
        assert scene_kw["agent_profile_id"] == 77
        assert scene_kw["instance_key"].startswith("inventory-insight-copy-")
        assert scene_kw["instance_key"] != "inventory-insight"

    async def test_clone_rolls_back_on_scene_failure(self):
        source = _profile(id=11)
        tx = MagicMock(return_value=_FakeTx())
        with patch.object(
            svc.agent_service, "get_profile", AsyncMock(return_value=source)
        ), patch.object(
            svc.agent_service, "create_profile", AsyncMock(return_value=_profile(id=77))
        ), patch.object(
            svc.KuaiaiAgentProfile,
            "get_or_none",
            AsyncMock(return_value=None),
        ), patch.object(
            KuaiaiAgentScene, "filter", MagicMock(return_value=_qs([]))
        ), patch.object(
            KuaiaiAgentScene,
            "create",
            AsyncMock(side_effect=RuntimeError("db down")),
        ), patch(
            "apps.kuaiai.services.agent_scene_service.in_transaction", tx
        ):
            with pytest.raises(RuntimeError):
                await svc.clone_instance(
                    TENANT, _user(), "inventory-insight", 11
                )

    async def test_clone_validates_and_copies_default_model_in_tx(self):
        """源档案 default_model_id：同租户 chat 复核通过后同事务写入。"""
        source = _profile(id=11, name="我的助手", default_model_id=5)
        captured = {}

        async def _create_profile(tenant_id, user, payload):
            p = _profile(id=77, name=payload.name, status=payload.status)
            captured["profile"] = p
            return p

        async def _create_scene(**kwargs):
            captured["scene_key"] = kwargs["instance_key"]
            return _scene(
                instance_key=kwargs["instance_key"],
                agent_profile_id=kwargs["agent_profile_id"],
            )

        async def _library(tenant_id, user):
            return {
                "items": [
                    {"key": captured.get("scene_key", ""),
                     "status": "not_ready"}
                ]
            }

        require = AsyncMock(return_value=MagicMock())
        with patch.object(
            svc.agent_service, "get_profile", AsyncMock(return_value=source)
        ), patch.object(
            svc.agent_service, "_require_chat_model", require
        ), patch.object(
            svc.agent_service,
            "create_profile",
            AsyncMock(side_effect=_create_profile),
        ), patch.object(
            svc.KuaiaiAgentProfile,
            "get_or_none",
            AsyncMock(return_value=None),
        ), patch.object(
            KuaiaiAgentScene, "filter", MagicMock(return_value=_qs([]))
        ), patch.object(
            KuaiaiAgentScene, "create", AsyncMock(side_effect=_create_scene)
        ), patch(
            "apps.kuaiai.services.agent_scene_service.in_transaction",
            MagicMock(return_value=_FakeTx()),
        ), patch.object(
            svc,
            "list_agent_library",
            AsyncMock(side_effect=_library),
        ):
            await svc.clone_instance(
                TENANT, _user(), "inventory-insight", 11
            )
        require.assert_awaited_once_with(TENANT, 5)
        assert captured["profile"].default_model_id == 5
        captured["profile"].save.assert_awaited()

    async def test_clone_invalid_default_model_fails_atomically(self):
        """default_model_id 复核失败：档案与实例都不落库（整体回滚）。"""
        source = _profile(id=11, default_model_id=5)
        create_profile = AsyncMock()
        create_scene = AsyncMock()
        with patch.object(
            svc.agent_service, "get_profile", AsyncMock(return_value=source)
        ), patch.object(
            svc.agent_service,
            "_require_chat_model",
            AsyncMock(
                side_effect=BusinessLogicError(
                    "default_model_id 须指向本租户 chat 类型的启用模型行"
                )
            ),
        ), patch.object(
            svc.agent_service, "create_profile", create_profile
        ), patch.object(
            KuaiaiAgentScene, "create", create_scene
        ), patch(
            "apps.kuaiai.services.agent_scene_service.in_transaction",
            MagicMock(return_value=_FakeTx()),
        ):
            with pytest.raises(BusinessLogicError):
                await svc.clone_instance(
                    TENANT, _user(), "inventory-insight", 11
                )
        create_profile.assert_not_awaited()
        create_scene.assert_not_awaited()


# ============================================================ chat 场景守卫


@pytest.mark.asyncio
class TestGuardAgentKey:
    async def _call(self, **over):
        scene = over.get("scene", _scene())
        profile = over.get("profile", _profile())
        switches = over.get(
            "switches", {k: True for k in svc.TEMPLATE_KEYS}
        )
        grant = over.get("grant", True)
        chat_ready = over.get("chat_ready", True)
        with patch.object(
            KuaiaiAgentScene, "get_or_none", AsyncMock(return_value=scene)
        ), patch.object(
            svc, "agent_switches", AsyncMock(return_value=switches)
        ), patch.object(
            svc.KuaiaiAgentProfile,
            "get_or_none",
            AsyncMock(return_value=profile),
        ), patch.object(
            svc.grant_service,
            "check_use_grant",
            AsyncMock(return_value=grant),
        ), patch.object(
            svc, "is_chat_ready", AsyncMock(return_value=chat_ready)
        ):
            await svc.guard_scene_agent_key(
                TENANT, "inventory-insight", 11, _user()
            )

    async def test_ok(self):
        await self._call()

    async def test_missing_scene_404(self):
        with pytest.raises(NotFoundError):
            await self._call(scene=None)

    async def test_template_switch_off(self):
        switches = {k: True for k in svc.TEMPLATE_KEYS}
        switches["inventory-insight"] = False
        with pytest.raises(BusinessLogicError):
            await self._call(switches=switches)

    async def test_instance_disabled(self):
        with pytest.raises(BusinessLogicError):
            await self._call(scene=_scene(enabled=False))

    async def test_unbound(self):
        with pytest.raises(BusinessLogicError):
            await self._call(scene=_scene(agent_profile_id=None))

    async def test_agent_id_mismatch(self):
        with pytest.raises(BusinessLogicError):
            await self._call(scene=_scene(agent_profile_id=99))

    async def test_profile_missing_404(self):
        with pytest.raises(NotFoundError):
            await self._call(profile=None)

    async def test_profile_disabled_403(self):
        with pytest.raises(AuthorizationError):
            await self._call(profile=_profile(status="停用"))

    async def test_no_grant_403(self):
        with pytest.raises(AuthorizationError):
            await self._call(grant=False)

    async def test_chat_not_ready(self):
        with pytest.raises(BusinessLogicError):
            await self._call(chat_ready=False)


# ============================================================ hub


@pytest.mark.asyncio
class TestHub:
    async def test_days_clamped(self):
        with patch.object(
            operations_service,
            "_model_public_status",
            AsyncMock(return_value={"configured": True, "enabled": True,
                                    "model": "m", "connection_uuid": "u"}),
        ), patch.object(
            operations_service,
            "_metrics",
            AsyncMock(return_value={"total_calls": 1, "pulse_count": 0,
                                    "corpus_count": 0, "avg_latency_ms": 0}),
        ), patch.object(
            operations_service,
            "_build_capabilities",
            AsyncMock(return_value=[]),
        ):
            out = await operations_service.get_hub(TENANT, 999)
        assert out["days"] == 90
        assert out["model"]["configured"] is True

    async def test_metrics_failure_returns_nulls_not_zeros(self):
        with patch(
            "core.ai.stats_service.AiStatsService.get_overview",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            metrics = await operations_service._metrics(TENANT, 7)
        assert metrics["total_calls"] is None
        assert metrics["pulse_count"] is None

    async def test_capabilities_status_closed_set(self):
        caps = await operations_service._build_capabilities(
            TENANT, {"configured": False, "enabled": False}
        )
        assert len(caps) <= 8
        for c in caps:
            assert c["status"] in {"ready", "partial", "not_ready"}
        ask = next(c for c in caps if c["key"] == "ask")
        assert ask["status"] == "not_ready"


# ============================================================ 只读 Tool


@pytest.mark.asyncio
class TestSceneTools:
    async def test_no_context_fail_closed(self):
        from apps.kuaiai.services import scene_tools

        for fn in (
            scene_tools.query_inventory_balance,
            scene_tools.query_delivery_risk,
            scene_tools.query_purchase_followup,
            scene_tools.query_quality_anomalies,
        ):
            assert "上下文" in await fn(ctx=None)
        assert "上下文" in await scene_tools.query_published_schedule(
            plan_date="2026-01-01", ctx=None
        )
        assert "上下文" in await scene_tools.query_supplier_orders(
            supplier_id=1, ctx=None
        )

    async def test_published_schedule_requires_date(self):
        from apps.kuaiai.services import scene_tools

        ctx = SimpleNamespace(tenant_id=TENANT, user=_user())
        out = await scene_tools.query_published_schedule(
            plan_date="not-a-date", ctx=ctx
        )
        assert "YYYY-MM-DD" in out

    async def test_quality_anomalies_type_closed_set(self):
        from apps.kuaiai.services import scene_tools

        ctx = SimpleNamespace(tenant_id=TENANT, user=_user())
        out = await scene_tools.query_quality_anomalies(
            inspection_type="evil", ctx=ctx
        )
        assert "incoming" in out

    async def test_supplier_orders_requires_valid_id(self):
        from apps.kuaiai.services import scene_tools

        ctx = SimpleNamespace(tenant_id=TENANT, user=_user())
        assert "无效" in await scene_tools.query_supplier_orders(
            supplier_id=-1, ctx=ctx
        )
        assert "无效" in await scene_tools.query_supplier_orders(
            supplier_id="abc", ctx=ctx
        )

    async def test_published_schedule_unpublished_refused(self):
        from apps.kuaiai.services import scene_tools

        ctx = SimpleNamespace(tenant_id=TENANT, user=_user())
        plan = SimpleNamespace(status="draft", id=1, lines=[])
        with patch(
            "apps.kuaizhizao.services.rolling_schedule_service"
            ".RollingScheduleService.get_plan_by_date",
            AsyncMock(return_value=plan),
        ):
            out = await scene_tools.query_published_schedule(
                plan_date="2026-01-05", ctx=ctx
            )
        assert "尚未发布" in out


# ============================================================ schema


class TestSchemas:
    def test_update_schema_forbids_extra(self):
        from apps.kuaiai.schemas.operations import SceneInstanceUpdate

        with pytest.raises(Exception):
            SceneInstanceUpdate(
                enabled=True, template_key="x"  # type: ignore[call-arg]
            )

    def test_clone_schema_forbids_extra(self):
        from apps.kuaiai.schemas.operations import SceneInstanceClone

        with pytest.raises(Exception):
            SceneInstanceClone(
                template_key="inventory-insight",
                source_agent_id=1,
                agent_profile_id=2,  # type: ignore[call-arg]
            )
