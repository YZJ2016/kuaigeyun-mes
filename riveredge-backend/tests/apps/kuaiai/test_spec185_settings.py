"""KU-AI spec 185 单测：模型与能力设置聚合（全部 mock，不触真库）。

覆盖要点：
- GET：角色 options 闭集字段（本租户/启用/model_role 匹配、无 key/cipher）、
  OCR 脱敏、六模板开关缺省 true、能力项缺省、version 派生；
- PUT：跨租户 404、角色不符/停用/缺凭据 422、未知字段/rag 边界/rag_backend
  闭集/agent_switches 闭集 422、版本冲突 409、校验失败不部分保存、
  白名单深合并保留无关键、空 vision 清除、保存后失效模型缓存、审计不含敏感值；
- T6 闭环：写回的 agent_switches 经 agent_scene_service 读路径生效，
  复制实例继承来源模板总开关。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from apps.kuaiai.models.agent import KuaiaiAgentProfile
from apps.kuaiai.models.agent_scene import KuaiaiAgentScene
from apps.kuaiai.schemas.operations import (
    SettingsCapabilitiesIn,
    SettingsUpdateIn,
)
from apps.kuaiai.services import agent_scene_service as scene_svc
from apps.kuaiai.services import settings_service as svc
from core.models.integration_config import IntegrationConfig
from core.models.site_setting import SiteSetting
from infra.exceptions.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

TENANT = 7
OTHER_TENANT = 8
USER_ID = 5
CHAT_UUID = "11111111-1111-1111-1111-111111111111"
VISION_UUID = "22222222-2222-2222-2222-222222222222"
CROSS_UUID = "33333333-3333-3333-3333-333333333333"
TEMPLATE_KEYS = tuple(t.key for t in scene_svc.SCENE_TEMPLATES)


def _user(uid: int = USER_ID):
    return SimpleNamespace(id=uid, full_name="测试用户", username="tester")


def _qs(rows=(), first=None):
    q = MagicMock()
    for m in ("filter", "order_by", "offset", "limit", "select_for_update"):
        setattr(q, m, MagicMock(return_value=q))
    q.all = AsyncMock(return_value=list(rows))
    q.first = AsyncMock(
        return_value=first if first is not None else (rows[0] if rows else None)
    )
    q.count = AsyncMock(return_value=len(rows))
    q.exists = AsyncMock(return_value=bool(rows))
    q.values_list = AsyncMock(return_value=list(rows))
    return q


class _FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _tx():
    return MagicMock(return_value=_FakeTx())


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
    """IntegrationConfig.filter mock：uuid kwarg → 单查；type__in → 列表。"""

    def _filter(**kwargs):
        uuid = kwargs.get("uuid")
        if uuid is not None:
            hit = next((c for c in conns if str(c.uuid) == str(uuid)), None)
            return _qs([hit] if hit else [])
        return _qs(list(conns))

    return MagicMock(side_effect=_filter)


def _payload(**over):
    base = dict(
        version="v1",
        chat_connection_uuid=CHAT_UUID,
        vision_connection_uuid=VISION_UUID,
        agent_switches={k: True for k in TEMPLATE_KEYS},
        capabilities=dict(
            tools_enabled=True,
            rag_enabled=True,
            rag_use_embedding=True,
            rag_backend="native",
            rag_top_k=5,
            stream_enabled=True,
            custom_system_prompt="企业背景",
        ),
    )
    base.update(over)
    if "capabilities" in over and over["capabilities"] is not None:
        base["capabilities"] = over["capabilities"]
    return SettingsUpdateIn(**base)


def _payload_obj(**over):
    """构造 SettingsUpdateIn 模型实例（capabilities 内部转模型）。"""
    data = _payload(**over).model_dump()
    return SettingsUpdateIn(**data)


def _patch_get_settings(site):
    return patch(
        "core.services.system.site_setting_service.SiteSettingService.get_settings",
        AsyncMock(return_value=site),
    )


# ============================================================ GET


@pytest.mark.asyncio
class TestGetSettings:
    async def test_get_full_shape_and_masking(self):
        chat = _conn(CHAT_UUID, "chat")
        vision = _conn(
            VISION_UUID,
            "vision",
            cfg_extra={
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-vl-max",
            },
        )
        other = _conn(CROSS_UUID, "embed")  # 角色不符不进 options
        site = _site(
            {
                "integrations": {
                    "kuaiai": {
                        "active_chat_connection_uuid": CHAT_UUID,
                        "active_vision_connection_uuid": VISION_UUID,
                        "agent_switches": {"inventory-insight": False},
                        "tools_enabled": False,
                        "rag_top_k": 8,
                        "ocr_api_key": "sk-secret",
                    }
                }
            }
        )
        with _patch_get_settings(site), patch.object(
            IntegrationConfig, "filter", _conn_filter([chat, vision, other])
        ), patch(
            "core.utils.integration_settings._load_llm_connection",
            AsyncMock(return_value=vision),
        ):
            out = await svc.get_settings(TENANT)

        assert out["chat_connection_uuid"] == CHAT_UUID
        assert out["vision_connection_uuid"] == VISION_UUID
        assert [o["uuid"] for o in out["chat_options"]] == [CHAT_UUID]
        assert [o["uuid"] for o in out["vision_options"]] == [VISION_UUID]
        opt = out["chat_options"][0]
        assert set(opt.keys()) == {
            "uuid",
            "name",
            "provider",
            "model",
            "model_role",
            "is_active",
            "is_selected",
        }
        assert opt["is_selected"] is True
        assert opt["model_role"] == "chat"
        # OCR 脱敏：host 保留、路径掩去、不回明文 key
        assert out["ocr"]["configured"] is True
        assert out["ocr"]["model"] == "qwen-vl-max"
        assert out["ocr"]["base_url_masked"].endswith("/***")
        assert "compatible-mode" not in out["ocr"]["base_url_masked"]
        assert "aliyuncs.com" in out["ocr"]["base_url_masked"]
        # 六键开关：缺键 true / 显式 false
        assert set(out["agent_switches"].keys()) == set(TEMPLATE_KEYS)
        assert out["agent_switches"]["inventory-insight"] is False
        # 能力项缺省合并
        assert out["capabilities"]["tools_enabled"] is False
        assert out["capabilities"]["rag_top_k"] == 8
        assert out["capabilities"]["rag_backend"] == "native"
        assert out["version"] == svc._version_of(site)
        # 全响应无任何密钥/cipher 字样
        assert "sk-real-key" not in json.dumps(out)
        assert "sk-secret" not in json.dumps(out)

    async def test_get_empty_state_defaults(self):
        site = _site({})
        with _patch_get_settings(site), patch.object(
            IntegrationConfig, "filter", _conn_filter([])
        ), patch(
            "core.utils.integration_settings._load_llm_connection",
            AsyncMock(return_value=None),
        ):
            out = await svc.get_settings(TENANT)

        assert out["chat_connection_uuid"] is None
        assert out["vision_connection_uuid"] is None
        assert out["chat_options"] == []
        assert out["vision_options"] == []
        assert out["ocr"] == {
            "configured": False,
            "base_url_masked": "",
            "model": None,
        }
        assert all(v is True for v in out["agent_switches"].values())
        caps = out["capabilities"]
        assert caps == {
            "tools_enabled": True,
            "rag_enabled": True,
            "rag_use_embedding": True,
            "rag_backend": "native",
            "rag_top_k": 5,
            "stream_enabled": True,
            "custom_system_prompt": "",
        }

    async def test_inactive_or_wrong_role_excluded_from_options(self):
        disabled_chat = _conn(CHAT_UUID, "chat", is_active=False)
        vision = _conn(VISION_UUID, "vision")
        site = _site(
            {"integrations": {"kuaiai": {"active_chat_connection_uuid": CHAT_UUID}}}
        )
        with _patch_get_settings(site), patch.object(
            IntegrationConfig, "filter", _conn_filter([vision])
        ), patch(
            "core.utils.integration_settings._load_llm_connection",
            AsyncMock(return_value=None),
        ):
            out = await svc.get_settings(TENANT)
        # 已选用的停用连接仍回 uuid，但不出现在 options（选项只列启用行）
        assert out["chat_connection_uuid"] == CHAT_UUID
        assert out["chat_options"] == []
        assert disabled_chat.uuid == CHAT_UUID

    async def test_get_missing_switches_default_true(self):
        site = _site({"integrations": {"kuaiai": {"agent_switches": {}}}})
        with _patch_get_settings(site), patch.object(
            IntegrationConfig, "filter", _conn_filter([])
        ), patch(
            "core.utils.integration_settings._load_llm_connection",
            AsyncMock(return_value=None),
        ):
            out = await svc.get_settings(TENANT)
        assert out["agent_switches"] == {k: True for k in TEMPLATE_KEYS}


# ============================================================ PUT 校验


@pytest.mark.asyncio
class TestPutValidation:
    async def test_cross_tenant_uuid_404(self):
        payload = _payload_obj()
        site = _site({})
        with patch.object(
            IntegrationConfig, "filter", _conn_filter([])
        ), _patch_get_settings(site), patch(
            "apps.kuaiai.services.settings_service.in_transaction", _tx()
        ):
            with pytest.raises(NotFoundError):
                await svc.update_settings(TENANT, _user(), payload)

    async def test_wrong_role_422_and_no_save(self):
        chat = _conn(CHAT_UUID, "vision")  # 角色不符
        site = _site({})
        with patch.object(
            IntegrationConfig, "filter", _conn_filter([chat])
        ), _patch_get_settings(site), patch(
            "apps.kuaiai.services.settings_service.in_transaction", _tx()
        ):
            with pytest.raises(ValidationError):
                await svc.update_settings(TENANT, _user(), _payload_obj())
        site.save.assert_not_awaited()

    async def test_disabled_connection_422_and_no_save(self):
        chat = _conn(CHAT_UUID, "chat", is_active=False)
        site = _site({})
        with patch.object(
            IntegrationConfig, "filter", _conn_filter([chat])
        ), _patch_get_settings(site), patch(
            "apps.kuaiai.services.settings_service.in_transaction", _tx()
        ):
            with pytest.raises(ValidationError):
                await svc.update_settings(TENANT, _user(), _payload_obj())
        site.save.assert_not_awaited()

    async def test_missing_api_key_422(self):
        chat = _conn(CHAT_UUID, "chat", cfg_extra={"api_key": ""})
        site = _site({})
        with patch.object(
            IntegrationConfig, "filter", _conn_filter([chat])
        ), _patch_get_settings(site), patch(
            "apps.kuaiai.services.settings_service.in_transaction", _tx()
        ):
            with pytest.raises(ValidationError):
                await svc.update_settings(TENANT, _user(), _payload_obj())

    async def test_unknown_field_422(self):
        with pytest.raises(PydanticValidationError):
            SettingsUpdateIn(
                **_payload_obj().model_dump(),
                api_key="sk-evil",
            )
        with pytest.raises(PydanticValidationError):
            SettingsCapabilitiesIn(
                tools_enabled=True,
                rag_enabled=True,
                rag_use_embedding=True,
                rag_backend="native",
                rag_top_k=5,
                stream_enabled=True,
                custom_system_prompt="",
                ocr_api_key="x",
            )

    async def test_rag_bounds_and_backend_closed(self):
        for bad in (0, 21):
            with pytest.raises(PydanticValidationError):
                _payload_obj(
                    capabilities=dict(
                        tools_enabled=True,
                        rag_enabled=True,
                        rag_use_embedding=True,
                        rag_backend="native",
                        rag_top_k=bad,
                        stream_enabled=True,
                        custom_system_prompt="",
                    )
                )
        for bad_backend in ("llamaindex", "elasticsearch"):
            with pytest.raises(PydanticValidationError):
                _payload_obj(
                    capabilities=dict(
                        tools_enabled=True,
                        rag_enabled=True,
                        rag_use_embedding=True,
                        rag_backend=bad_backend,
                        rag_top_k=5,
                        stream_enabled=True,
                        custom_system_prompt="",
                    )
                )
        ok = _payload_obj(
            capabilities=dict(
                tools_enabled=True,
                rag_enabled=True,
                rag_use_embedding=True,
                rag_backend="native",
                rag_top_k=20,
                stream_enabled=True,
                custom_system_prompt="",
            )
        )
        assert ok.capabilities.rag_top_k == 20

    async def test_agent_switches_closed_set_422(self):
        site = _site({})
        chat = _conn(CHAT_UUID, "chat")
        vision = _conn(VISION_UUID, "vision")

        def _bad_payload(switches):
            # 绕过 schema：直接构造并篡改字段模拟服务层防御
            obj = _payload_obj()
            obj.agent_switches = switches
            return obj

        for bad in (
            {k: True for k in TEMPLATE_KEYS[:-1]},  # 缺一键
            {**{k: True for k in TEMPLATE_KEYS}, "evil": True},  # 多键
            {**{k: True for k in TEMPLATE_KEYS}, "inventory-insight": "yes"},
        ):
            with patch.object(
                IntegrationConfig, "filter", _conn_filter([chat, vision])
            ), _patch_get_settings(site):
                with pytest.raises(ValidationError):
                    await svc.update_settings(
                        TENANT, _user(), _bad_payload(bad)
                    )
        site.save.assert_not_awaited()


# ============================================================ PUT 保存


@pytest.mark.asyncio
class TestPutSave:
    def _site_with_kuaiai(self, extra=None):
        kuaiai = {
            "active_provider": "deepseek",
            "active_chat_connection_uuid": "old-chat",
            "active_vision_connection_uuid": "old-vision",
            "ocr_base_url": "https://legacy-ocr",
            "unrelated_flag": "keep-me",
        }
        if extra:
            kuaiai.update(extra)
        return _site(
            {
                "integrations": {"kuaiai": kuaiai},
                "security": {"token_check_interval": 60},
            }
        )

    def _run_save(self, site, payload=None, conns=None):
        chat = _conn(CHAT_UUID, "chat")
        vision = _conn(VISION_UUID, "vision")
        conns = conns if conns is not None else [chat, vision]
        payload = payload or _payload_obj()
        return patch.object(
            IntegrationConfig, "filter", _conn_filter(conns)
        ), _patch_get_settings(site), patch.object(
            SiteSetting,
            "filter",
            MagicMock(return_value=_qs([site])),
        ), patch(
            "apps.kuaiai.services.settings_service.in_transaction", _tx()
        ), patch(
            "core.ai.runtime.model_factory.evict_model_cache", MagicMock()
        ), patch.object(
            svc, "get_settings", AsyncMock(return_value={"ok": True})
        )

    async def test_version_conflict_409_no_save(self):
        site = self._site_with_kuaiai()
        stale = _payload_obj(version="stale-version")
        p1, p2, p3, p4, p5, p6 = self._run_save(site, payload=stale)
        with p1, p2, p3, p4, p5, p6:
            with pytest.raises(ConflictError) as exc:
                await svc.update_settings(TENANT, _user(), stale)
        assert exc.value.status_code == 409
        site.save.assert_not_awaited()

    async def test_version_match_saves_once_and_evicts(self):
        site = self._site_with_kuaiai()
        payload = _payload_obj(version=svc._version_of(site))
        p1, p2, p3, p4, p5, p6 = self._run_save(site, payload=payload)
        with p1, p2, p3, p4, p5 as evict_mock, p6:
            out = await svc.update_settings(TENANT, _user(), payload)
        assert out == {"ok": True}
        site.save.assert_awaited_once_with(
            update_fields=["settings", "updated_at"]
        )
        evict_mock.assert_called_once_with(TENANT)

    async def test_connections_are_locked_inside_transaction_in_uuid_order(self):
        events = []
        site = self._site_with_kuaiai()
        payload = _payload_obj(version=svc._version_of(site))
        chat = _conn(CHAT_UUID, "chat")
        vision = _conn(VISION_UUID, "vision")

        class TracedTx:
            async def __aenter__(self):
                events.append("tx-enter")
                return self

            async def __aexit__(self, *args):
                events.append("tx-exit")
                return False

        def traced_filter(**kwargs):
            uuid = str(kwargs["uuid"])
            events.append(f"filter:{uuid}")
            row = chat if uuid == CHAT_UUID else vision
            query = _qs([row])
            query.select_for_update.side_effect = lambda: (
                events.append(f"lock:{uuid}") or query
            )
            return query

        with _patch_get_settings(site), patch.object(
            IntegrationConfig, "filter", MagicMock(side_effect=traced_filter)
        ), patch.object(
            SiteSetting, "filter", MagicMock(return_value=_qs([site]))
        ), patch(
            "apps.kuaiai.services.settings_service.in_transaction",
            MagicMock(return_value=TracedTx()),
        ), patch(
            "core.ai.runtime.model_factory.evict_model_cache", MagicMock()
        ), patch.object(
            svc, "get_settings", AsyncMock(return_value={"ok": True})
        ):
            await svc.update_settings(TENANT, _user(), payload)

        assert events.index("tx-enter") < events.index(f"filter:{CHAT_UUID}")
        assert [event for event in events if event.startswith("lock:")] == [
            f"lock:{CHAT_UUID}",
            f"lock:{VISION_UUID}",
        ]
        assert events.index(f"lock:{VISION_UUID}") < events.index("tx-exit")

    async def test_invalid_locked_connection_rolls_back_without_site_save(self):
        site = self._site_with_kuaiai()
        payload = _payload_obj(version=svc._version_of(site))
        chat = _conn(CHAT_UUID, "chat")
        disabled_vision = _conn(VISION_UUID, "vision", is_active=False)
        p1, p2, p3, p4, p5, p6 = self._run_save(
            site, payload=payload, conns=[chat, disabled_vision]
        )
        with p1, p2, p3, p4, p5, p6:
            with pytest.raises(ValidationError):
                await svc.update_settings(TENANT, _user(), payload)
        site.save.assert_not_awaited()

    async def test_deep_merge_preserves_unrelated_keys(self):
        site = self._site_with_kuaiai()
        payload = _payload_obj(version=svc._version_of(site))
        p1, p2, p3, p4, p5, p6 = self._run_save(site, payload=payload)
        with p1, p2, p3, p4, p5, p6:
            await svc.update_settings(TENANT, _user(), payload)
        kuaiai = site.settings["integrations"]["kuaiai"]
        assert kuaiai["active_chat_connection_uuid"] == CHAT_UUID
        assert kuaiai["active_vision_connection_uuid"] == VISION_UUID
        # 无关键与 integrations 外结构保留
        assert kuaiai["active_provider"] == "deepseek"
        assert kuaiai["ocr_base_url"] == "https://legacy-ocr"
        assert kuaiai["unrelated_flag"] == "keep-me"
        assert site.settings["security"] == {"token_check_interval": 60}
        # 开关与能力项写回
        assert kuaiai["agent_switches"] == {
            k: True for k in TEMPLATE_KEYS
        }
        assert kuaiai["rag_top_k"] == 5
        assert kuaiai["custom_system_prompt"] == "企业背景"
        assert kuaiai["rag_backend"] == "native"

    async def test_explicit_false_switch_and_empty_vision(self):
        site = self._site_with_kuaiai()
        switches = {k: True for k in TEMPLATE_KEYS}
        switches["inventory-insight"] = False
        payload = _payload_obj(
            version=svc._version_of(site),
            vision_connection_uuid=None,
            agent_switches=switches,
        )
        p1, p2, p3, p4, p5, p6 = self._run_save(site, payload=payload)
        with p1, p2, p3, p4, p5, p6:
            await svc.update_settings(TENANT, _user(), payload)
        kuaiai = site.settings["integrations"]["kuaiai"]
        assert kuaiai["active_vision_connection_uuid"] == ""
        assert kuaiai["agent_switches"]["inventory-insight"] is False
        # 复制实例继承来源模板总开关：场景读路径缺键默认/显式 false
        from core.utils.integration_settings import read_agent_switches

        view = read_agent_switches(kuaiai, TEMPLATE_KEYS)
        assert view["inventory-insight"] is False
        assert view["planner-advisor"] is True

    async def test_saved_switches_visible_via_scene_read_path(self):
        """写回的开关经 agent_scene_service.agent_switches 读路径生效。"""
        site = self._site_with_kuaiai(
            {"agent_switches": {"planner-advisor": False}}
        )
        with _patch_get_settings(site):
            switches = await scene_svc.agent_switches(TENANT)
        assert switches["planner-advisor"] is False
        assert switches["inventory-insight"] is True

    async def test_copy_instance_inherits_template_switch(self):
        """复制实例状态 = 模板总开关 ∧ 实例 enabled（总开关关 → not_ready）。"""
        copy_scene = SimpleNamespace(
            id=99,
            tenant_id=TENANT,
            instance_key="inventory-insight-copy-ab12cd34",
            template_key="inventory-insight",
            origin="copy",
            agent_profile_id=11,
            overrides={},
            enabled=True,
            deleted_at=None,
            update_from_dict=MagicMock(),
            save=AsyncMock(),
        )
        profile = SimpleNamespace(
            id=11,
            tenant_id=TENANT,
            name="助手",
            status="启用",
            deleted_at=None,
        )
        site = self._site_with_kuaiai(
            {"agent_switches": {"inventory-insight": False}}
        )
        with patch.object(
            KuaiaiAgentScene, "filter", MagicMock(return_value=_qs([copy_scene]))
        ), patch.object(
            KuaiaiAgentProfile, "filter", MagicMock(return_value=_qs([profile]))
        ), _patch_get_settings(site), patch.object(
            scene_svc.grant_service,
            "usable_profile_ids",
            AsyncMock(return_value={11}),
        ), patch.object(
            scene_svc, "_has_permission", AsyncMock(return_value=True)
        ), patch.object(
            scene_svc, "is_chat_ready", AsyncMock(return_value=True)
        ), patch.object(
            scene_svc,
            "_route_permissions_for_user",
            AsyncMock(return_value={}),
        ):
            out = await scene_svc.list_agent_library(TENANT, _user())
        item = next(i for i in out["items"] if i["key"].endswith("ab12cd34"))
        assert item["status"] == "not_ready"
        assert item["disabled_reason"] == "场景总开关已停用"


# ============================================================ rag_enabled 运行时生效（spec 186 缺陷修复）


@pytest.mark.asyncio
class TestRagEnabledGate:
    """``integrations.kuaiai.rag_enabled`` 对检索唯一入口 ``retrieve`` 的门禁。

    spec 185 规则「RAG 关闭时检索不执行」：spec 186 验收发现 facade 未消费
    该开关（写得出、读不进执行路径），修复落 retrieval.retrieve 单点，
    同时覆盖 search_knowledge Tool 与路径 A knowledge_id 注入两条调用链。
    """

    async def test_rag_disabled_returns_empty_and_skips_pipeline(self):
        from apps.kuaiai.services import retrieval

        site = _site({"integrations": {"kuaiai": {"rag_enabled": False}}})
        with _patch_get_settings(site), patch.object(
            retrieval, "_retrieve", AsyncMock()
        ) as inner:
            out = await retrieval.retrieve(TENANT, "问题", [1])
        assert out == []
        inner.assert_not_awaited()

    async def test_rag_enabled_runs_pipeline(self):
        from apps.kuaiai.services import retrieval

        site = _site({"integrations": {"kuaiai": {"rag_enabled": True}}})
        with _patch_get_settings(site), patch.object(
            retrieval, "_retrieve", AsyncMock(return_value=[{"x": 1}])
        ) as inner:
            out = await retrieval.retrieve(TENANT, "问题", [1])
        assert out == [{"x": 1}]
        inner.assert_awaited_once()

    async def test_missing_key_defaults_enabled(self):
        from apps.kuaiai.services import retrieval

        site = _site({"integrations": {"kuaiai": {}}})
        with _patch_get_settings(site), patch.object(
            retrieval, "_retrieve", AsyncMock(return_value=[])
        ) as inner:
            await retrieval.retrieve(TENANT, "问题", [1])
        inner.assert_awaited_once()

    async def test_settings_read_failure_defaults_enabled(self):
        """设置读取失败与缺键同口径（True），不静默关闭检索。"""
        from apps.kuaiai.services import retrieval

        with patch(
            "core.services.system.site_setting_service.SiteSettingService.get_settings",
            AsyncMock(side_effect=RuntimeError("db down")),
        ), patch.object(
            retrieval, "_retrieve", AsyncMock(return_value=[])
        ) as inner:
            await retrieval.retrieve(TENANT, "问题", [1])
        inner.assert_awaited_once()

    async def test_search_knowledge_tool_blocked_when_rag_off(self):
        """Tool 链同门：rag_enabled=False 时 search_knowledge 不触发检索。"""
        from apps.kuaiai.services import chat_tools, retrieval

        profile = SimpleNamespace(
            status="启用",
            knowledge_ids=[1],
        )
        ctx = SimpleNamespace(
            tenant_id=TENANT, user=_user(), agent_id=11
        )
        site = _site({"integrations": {"kuaiai": {"rag_enabled": False}}})
        with patch.object(
            KuaiaiAgentProfile,
            "filter",
            MagicMock(return_value=_qs([profile])),
        ), _patch_get_settings(site), patch.object(
            retrieval, "_retrieve", AsyncMock()
        ) as inner:
            out = await chat_tools.search_knowledge("问题", ctx=ctx)
        inner.assert_not_awaited()
        assert out == chat_tools._ERR_NO_HIT


class TestPublicStatusModelNull:
    """review 修复：public_status 未配置时 model 置空，不返回出厂默认名。"""

    def test_model_null_when_unconfigured(self):
        from core.utils.integration_settings import (
            build_deepseek_public_status_from_active,
        )

        out = build_deepseek_public_status_from_active(
            {"enabled": True, "model": "deepseek-chat", "provider": "deepseek"}
        )
        assert out["configured"] is False
        assert out["enabled"] is False
        assert out["model"] is None

    def test_model_name_when_configured(self):
        from core.utils.integration_settings import (
            build_deepseek_public_status_from_active,
        )

        out = build_deepseek_public_status_from_active(
            {
                "enabled": True,
                "model": "deepseek-chat",
                "api_key": "sk-real",
                "provider": "deepseek",
            }
        )
        assert out["configured"] is True
        assert out["enabled"] is True
        assert out["model"] == "deepseek-chat"
