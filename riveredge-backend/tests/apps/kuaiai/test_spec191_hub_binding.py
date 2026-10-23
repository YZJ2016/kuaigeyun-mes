"""KU-AI spec 191 单测：hub 场景卡绑定 + 设置页能力绑定（全部 mock，不触真库）。

覆盖要点：
- 绑定解析三态：无条目→同 key 预置；显式 null→解绑；实例 key→覆盖（含复制实例）；
  预置软删/未落地/覆盖实例缺失的降级原因；
- hub 场景卡状态级联每分支（总开关/实例停用/未绑档案/档案缺失/档案停用/
  chat 未就绪/无使用权/档案无业务 Tool/仅写 Tool 豁免）；
- capabilities[] 组成：ask + 逐模板场景卡；data_query 不再出现；
- 设置 GET：逐模板绑定视图 + 实例选项 + resolved 解析；
- 设置 PUT：越租户/已删实例 422、缺省 capability_bindings 不修改、
  整 map 替换写回与审计字段名。
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.models.agent import KuaiaiAgentProfile
from apps.kuaiai.models.agent_scene import KuaiaiAgentScene
from apps.kuaiai.schemas.operations import SettingsUpdateIn
from apps.kuaiai.services import agent_scene_service as scene_svc
from apps.kuaiai.services import operations_service as ops_svc
from apps.kuaiai.services import settings_service as svc
from apps.kuaiai.services import tool_catalog_service
from core.models.integration_config import IntegrationConfig
from core.models.site_setting import SiteSetting
from core.utils.integration_settings import (
    read_capability_bindings,
    resolve_capability_binding,
    validate_capability_bindings_payload,
)
from infra.exceptions.exceptions import ValidationError

TENANT = 7
USER_ID = 5
CHAT_UUID = "11111111-1111-1111-1111-111111111111"
TEMPLATE_KEYS = tuple(t.key for t in scene_svc.SCENE_TEMPLATES)
FIRST = TEMPLATE_KEYS[0]  # inventory-insight


def _user(uid: int = USER_ID):
    return SimpleNamespace(id=uid, full_name="测试用户", username="tester")


def _qs(rows=()):
    q = MagicMock()
    rows = list(rows)
    for m in ("filter", "order_by", "offset", "limit", "select_for_update"):
        setattr(q, m, MagicMock(return_value=q))
    q.all = AsyncMock(return_value=rows)
    q.first = AsyncMock(return_value=rows[0] if rows else None)
    q.count = AsyncMock(return_value=len(rows))
    q.exists = AsyncMock(return_value=bool(rows))
    q.values_list = AsyncMock(return_value=rows)
    return q


class _FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _tx():
    return MagicMock(return_value=_FakeTx())


def _scene(key=FIRST, **kw):
    base = dict(
        id=1,
        tenant_id=TENANT,
        instance_key=key,
        template_key=FIRST,
        origin="system_seed",
        agent_profile_id=11,
        overrides={},
        enabled=True,
        deleted_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _profile(**kw):
    base = dict(
        id=11,
        tenant_id=TENANT,
        name="库存洞察助手",
        status="启用",
        enabled_tools=["query_inventory"],
        deleted_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _catalog():
    return [
        SimpleNamespace(name="search_knowledge", kind="read"),
        SimpleNamespace(name="query_work_orders", kind="read"),
        SimpleNamespace(name="query_inventory", kind="read"),
        SimpleNamespace(name="analyze_delivery_risk", kind="read"),
        SimpleNamespace(name="query_purchase_orders", kind="read"),
        SimpleNamespace(name="query_schedule", kind="read"),
        SimpleNamespace(name="analyze_quality", kind="read"),
        SimpleNamespace(name="submit_production_feedback", kind="write"),
        SimpleNamespace(name="update_workorder_status", kind="write"),
    ]


async def _caps(
    scenes,
    profiles,
    *,
    kuaiai=None,
    chat=True,
    usable=None,
    has_agent_read=True,
    switches=None,
    catalog=None,
):
    with patch.object(
        scene_svc,
        "_site_kuaiai_integration",
        AsyncMock(return_value=kuaiai if kuaiai is not None else {}),
    ), patch.object(
        KuaiaiAgentScene, "filter", MagicMock(return_value=_qs(scenes))
    ), patch.object(
        KuaiaiAgentProfile, "filter", MagicMock(return_value=_qs(profiles))
    ), patch.object(
        scene_svc,
        "agent_switches",
        AsyncMock(
            return_value=switches
            or {k: True for k in scene_svc.TEMPLATE_KEYS}
        ),
    ), patch.object(
        scene_svc.grant_service,
        "usable_profile_ids",
        AsyncMock(return_value=set(usable if usable is not None else {11})),
    ), patch.object(
        scene_svc, "_has_permission", AsyncMock(return_value=has_agent_read)
    ), patch.object(
        scene_svc,
        "_route_permissions_for_user",
        AsyncMock(return_value={}),
    ), patch.object(
        tool_catalog_service,
        "list_tool_catalog",
        MagicMock(return_value=catalog if catalog is not None else _catalog()),
    ):
        return await ops_svc._build_capabilities(
            TENANT, {"configured": chat, "enabled": chat}, _user()
        )


def _card(caps, key):
    return next(c for c in caps if c["key"] == key)


def _preset_scene_set(**kw):
    """六个预置实例 + 各自启用档案（id=11..16），首个可 kw 覆盖。"""
    scenes, profiles = [], []
    for i, key in enumerate(TEMPLATE_KEYS):
        pid = 11 + i
        scene_kw = dict(kw) if i == 0 else {}
        scene_kw.setdefault("agent_profile_id", pid)
        scenes.append(_scene(key, id=i + 1, **scene_kw))
        profiles.append(_profile(id=pid))
    return scenes, profiles


# ============================================================ 绑定解析三态


@pytest.mark.asyncio
class TestBindingResolution:
    async def test_default_binding_resolves_preset(self):
        scenes, profiles = _preset_scene_set()
        caps = await _caps(scenes, profiles)
        card = _card(caps, FIRST)
        assert card["status"] == "ready"
        assert card["scene_key"] == FIRST
        assert card["agent_profile_id"] == 11
        assert card["disabled_reason"] is None

    async def test_explicit_null_unbinds(self):
        scenes, profiles = _preset_scene_set()
        caps = await _caps(
            scenes,
            profiles,
            kuaiai={"capability_bindings": {FIRST: None}},
        )
        card = _card(caps, FIRST)
        assert card["status"] == "not_ready"
        assert card["disabled_reason"] == "已解绑场景"
        assert card["scene_key"] is None
        assert card["agent_profile_id"] is None

    async def test_override_to_copy_instance(self):
        scenes, profiles = _preset_scene_set()
        copy = _scene(
            "inv-copy-1",
            id=99,
            template_key=FIRST,
            origin="copy",
            agent_profile_id=11,
        )
        caps = await _caps(
            scenes + [copy],
            profiles,
            kuaiai={"capability_bindings": {FIRST: "inv-copy-1"}},
        )
        card = _card(caps, FIRST)
        assert card["status"] == "ready"
        assert card["scene_key"] == "inv-copy-1"
        assert card["agent_profile_id"] == 11

    async def test_preset_soft_deleted(self):
        scenes, profiles = _preset_scene_set()
        scenes[0].deleted_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        caps = await _caps(scenes, profiles)
        card = _card(caps, FIRST)
        assert card["status"] == "not_ready"
        assert card["disabled_reason"] == "预置场景已删除"

    async def test_preset_missing_provisioning(self):
        scenes, profiles = _preset_scene_set()
        caps = await _caps(scenes[1:], profiles[1:])
        card = _card(caps, FIRST)
        assert card["status"] == "not_ready"
        assert card["disabled_reason"] == "场景预置未完成，请重新同步应用后重试"

    async def test_override_missing_instance(self):
        scenes, profiles = _preset_scene_set()
        caps = await _caps(
            scenes,
            profiles,
            kuaiai={"capability_bindings": {FIRST: "ghost-key"}},
        )
        card = _card(caps, FIRST)
        assert card["status"] == "not_ready"
        assert card["disabled_reason"] == "绑定的场景实例不存在或已删除"
        assert card["scene_key"] is None

    async def test_soft_deleted_preset_still_bindable_via_override(self):
        """预置软删后经覆盖改绑复制实例可恢复（AC2 括注）。"""
        scenes, profiles = _preset_scene_set()
        scenes[0].deleted_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        copy = _scene(
            "inv-copy-1", id=99, template_key=FIRST, origin="copy"
        )
        caps = await _caps(
            scenes + [copy],
            profiles,
            kuaiai={"capability_bindings": {FIRST: "inv-copy-1"}},
        )
        assert _card(caps, FIRST)["status"] == "ready"


# ============================================================ 状态级联


@pytest.mark.asyncio
class TestStatusCascade:
    async def test_template_switch_off(self):
        scenes, profiles = _preset_scene_set()
        switches = {k: True for k in TEMPLATE_KEYS}
        switches[FIRST] = False
        caps = await _caps(scenes, profiles, switches=switches)
        card = _card(caps, FIRST)
        assert card["status"] == "not_ready"
        assert card["disabled_reason"] == "场景总开关已停用"

    async def test_instance_disabled(self):
        scenes, profiles = _preset_scene_set(enabled=False)
        caps = await _caps(scenes, profiles)
        card = _card(caps, FIRST)
        assert card["status"] == "not_ready"
        assert card["disabled_reason"] == "场景实例已停用"

    async def test_no_profile_bound(self):
        scenes, profiles = _preset_scene_set(agent_profile_id=None)
        caps = await _caps(scenes, profiles)
        card = _card(caps, FIRST)
        assert card["status"] == "not_ready"
        assert card["disabled_reason"] == "未绑定 Agent 档案"

    async def test_profile_missing(self):
        scenes, profiles = _preset_scene_set()
        profiles[0].deleted_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # 档案软删后 profiles_by_id 查不到（deleted_at__isnull 过滤由调用方保证）
        live = [p for p in profiles if p.deleted_at is None]
        caps = await _caps(scenes, live)
        card = _card(caps, FIRST)
        assert card["status"] == "not_ready"
        assert card["disabled_reason"] == "绑定的 Agent 档案不存在或已删除"

    async def test_profile_disabled(self):
        scenes, profiles = _preset_scene_set()
        profiles[0].status = "停用"
        caps = await _caps(scenes, profiles)
        card = _card(caps, FIRST)
        assert card["status"] == "not_ready"
        assert card["disabled_reason"] == "Agent 档案未启用"

    async def test_chat_not_ready_partial(self):
        scenes, profiles = _preset_scene_set()
        caps = await _caps(scenes, profiles, chat=False)
        card = _card(caps, FIRST)
        assert card["status"] == "partial"
        assert card["disabled_reason"] == "未配置可用的对话模型连接"

    async def test_no_use_grant_partial_and_masked(self):
        scenes, profiles = _preset_scene_set()
        caps = await _caps(
            scenes, profiles, usable=set(), has_agent_read=False
        )
        card = _card(caps, FIRST)
        assert card["status"] == "partial"
        assert card["disabled_reason"] == "当前用户无该 Agent 档案使用权"
        # 无使用权且无 agent:read → 档案 id 脱敏为 null（同 _build_item）
        assert card["agent_profile_id"] is None

    async def test_no_business_tool_not_ready(self):
        scenes, profiles = _preset_scene_set()
        profiles[0].enabled_tools = ["search_knowledge"]
        caps = await _caps(scenes, profiles)
        card = _card(caps, FIRST)
        assert card["status"] == "not_ready"
        assert card["disabled_reason"] == "绑定档案未勾选业务查询工具"

    async def test_write_only_tool_exempt(self):
        """档案只含 kind=write Tool 不受业务查询 Tool 限制（AC3）。"""
        scenes, profiles = _preset_scene_set()
        profiles[0].enabled_tools = ["submit_production_feedback"]
        caps = await _caps(scenes, profiles)
        assert _card(caps, FIRST)["status"] == "ready"

    async def test_unregistered_tool_name_not_counted(self):
        """enabled_tools 含目录外（未注册/未知）名称不算业务 Tool。"""
        scenes, profiles = _preset_scene_set()
        profiles[0].enabled_tools = ["legacy_gone_tool"]
        caps = await _caps(scenes, profiles)
        card = _card(caps, FIRST)
        assert card["status"] == "not_ready"
        assert card["disabled_reason"] == "绑定档案未勾选业务查询工具"


# ============================================================ capabilities[] 组成


@pytest.mark.asyncio
class TestCapabilitiesShape:
    async def test_caps_are_ask_plus_one_per_template(self):
        scenes, profiles = _preset_scene_set()
        caps = await _caps(scenes, profiles)
        keys = [c["key"] for c in caps]
        assert keys == ["ask", *TEMPLATE_KEYS]
        assert "data_query" not in keys

    async def test_ask_card_unchanged(self):
        scenes, profiles = _preset_scene_set()
        caps = await _caps(scenes, profiles, chat=False)
        ask = _card(caps, "ask")
        assert ask["status"] == "not_ready"
        assert ask["route"] == "/apps/kuaiai/chat"
        assert ask["disabled_reason"] == "未配置可用的对话模型连接"

    async def test_scene_cards_carry_template_meta(self):
        scenes, profiles = _preset_scene_set()
        caps = await _caps(scenes, profiles)
        template = scene_svc.SCENE_TEMPLATES[0]
        card = _card(caps, FIRST)
        assert card["name"] == template.name
        assert card["description"] == template.description

    async def test_scene_aggregation_failure_degrades(self):
        """场景数据源整体失败 → 每模板 not_ready 占位，不整页 500。"""
        with patch.object(
            scene_svc,
            "_site_kuaiai_integration",
            AsyncMock(return_value={}),
        ), patch.object(
            KuaiaiAgentScene,
            "filter",
            MagicMock(side_effect=RuntimeError("db down")),
        ):
            caps = await ops_svc._build_capabilities(
                TENANT, {"configured": True, "enabled": True}, _user()
            )
        scene_cards = [c for c in caps if c["key"] != "ask"]
        assert len(scene_cards) == len(TEMPLATE_KEYS)
        assert all(c["status"] == "not_ready" for c in scene_cards)
        assert all(
            c["disabled_reason"] == "场景状态读取失败" for c in scene_cards
        )


# ============================================================ 绑定读写工具函数


class TestBindingHelpers:
    def test_read_bindings_filters_to_template_keys(self):
        kuaiai = {
            "capability_bindings": {
                FIRST: "inv-copy-1",
                "evil-key": "inv-copy-2",
                TEMPLATE_KEYS[1]: None,
                TEMPLATE_KEYS[2]: 42,  # 非法类型按无条目
            }
        }
        out = read_capability_bindings(kuaiai, TEMPLATE_KEYS)
        assert out == {FIRST: "inv-copy-1", TEMPLATE_KEYS[1]: None}

    def test_validate_payload_closed_set_and_types(self):
        ok = validate_capability_bindings_payload(
            {FIRST: "inv-copy-1", TEMPLATE_KEYS[1]: None}, TEMPLATE_KEYS
        )
        assert ok == {FIRST: "inv-copy-1", TEMPLATE_KEYS[1]: None}
        with pytest.raises(ValidationError):
            validate_capability_bindings_payload(
                {"evil-key": "x"}, TEMPLATE_KEYS
            )
        with pytest.raises(ValidationError):
            validate_capability_bindings_payload(
                {FIRST: 123}, TEMPLATE_KEYS
            )
        with pytest.raises(ValidationError):
            validate_capability_bindings_payload(
                {FIRST: "  "}, TEMPLATE_KEYS
            )
        with pytest.raises(ValidationError):
            validate_capability_bindings_payload("not-a-dict", TEMPLATE_KEYS)

    def test_resolve_binding_three_states(self):
        keys = {FIRST, "inv-copy-1"}
        assert (
            resolve_capability_binding({}, FIRST, keys) == FIRST
        )  # 无条目→同 key 预置
        assert (
            resolve_capability_binding({FIRST: None}, FIRST, keys) is None
        )  # null→解绑
        assert (
            resolve_capability_binding({FIRST: "inv-copy-1"}, FIRST, keys)
            == "inv-copy-1"
        )  # 覆盖
        assert (
            resolve_capability_binding({FIRST: "ghost"}, FIRST, keys) is None
        )  # 覆盖实例缺失
        assert (
            resolve_capability_binding({}, "ghost-tpl", keys) is None
        )  # 无条目且同 key 预置缺失


# ============================================================ 设置 GET/PUT


def _site(settings=None, updated_at=None):
    return SimpleNamespace(
        id=3,
        uuid="site-uuid-1",
        tenant_id=TENANT,
        updated_at=updated_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
        settings=settings if settings is not None else {},
        save=AsyncMock(),
    )


def _conn(uuid=CHAT_UUID, role="chat", is_active=True, cfg_extra=None, **kw):
    cfg = {
        "model_role": role,
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "api_key": "sk-real-key",
    }
    if cfg_extra:
        cfg.update(cfg_extra)
    base = dict(
        uuid=uuid,
        tenant_id=TENANT,
        name="DeepSeek 连接",
        type="deepseek",
        is_active=is_active,
        config=cfg,
        get_config=lambda: cfg,
        save=AsyncMock(),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _conn_filter(conns):
    def _filter(**kwargs):
        uuid = kwargs.get("uuid")
        if uuid is not None:
            hit = next((c for c in conns if str(c.uuid) == str(uuid)), None)
            return _qs([hit] if hit else [])
        return _qs(list(conns))

    return MagicMock(side_effect=_filter)


def _patch_get_settings(site):
    return patch(
        "core.services.system.site_setting_service.SiteSettingService.get_settings",
        AsyncMock(return_value=site),
    )


def _payload(**over):
    base = dict(
        version="v1",
        chat_connection_uuid=CHAT_UUID,
        vision_connection_uuid=None,
        agent_switches={k: True for k in TEMPLATE_KEYS},
        capabilities=dict(
            tools_enabled=True,
            rag_enabled=True,
            rag_use_embedding=True,
            rag_backend="native",
            rag_top_k=5,
            stream_enabled=True,
            custom_system_prompt="",
        ),
    )
    base.update(over)
    return SettingsUpdateIn(**base)


def _scene_filter(scenes):
    """KuaiaiAgentScene.filter mock：instance_key__in → 命中行 keys。"""
    by_key = {s.instance_key: s for s in scenes}

    def _filter(**kwargs):
        keys = kwargs.get("instance_key__in")
        if keys is not None:
            hits = [
                k
                for k in keys
                if k in by_key and by_key[k].deleted_at is None
            ]
            return _qs(hits)
        return _qs(list(scenes))

    return MagicMock(side_effect=_filter)


class TestSettingsGetBindings:
    @pytest.mark.asyncio
    async def test_get_returns_bindings_options_and_resolved(self):
        scenes, profiles = _preset_scene_set()
        copy = _scene(
            "inv-copy-1", id=99, template_key=FIRST, origin="copy"
        )
        library_items = [
            {"key": s.instance_key, "name": s.instance_key,
             "template_key": s.template_key}
            for s in scenes
        ] + [
            {"key": copy.instance_key, "name": "副本",
             "template_key": copy.template_key}
        ]
        site = _site(
            {
                "integrations": {
                    "kuaiai": {
                        "capability_bindings": {
                            FIRST: "inv-copy-1",
                            TEMPLATE_KEYS[1]: None,
                        }
                    }
                }
            }
        )
        with _patch_get_settings(site), patch.object(
            IntegrationConfig, "filter", _conn_filter([])
        ), patch(
            "core.utils.integration_settings._load_llm_connection",
            AsyncMock(return_value=None),
        ), patch.object(
            svc,
            "list_agent_library",
            AsyncMock(return_value={"items": library_items}),
        ):
            out = await svc.get_settings(TENANT, _user())

        rows = {r["capability_key"]: r for r in out["capability_bindings"]}
        assert set(rows) == set(TEMPLATE_KEYS)
        assert rows[FIRST]["override_present"] is True
        assert rows[FIRST]["override_instance_key"] == "inv-copy-1"
        assert rows[FIRST]["resolved_instance_key"] == "inv-copy-1"
        assert rows[TEMPLATE_KEYS[1]]["override_present"] is True
        assert rows[TEMPLATE_KEYS[1]]["override_instance_key"] is None
        assert rows[TEMPLATE_KEYS[1]]["resolved_instance_key"] is None
        assert rows[TEMPLATE_KEYS[2]]["override_present"] is False
        assert (
            rows[TEMPLATE_KEYS[2]]["resolved_instance_key"]
            == TEMPLATE_KEYS[2]
        )
        opt_keys = {o["key"] for o in out["scene_instance_options"]}
        assert "inv-copy-1" in opt_keys and FIRST in opt_keys

    @pytest.mark.asyncio
    async def test_get_defaults_when_no_bindings(self):
        site = _site({})
        with _patch_get_settings(site), patch.object(
            IntegrationConfig, "filter", _conn_filter([])
        ), patch(
            "core.utils.integration_settings._load_llm_connection",
            AsyncMock(return_value=None),
        ), patch.object(
            svc, "list_agent_library", AsyncMock(return_value={"items": []})
        ):
            out = await svc.get_settings(TENANT, _user())
        assert all(
            r["override_present"] is False for r in out["capability_bindings"]
        )
        assert all(
            r["resolved_instance_key"] is None
            for r in out["capability_bindings"]
        )
        assert out["scene_instance_options"] == []


class TestSettingsPutBindings:
    def _run_save(self, site, payload, scenes=()):
        conn = _conn(CHAT_UUID, "chat")
        return (
            patch.object(
                IntegrationConfig, "filter", _conn_filter([conn])
            ),
            _patch_get_settings(site),
            patch.object(
                KuaiaiAgentScene, "filter", _scene_filter(scenes)
            ),
            patch.object(
                SiteSetting,
                "filter",
                MagicMock(return_value=_qs([site])),
            ),
            patch("apps.kuaiai.services.settings_service.in_transaction", _tx()),
            patch("core.ai.runtime.model_factory.evict_model_cache", MagicMock()),
            patch.object(svc, "get_settings", AsyncMock(return_value={"ok": True})),
        )

    @pytest.mark.asyncio
    async def test_cross_tenant_or_deleted_instance_422(self):
        site = _site({"integrations": {"kuaiai": {}}})
        # KuaiaiAgentScene.filter 只回本租户未删行 → 越租户 key 查不到 → 422
        scenes = [_scene("inv-copy-1")]
        bad_keys = ("other-tenant-key", "deleted-copy")
        for bad in bad_keys:
            payload = _payload(
                version=svc._version_of(site),
                capability_bindings={FIRST: bad},
            )
            p = self._run_save(site, payload, scenes)
            with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
                with pytest.raises(ValidationError):
                    await svc.update_settings(TENANT, _user(), payload)
        site.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deleted_instance_422(self):
        site = _site({"integrations": {"kuaiai": {}}})
        scenes = [
            _scene(
                "gone-copy",
                deleted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        ]
        payload = _payload(
            version=svc._version_of(site),
            capability_bindings={FIRST: "gone-copy"},
        )
        p = self._run_save(site, payload, scenes)
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
            with pytest.raises(ValidationError):
                await svc.update_settings(TENANT, _user(), payload)
        site.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_omitted_key_not_modified(self):
        """PUT 缺省 capability_bindings → 站点既有覆盖原样保留。"""
        site = _site(
            {
                "integrations": {
                    "kuaiai": {
                        "capability_bindings": {FIRST: "inv-copy-1"},
                        "unrelated_flag": "keep-me",
                    }
                }
            }
        )
        payload = _payload(version=svc._version_of(site))
        assert payload.capability_bindings is None
        p = self._run_save(site, payload)
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
            await svc.update_settings(TENANT, _user(), payload)
        kuaiai = site.settings["integrations"]["kuaiai"]
        assert kuaiai["capability_bindings"] == {FIRST: "inv-copy-1"}
        assert kuaiai["unrelated_flag"] == "keep-me"

    @pytest.mark.asyncio
    async def test_saves_bindings_and_audit_field(self):
        site = _site({"integrations": {"kuaiai": {}}})
        scenes = [_scene("inv-copy-1")]
        payload = _payload(
            version=svc._version_of(site),
            capability_bindings={FIRST: "inv-copy-1", TEMPLATE_KEYS[1]: None},
        )
        p = self._run_save(site, payload, scenes)
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
            await svc.update_settings(TENANT, _user(), payload)
        kuaiai = site.settings["integrations"]["kuaiai"]
        assert kuaiai["capability_bindings"] == {
            FIRST: "inv-copy-1",
            TEMPLATE_KEYS[1]: None,
        }
        site.save.assert_awaited_once_with(
            update_fields=["settings", "updated_at"]
        )

    @pytest.mark.asyncio
    async def test_empty_map_clears_overrides(self):
        site = _site(
            {
                "integrations": {
                    "kuaiai": {"capability_bindings": {FIRST: "inv-copy-1"}}
                }
            }
        )
        payload = _payload(
            version=svc._version_of(site), capability_bindings={}
        )
        p = self._run_save(site, payload)
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
            await svc.update_settings(TENANT, _user(), payload)
        assert (
            site.settings["integrations"]["kuaiai"]["capability_bindings"]
            == {}
        )

    @pytest.mark.asyncio
    async def test_unknown_capability_key_422(self):
        site = _site({"integrations": {"kuaiai": {}}})
        payload = _payload(
            version=svc._version_of(site),
            capability_bindings={"evil-key": "x"},
        )
        p = self._run_save(site, payload)
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
            with pytest.raises(ValidationError):
                await svc.update_settings(TENANT, _user(), payload)
        site.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_validation_before_version_conflict(self):
        """非法绑定值先于版本比对报错（与候选连接校验同顺序）。"""
        site = _site({"integrations": {"kuaiai": {}}})
        payload = _payload(
            version="stale",
            capability_bindings={"evil-key": "x"},
        )
        p = self._run_save(site, payload)
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
            with pytest.raises(ValidationError):
                await svc.update_settings(TENANT, _user(), payload)


class TestSchema:
    def test_capability_bindings_optional_field(self):
        payload = SettingsUpdateIn(
            version="v",
            chat_connection_uuid="u",
            agent_switches={k: True for k in TEMPLATE_KEYS},
            capabilities=dict(
                tools_enabled=True,
                rag_enabled=True,
                rag_use_embedding=True,
                rag_backend="native",
                rag_top_k=5,
                stream_enabled=True,
                custom_system_prompt="",
            ),
        )
        assert payload.capability_bindings is None
        with pytest.raises(Exception):
            SettingsUpdateIn(
                version="v",
                chat_connection_uuid="u",
                agent_switches={k: True for k in TEMPLATE_KEYS},
                capabilities=dict(
                    tools_enabled=True,
                    rag_enabled=True,
                    rag_use_embedding=True,
                    rag_backend="native",
                    rag_top_k=5,
                    stream_enabled=True,
                    custom_system_prompt="",
                ),
                evil_field=1,  # type: ignore[call-arg]
            )

