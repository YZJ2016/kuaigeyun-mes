"""KU-AI spec 222 单测：场景分类闭集 + hub 下发 category（全部 mock，不触真库）。

覆盖要点：
- SCENE_CATEGORIES 闭集恰好九类；每个出厂模板 category ∈ 闭集；
  SceneTemplate(category=闭集外值) 构造即拒绝（Z1=a）；
- hub capabilities[]：ask 卡 category=None；场景卡逐模板下发模板分类；
  解绑/预置缺失/聚合失败的占位卡同样下发模板分类；
- 实例 overrides.category 合法闭集值覆盖模板分类下发；闭集外值回落
  模板分类（与 _merged_fields 同闭集语义）；
- SCENE_OVERRIDE_KEYS 放行 category + _validate_override_fields 闭集校验
  （集成阶段已在 agent_scene_service.py 落地）。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.models.agent import KuaiaiAgentProfile
from apps.kuaiai.models.agent_scene import KuaiaiAgentScene
from apps.kuaiai.schemas.operations import HubCapabilityOut
from apps.kuaiai.services import agent_scene_service as scene_svc
from apps.kuaiai.services import operations_service as ops_svc
from apps.kuaiai.services import tool_catalog_service
from infra.exceptions.exceptions import BusinessLogicError

TENANT = 7
USER_ID = 5
TEMPLATE_KEYS = tuple(t.key for t in scene_svc.SCENE_TEMPLATES)
TEMPLATE_MAP = {t.key: t for t in scene_svc.SCENE_TEMPLATES}
FIRST = TEMPLATE_KEYS[0]  # inventory-insight

EXPECTED_CATEGORIES = frozenset(
    {
        "plan",
        "production",
        "quality",
        "inventory",
        "purchase",
        "equipment",
        "engineering",
        "management",
        "general",
    }
)


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
        MagicMock(return_value=_catalog()),
    ):
        return await ops_svc._build_capabilities(
            TENANT, {"configured": chat, "enabled": chat}, _user()
        )


def _card(caps, key):
    return next(c for c in caps if c["key"] == key)


def _preset_scene_set(**kw):
    """逐模板预置实例 + 各自启用档案（id=11..），首个可 kw 覆盖。"""
    scenes, profiles = [], []
    for i, key in enumerate(TEMPLATE_KEYS):
        pid = 11 + i
        scene_kw = dict(kw) if i == 0 else {}
        scene_kw.setdefault("agent_profile_id", pid)
        scenes.append(_scene(key, id=i + 1, **scene_kw))
        profiles.append(_profile(id=pid))
    return scenes, profiles


# ============================================================ 分类闭集


class TestCategoryClosedSet:
    def test_scene_categories_exact_nine(self):
        assert scene_svc.SCENE_CATEGORIES == EXPECTED_CATEGORIES

    def test_every_template_category_in_closed_set(self):
        for template in scene_svc.SCENE_TEMPLATES:
            assert template.category in scene_svc.SCENE_CATEGORIES, (
                f"{template.key} category={template.category}"
            )

    def test_template_rejects_unknown_category(self):
        with pytest.raises(ValueError):
            scene_svc.SceneTemplate(
                key="bad-category-tpl",
                name="坏分类",
                description="desc",
                image_key="x",
                capability_tags=(),
                sample_prompt="p",
                scene_route=None,
                system_prompt="",
                readonly_tools=(),
                category="bogus",
            )

    def test_template_category_default_is_general(self):
        template = scene_svc.SceneTemplate(
            key="no-category-tpl",
            name="未分类",
            description="desc",
            image_key="x",
            capability_tags=(),
            sample_prompt="p",
            scene_route=None,
            system_prompt="",
            readonly_tools=(),
        )
        assert template.category == "general"


# ============================================================ hub 下发


@pytest.mark.asyncio
class TestHubCategoryDownlink:
    async def test_scene_cards_carry_template_category(self):
        scenes, profiles = _preset_scene_set()
        caps = await _caps(scenes, profiles)
        for card in caps:
            if card["key"] == "ask":
                assert card.get("category") is None
            else:
                assert card["category"] == TEMPLATE_MAP[card["key"]].category

    async def test_unbound_placeholder_keeps_template_category(self):
        scenes, profiles = _preset_scene_set()
        caps = await _caps(
            scenes,
            profiles,
            kuaiai={"capability_bindings": {FIRST: None}},
        )
        card = _card(caps, FIRST)
        assert card["status"] == "not_ready"
        assert card["category"] == TEMPLATE_MAP[FIRST].category

    async def test_missing_preset_keeps_template_category(self):
        scenes, profiles = _preset_scene_set()
        caps = await _caps(scenes[1:], profiles[1:])
        card = _card(caps, FIRST)
        assert card["status"] == "not_ready"
        assert card["category"] == TEMPLATE_MAP[FIRST].category

    async def test_aggregation_failure_keeps_template_category(self):
        """场景数据源整体失败的占位卡同样下发模板分类。"""
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
        assert all(
            c["category"] == TEMPLATE_MAP[c["key"]].category
            for c in scene_cards
        )

    async def test_instance_override_category_propagates(self):
        """实例 overrides.category 合法值覆盖模板分类下发。"""
        scenes, profiles = _preset_scene_set()
        scenes[0].overrides = {"category": "management"}
        caps = await _caps(scenes, profiles)
        assert _card(caps, FIRST)["category"] == "management"

    async def test_invalid_override_category_falls_back_to_template(self):
        """闭集外覆盖值不下发，回落模板分类（写入路径校验之外的防御）。"""
        scenes, profiles = _preset_scene_set()
        scenes[0].overrides = {"category": "bogus"}
        caps = await _caps(scenes, profiles)
        assert (
            _card(caps, FIRST)["category"] == TEMPLATE_MAP[FIRST].category
        )

    async def test_copy_instance_override_category_propagates(self):
        """改绑复制实例时按该实例 overrides.category 下发。"""
        scenes, profiles = _preset_scene_set()
        copy = _scene(
            "inv-copy-1",
            id=99,
            template_key=FIRST,
            origin="copy",
            overrides={"category": "engineering"},
        )
        caps = await _caps(
            scenes + [copy],
            profiles,
            kuaiai={"capability_bindings": {FIRST: "inv-copy-1"}},
        )
        card = _card(caps, FIRST)
        assert card["scene_key"] == "inv-copy-1"
        assert card["category"] == "engineering"


# ============================================================ 解析与契约


class TestResolveCategory:
    def test_prefers_merged_fields_then_overrides_then_template(self):
        template = TEMPLATE_MAP[FIRST]
        scene = _scene(overrides={"category": "engineering"})
        # merged fields 已带合法值优先（集成后 _merged_fields 通路）
        assert (
            ops_svc._resolve_category(
                scene, template, {"category": "management"}
            )
            == "management"
        )
        # merged 值非法 → overrides 合法值
        assert (
            ops_svc._resolve_category(scene, template, {"category": "bogus"})
            == "engineering"
        )
        # 无 merged → overrides 合法值
        assert ops_svc._resolve_category(scene, template) == "engineering"
        # 无 scene（占位卡）→ 模板分类
        assert (
            ops_svc._resolve_category(None, template) == template.category
        )

    def test_schema_serializes_category(self):
        out = HubCapabilityOut(
            key="k", name="n", status="ready", category="quality"
        )
        assert out.model_dump()["category"] == "quality"
        assert (
            HubCapabilityOut(key="ask", name="n", status="ready").category
            is None
        )


# ============================================================ 实例覆盖白名单
# SCENE_OVERRIDE_KEYS 放行 category + _validate_override_fields 闭集校验。


class TestOverrideWhitelist:
    def test_override_keys_whitelist_includes_category(self):
        assert "category" in scene_svc.SCENE_OVERRIDE_KEYS

    def test_validate_override_fields_accepts_valid_category(self):
        out = scene_svc._validate_override_fields({"category": "quality"})
        assert out == {"category": "quality"}

    def test_validate_override_fields_none_clears_category(self):
        out = scene_svc._validate_override_fields({"category": None})
        assert out == {"category": None}

    def test_validate_override_fields_rejects_unknown_category(self):
        with pytest.raises(BusinessLogicError):
            scene_svc._validate_override_fields({"category": "bogus"})
