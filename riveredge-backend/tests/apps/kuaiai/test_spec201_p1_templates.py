"""KU-AI spec 201 单测：P1 场景预置模板（全部 mock，不触真库）。

覆盖要点：
- SCENE_TEMPLATES 扩为 9：3 个新模板 key/Tool 组合/category 闭集/插画/路由白名单；
- 既有三模板（inventory-insight/purchase-followup/quality-analysis）追加 P1 只读
  Tool 且 system_prompt 只引用本模板 Tool 并要求查不到如实说明；
- 生命周期种子：存量 6 实例租户只补 3 个新实例（既有实例/档案不动），
  新租户 9 实例 + 9 份停用空授权只读档案；
- 新场景路由入 SCENE_ROUTE_PERMISSIONS 白名单，无权限 scene_available=false；
- 设置 GET 返回 agent_templates（9 项按模板顺序），9 键开关可保存/缺键 422；
- 能力绑定无覆盖时默认解析同 key 预置实例（spec 191 依赖）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.constants import ENABLED_TOOL_NAMES
from apps.kuaiai.models.agent_scene import KuaiaiAgentScene
from apps.kuaiai.schemas.operations import SettingsUpdateIn
from apps.kuaiai.services import agent_scene_service as svc
from apps.kuaiai.services import settings_service
from core.models.integration_config import IntegrationConfig
from core.models.site_setting import SiteSetting
from core.utils.integration_settings import resolve_capability_binding
from infra.exceptions.exceptions import ValidationError

TENANT = 7
USER_ID = 5

NEW_TEMPLATE_KEYS = {"shift-lead", "order-delivery", "work-instruction"}
OLD_TEMPLATE_KEYS = {
    "inventory-insight",
    "planner-advisor",
    "purchase-followup",
    "schedule-explainer",
    "quality-analysis",
    "supplier-collaboration",
}
WRITE_TOOL_NAMES = {"submit_production_feedback", "update_workorder_status"}

_EXPECTED_NEW_TOOLS = {
    "shift-lead": (
        "query_work_orders",
        "analyze_kitting",
        "query_material_shortages",
        "query_production_daily",
        "query_pulse_signals",
    ),
    "order-delivery": (
        "query_sales_orders",
        "query_work_orders",
        "analyze_delivery_risk",
        "analyze_kitting",
    ),
    "work-instruction": (
        "search_knowledge",
        "query_process_routes",
        "query_work_orders",
    ),
}

_EXPECTED_APPENDED_TOOLS = {
    "inventory-insight": {
        "query_inventory_alerts",
        "query_replenishment_suggestions",
        "query_slow_moving_inventory",
    },
    "purchase-followup": {"query_purchase_arrival_warnings"},
    "quality-analysis": {
        "query_quality_exceptions",
        "analyze_first_pass_yield",
        "analyze_defect_pareto",
    },
}

_TEMPLATE_MAP = {t.key: t for t in svc.SCENE_TEMPLATES}


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
    q.values_list = AsyncMock(return_value=rows)
    q.values = AsyncMock(return_value=rows)
    return q


class _FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _tx():
    return MagicMock(return_value=_FakeTx())


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
        enabled_tools=["query_inventory"],
        mcp_server_ids=[],
        status="启用",
        grant_mode="ROLE",
        deleted_at=None,
        save=AsyncMock(),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _site(settings=None, updated_at=None):
    return SimpleNamespace(
        id=3,
        uuid="site-uuid-1",
        tenant_id=TENANT,
        updated_at=updated_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
        settings=settings if settings is not None else {},
        save=AsyncMock(),
    )


CHAT_UUID = "11111111-1111-1111-1111-111111111111"
VISION_UUID = "22222222-2222-2222-2222-222222222222"


def _conn(uuid=CHAT_UUID, role="chat", is_active=True):
    cfg = {
        "model_role": role,
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "api_key": "sk-real-key",
    }
    return SimpleNamespace(
        uuid=uuid,
        tenant_id=TENANT,
        name="DeepSeek 连接",
        type="deepseek",
        is_active=is_active,
        config=cfg,
        get_config=lambda: cfg,
        save=AsyncMock(),
    )


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


def _payload_obj(**over):
    base = dict(
        version="v1",
        chat_connection_uuid=CHAT_UUID,
        vision_connection_uuid=VISION_UUID,
        agent_switches={t.key: True for t in svc.SCENE_TEMPLATES},
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


# ============================================================ 模板定义


class TestTemplateDefinitions:
    def test_nine_template_keys(self):
        assert len(svc.SCENE_TEMPLATES) == 9
        assert set(svc.TEMPLATE_KEYS) == OLD_TEMPLATE_KEYS | NEW_TEMPLATE_KEYS

    def test_new_templates_exact_tools(self):
        for key, expected in _EXPECTED_NEW_TOOLS.items():
            template = _TEMPLATE_MAP[key]
            assert tuple(template.readonly_tools) == expected, key

    def test_existing_templates_appended_p1_tools(self):
        for key, appended in _EXPECTED_APPENDED_TOOLS.items():
            template = _TEMPLATE_MAP[key]
            assert appended <= set(template.readonly_tools), key
        # 未在追加名单内的既有模板 Tool 组合不变
        assert _TEMPLATE_MAP["planner-advisor"].readonly_tools == (
            "query_work_orders",
            "analyze_delivery_risk",
        )
        assert _TEMPLATE_MAP["schedule-explainer"].readonly_tools == (
            "query_schedule",
        )
        assert _TEMPLATE_MAP["supplier-collaboration"].readonly_tools == (
            "query_purchase_orders",
        )

    def test_all_preset_tools_readonly_in_closed_set(self):
        for template in svc.SCENE_TEMPLATES:
            assert set(template.readonly_tools) <= ENABLED_TOOL_NAMES, (
                template.key
            )
            assert not set(template.readonly_tools) & WRITE_TOOL_NAMES, (
                template.key
            )

    def test_category_closed_set(self):
        for template in svc.SCENE_TEMPLATES:
            assert template.category in svc.SCENE_CATEGORIES, template.key

    def test_category_unknown_rejected(self):
        with pytest.raises(ValueError):
            svc.SceneTemplate(
                key="bad",
                name="bad",
                description="",
                image_key="",
                capability_tags=(),
                sample_prompt="",
                scene_route=None,
                system_prompt="",
                readonly_tools=(),
                category="evil",
            )

    def test_new_template_routes_whitelisted(self):
        for key in NEW_TEMPLATE_KEYS:
            route = _TEMPLATE_MAP[key].scene_route
            assert route in svc.SCENE_ROUTE_PERMISSIONS, key

    def test_new_image_keys_whitelisted(self):
        for key in NEW_TEMPLATE_KEYS:
            assert _TEMPLATE_MAP[key].image_key in svc.SCENE_IMAGE_KEYS

    def test_system_prompt_only_references_own_tools(self):
        for template in svc.SCENE_TEMPLATES:
            prompt = template.system_prompt
            own = set(template.readonly_tools)
            for tool_name in ENABLED_TOOL_NAMES:
                if tool_name in prompt:
                    assert tool_name in own, (
                        f"{template.key} 引用非本模板 Tool: {tool_name}"
                    )
            assert "查不到" in prompt and "如实说明" in prompt, template.key


# ============================================================ 生命周期种子


@pytest.mark.asyncio
class TestLifecycleSeedP1:
    async def test_existing_tenant_only_seeds_three_new(self):
        """存量租户（6 预置实例已建）：只补 3 个新实例，既有实例/档案不动。"""
        existing_keys = [k for k in svc.TEMPLATE_KEYS if k not in NEW_TEMPLATE_KEYS]
        assert len(existing_keys) == 6
        created_scenes = []
        created_templates = []

        async def _mk_profile(tenant_id, template):
            created_templates.append(template.key)
            return _profile(id=100 + len(created_templates), name=template.name)

        async def _mk_scene(**kwargs):
            created_scenes.append(kwargs)
            return _scene(
                instance_key=kwargs["instance_key"],
                agent_profile_id=kwargs["agent_profile_id"],
            )

        with patch.object(
            KuaiaiAgentScene,
            "filter",
            MagicMock(return_value=_qs(existing_keys, count=9)),
        ), patch.object(
            KuaiaiAgentScene, "get_or_none", AsyncMock(return_value=None)
        ), patch.object(
            KuaiaiAgentScene, "create", AsyncMock(side_effect=_mk_scene)
        ), patch(
            "apps.kuaiai.services.agent_scene_service.in_transaction", _tx()
        ), patch.object(
            svc, "_create_seed_profile", AsyncMock(side_effect=_mk_profile)
        ):
            result = await svc.seed_kuaiai_agent_scenes_on_lifecycle(TENANT)

        assert result["created"] == 3
        assert set(created_templates) == NEW_TEMPLATE_KEYS
        assert {s["instance_key"] for s in created_scenes} == NEW_TEMPLATE_KEYS
        assert all(s["origin"] == "system_seed" for s in created_scenes)
        assert all(s["created_by"] == 0 for s in created_scenes)
        assert all(s["created_by_name"] == "系统" for s in created_scenes)
        # 既有 6 模板未重建档案（只为缺失模板建档）
        assert not set(created_templates) & set(existing_keys)

    async def test_new_tenant_nine_disabled_profiles(self):
        """新租户：9 实例 + 9 份停用、空授权、只读 Tool 预置档案。"""
        profile_payloads = []
        created_scenes = []

        async def _create_profile(tenant_id, user, payload):
            profile_payloads.append(payload)
            return _profile(id=50 + len(profile_payloads), name=payload.name)

        async def _mk_scene(**kwargs):
            created_scenes.append(kwargs)
            return _scene(instance_key=kwargs["instance_key"])

        with patch.object(
            KuaiaiAgentScene, "filter", MagicMock(return_value=_qs([], count=9))
        ), patch.object(
            KuaiaiAgentScene, "get_or_none", AsyncMock(return_value=None)
        ), patch.object(
            svc.KuaiaiAgentProfile, "get_or_none", AsyncMock(return_value=None)
        ), patch.object(
            svc.agent_service,
            "create_profile",
            AsyncMock(side_effect=_create_profile),
        ), patch.object(
            KuaiaiAgentScene, "create", AsyncMock(side_effect=_mk_scene)
        ), patch(
            "apps.kuaiai.services.agent_scene_service.in_transaction", _tx()
        ):
            result = await svc.seed_kuaiai_agent_scenes_on_lifecycle(TENANT)

        assert result["created"] == 9
        assert len(created_scenes) == 9
        assert {s["instance_key"] for s in created_scenes} == set(
            svc.TEMPLATE_KEYS
        )
        template_by_key = {t.key: t for t in svc.SCENE_TEMPLATES}
        # 档案载荷顺序与缺失模板遍历一致：逐一对照模板 readonly_tools
        created_keys = [s["instance_key"] for s in created_scenes]
        for key, payload in zip(created_keys, profile_payloads):
            template = template_by_key[key]
            assert payload.status == "停用"
            assert payload.grant_mode == "ROLE"
            assert payload.default_model_id is None
            assert payload.mcp_server_ids == []
            assert payload.enabled_tools == list(template.readonly_tools)
            assert not set(payload.enabled_tools) & WRITE_TOOL_NAMES


# ============================================================ 路由与可用性


@pytest.mark.asyncio
class TestSceneRoutes:
    async def test_new_route_permission_mapping(self):
        assert (
            svc.SCENE_ROUTE_PERMISSIONS[
                "/apps/kuaizhizao/production-execution/reports/production-daily"
            ]
            == "kuaizhizao:production-execution-reports-production-daily:read"
        )
        assert (
            svc.SCENE_ROUTE_PERMISSIONS[
                "/apps/kuaizhizao/sales-management/sales-orders"
            ]
            == "kuaizhizao:sales-order:read"
        )
        assert (
            svc.SCENE_ROUTE_PERMISSIONS["/apps/master-data/process/sop"]
            == "master-data:process:sop:read"
        )

    async def test_scene_unavailable_without_route_permission(self):
        for key in NEW_TEMPLATE_KEYS:
            template = _TEMPLATE_MAP[key]
            assert svc._route_available(template.scene_route, {}) is False
            code = svc.SCENE_ROUTE_PERMISSIONS[template.scene_route]
            assert (
                svc._route_available(template.scene_route, {code: True})
                is True
            )


# ============================================================ 设置页后端驱动


@pytest.mark.asyncio
class TestSettingsAgentTemplates:
    async def test_get_returns_agent_templates_in_order(self):
        site = _site({})
        with _patch_get_settings(site), patch.object(
            IntegrationConfig, "filter", _conn_filter([])
        ), patch(
            "core.utils.integration_settings._load_llm_connection",
            AsyncMock(return_value=None),
        ):
            out = await settings_service.get_settings(TENANT)

        templates = out["agent_templates"]
        assert [t["key"] for t in templates] == [
            t.key for t in svc.SCENE_TEMPLATES
        ]
        assert len(templates) == 9
        assert all(set(t.keys()) == {"key", "name"} for t in templates)
        names = {t["key"]: t["name"] for t in templates}
        assert names["shift-lead"] == "班组长助手"
        assert names["order-delivery"] == "订单交期助手"
        assert names["work-instruction"] == "作业指导助手"
        # 开关键集与模板一致（9 键）
        assert set(out["agent_switches"].keys()) == set(svc.TEMPLATE_KEYS)

    async def test_nine_key_switches_save(self):
        kuaiai = {"active_chat_connection_uuid": "old-chat"}
        site = _site({"integrations": {"kuaiai": kuaiai}})
        chat = _conn(CHAT_UUID, "chat")
        vision = _conn(VISION_UUID, "vision")
        payload = _payload_obj(version=settings_service._version_of(site))
        with _patch_get_settings(site), patch.object(
            IntegrationConfig, "filter", _conn_filter([chat, vision])
        ), patch.object(
            SiteSetting, "filter", MagicMock(return_value=_qs([site]))
        ), patch(
            "apps.kuaiai.services.settings_service.in_transaction", _tx()
        ), patch(
            "core.ai.runtime.model_factory.evict_model_cache", MagicMock()
        ), patch.object(
            settings_service,
            "get_settings",
            AsyncMock(return_value={"ok": True}),
        ):
            await settings_service.update_settings(TENANT, _user(), payload)
        saved = site.settings["integrations"]["kuaiai"]["agent_switches"]
        assert set(saved.keys()) == set(svc.TEMPLATE_KEYS)
        assert len(saved) == 9

    async def test_missing_template_key_422(self):
        site = _site({})
        chat = _conn(CHAT_UUID, "chat")
        vision = _conn(VISION_UUID, "vision")
        switches = {t.key: True for t in svc.SCENE_TEMPLATES}
        switches.pop("shift-lead")
        payload = _payload_obj()
        payload.agent_switches = switches
        with patch.object(
            IntegrationConfig, "filter", _conn_filter([chat, vision])
        ), _patch_get_settings(site):
            with pytest.raises(ValidationError):
                await settings_service.update_settings(
                    TENANT, _user(), payload
                )
        site.save.assert_not_awaited()


# ============================================================ 能力绑定默认解析


class TestCapabilityBindingDefault:
    def test_new_templates_resolve_same_key_preset(self):
        for key in NEW_TEMPLATE_KEYS:
            assert (
                resolve_capability_binding({}, key, {key, "other"})
                == key
            )

    def test_new_templates_unbound_when_instance_missing(self):
        for key in NEW_TEMPLATE_KEYS:
            assert resolve_capability_binding({}, key, set()) is None
