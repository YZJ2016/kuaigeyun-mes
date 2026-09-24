"""KU-AI S2 单测：模型目录 + Agent 档案/授权（数据与管理面）。

全部 mock Tortoise 查询，不需要真实数据库。覆盖：
- enabled_tools 五值闭集（未知名 400）
- grant_mode ROLE|USER 互斥，切换同事务清空对侧名单
- 启用空名单 400 / 停用允许空
- options 只回当前用户有使用权的启用档案
- 跨租户 404 / 归属复核
- api_key 不出现在响应（打码回显 + 打码回写视为保留）
- model_type 闭集校验
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.models.agent import KuaiaiAgentGrant, KuaiaiAgentProfile
from apps.kuaiai.models.catalog import KuaiaiLlmModel, KuaiaiLlmProvider
from apps.kuaiai.schemas.agent import (
    AgentProfileCreate,
    AgentProfileUpdate,
)
from apps.kuaiai.schemas.catalog import (
    LlmModelCreate,
    LlmModelUpdate,
    LlmProviderCreate,
    LlmProviderUpdate,
)
from apps.kuaiai.services import agent_service, catalog_service, grant_service
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

TENANT = 7
OTHER_TENANT = 8
USER_ID = 5


def _user(uid: int = USER_ID):
    return SimpleNamespace(id=uid, full_name="测试用户", username="tester")


def _qs(rows=(), count=None):
    """伪 QuerySet：链式方法返回自身，终端方法为 AsyncMock。"""
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
    return q


class _FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _patch_tx():
    return patch(
        "tortoise.transactions.in_transaction", MagicMock(return_value=_FakeTx())
    )


def _self_updating(ns: SimpleNamespace) -> SimpleNamespace:
    """update_from_dict 回自身并对字段生效（对齐 Tortoise Model 行为）。"""

    def _upd(data):
        ns.__dict__.update(data)
        return ns

    ns.update_from_dict = MagicMock(side_effect=_upd)
    ns.save = AsyncMock()
    return ns


def _provider(pid=1, api_key="sk-secret", tenant=TENANT):
    return _self_updating(
        SimpleNamespace(
            id=pid,
            uuid=f"uuid-p{pid}",
            tenant_id=tenant,
            code="custom-x",
            name="自定义厂商",
            base_url="https://llm.example.invalid/v1",
            api_key=api_key,
            provider_type=None,
            status="启用",
            created_at=None,
            updated_at=None,
        )
    )


def _model(mid=1, provider_id=1, mtype="chat", status="启用", tenant=TENANT):
    return _self_updating(
        SimpleNamespace(
            id=mid,
            uuid=f"uuid-m{mid}",
            tenant_id=tenant,
            provider_id=provider_id,
            model_name="my-model",
            model_type=mtype,
            status=status,
            created_at=None,
            updated_at=None,
        )
    )


def _profile(aid=1, mode="USER", status="停用", tenant=TENANT):
    return _self_updating(
        SimpleNamespace(
            id=aid,
            uuid=f"uuid-a{aid}",
            tenant_id=tenant,
            name=f"档案{aid}",
            description=None,
            system_prompt=None,
            default_model_id=None,
            knowledge_ids=[],
            enabled_tools=[],
            mcp_server_ids=[],
            status=status,
            grant_mode=mode,
        )
    )


def _grant(gid, agent_id, ttype, tid):
    return SimpleNamespace(
        id=gid, tenant_id=TENANT, agent_id=agent_id,
        target_type=ttype, target_id=tid,
    )


class TestToolClosedSet:
    @pytest.mark.asyncio
    async def test_unknown_tool_name_400(self):
        payload = AgentProfileCreate(
            name="a1", grant_mode="USER",
            enabled_tools=["search_knowledge", "drop_table"],
        )
        with patch.object(
            KuaiaiAgentProfile, "get_or_none", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(BusinessLogicError) as exc:
                await agent_service.create_profile(TENANT, _user(), payload)
        assert exc.value.status_code == 400
        assert "drop_table" in exc.value.message

    @pytest.mark.asyncio
    async def test_known_tools_accepted_and_deduped(self):
        created = {}

        async def _create(**kw):
            created.update(kw)
            return _profile()

        payload = AgentProfileCreate(
            name="a1", grant_mode="USER",
            enabled_tools=["query_workorder", "query_workorder", "search_knowledge"],
        )
        with (
            patch.object(
                KuaiaiAgentProfile, "get_or_none", new=AsyncMock(return_value=None)
            ),
            patch.object(KuaiaiAgentProfile, "create", new=AsyncMock(side_effect=_create)),
        ):
            await agent_service.create_profile(TENANT, _user(), payload)
        assert created["enabled_tools"] == ["query_workorder", "search_knowledge"]

    @pytest.mark.asyncio
    async def test_update_unknown_tool_400(self):
        profile = _profile()
        payload = AgentProfileUpdate(enabled_tools=["exec_sql"])
        with (
            patch.object(
                KuaiaiAgentProfile, "get_or_none", new=AsyncMock(return_value=profile)
            ),
            _patch_tx(),
        ):
            with pytest.raises(BusinessLogicError):
                await agent_service.update_profile(TENANT, _user(), 1, payload)
        profile.update_from_dict.assert_not_called()


class TestGrantModeExclusive:
    @pytest.mark.asyncio
    async def test_invalid_grant_mode_400(self):
        payload = AgentProfileCreate(name="a1", grant_mode="DEPT")
        with pytest.raises(BusinessLogicError):
            await agent_service.create_profile(TENANT, _user(), payload)

    @pytest.mark.asyncio
    async def test_switch_mode_clears_opposite_side(self):
        """ROLE→USER 切换：同事务软删 target_type=role 的对侧名单。"""
        profile = _profile(mode="ROLE", status="停用")
        grant_q = _qs()
        with (
            patch.object(
                KuaiaiAgentProfile, "get_or_none", new=AsyncMock(return_value=profile)
            ),
            patch.object(
                KuaiaiAgentGrant, "filter", MagicMock(return_value=grant_q)
            ) as mock_filter,
            _patch_tx(),
        ):
            await agent_service.update_profile(
                TENANT, _user(), 1, AgentProfileUpdate(grant_mode="USER")
            )
        role_calls = [
            c for c in mock_filter.call_args_list
            if c.kwargs.get("target_type") == "role"
        ]
        assert role_calls, "切换为 USER 应清空 role 侧名单"
        grant_q.update.assert_awaited()
        saved = profile.update_from_dict.call_args.args[0]
        assert saved["grant_mode"] == "USER"

    @pytest.mark.asyncio
    async def test_same_mode_no_clear(self):
        profile = _profile(mode="USER", status="停用")
        grant_q = _qs()
        with (
            patch.object(
                KuaiaiAgentProfile, "get_or_none", new=AsyncMock(return_value=profile)
            ),
            patch.object(
                KuaiaiAgentGrant, "filter", MagicMock(return_value=grant_q)
            ) as mock_filter,
            _patch_tx(),
        ):
            await agent_service.update_profile(
                TENANT, _user(), 1, AgentProfileUpdate(description="d")
            )
        assert not any(
            "target_type" in c.kwargs for c in mock_filter.call_args_list
        )


class TestEnabledEmptyGrants:
    @pytest.mark.asyncio
    async def test_create_enabled_profile_400(self):
        """新建即启用：名单必然为空 → 400。"""
        payload = AgentProfileCreate(name="a1", grant_mode="USER", status="启用")
        with patch.object(
            KuaiaiAgentProfile, "get_or_none", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(BusinessLogicError) as exc:
                await agent_service.create_profile(TENANT, _user(), payload)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_enable_with_empty_grants_400(self):
        profile = _profile(mode="USER", status="停用")
        grant_q = _qs(count=0)
        with (
            patch.object(
                KuaiaiAgentProfile, "get_or_none", new=AsyncMock(return_value=profile)
            ),
            patch.object(KuaiaiAgentGrant, "filter", MagicMock(return_value=grant_q)),
            _patch_tx(),
        ):
            with pytest.raises(BusinessLogicError) as exc:
                await agent_service.update_profile(
                    TENANT, _user(), 1, AgentProfileUpdate(status="启用")
                )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_enable_with_grants_ok(self):
        profile = _profile(mode="USER", status="停用")
        grant_q = _qs(count=1)
        with (
            patch.object(
                KuaiaiAgentProfile, "get_or_none", new=AsyncMock(return_value=profile)
            ),
            patch.object(KuaiaiAgentGrant, "filter", MagicMock(return_value=grant_q)),
            _patch_tx(),
        ):
            await agent_service.update_profile(
                TENANT, _user(), 1, AgentProfileUpdate(status="启用")
            )
        profile.update_from_dict.assert_called()

    @pytest.mark.asyncio
    async def test_disabled_allows_empty_grants(self):
        profile = _profile(mode="USER", status="停用")
        with (
            patch.object(
                KuaiaiAgentProfile, "get_or_none", new=AsyncMock(return_value=profile)
            ),
            _patch_tx(),
        ):
            await agent_service.update_profile(
                TENANT, _user(), 1, AgentProfileUpdate(description="x")
            )
        profile.update_from_dict.assert_called()

    @pytest.mark.asyncio
    async def test_replace_grants_empty_on_enabled_400(self):
        profile = _profile(mode="USER", status="启用")
        with pytest.raises(BusinessLogicError):
            await grant_service.replace_grants(TENANT, profile, [], _user())

    @pytest.mark.asyncio
    async def test_replace_grants_writes_current_mode(self):
        profile = _profile(mode="ROLE", status="停用")
        grant_q = _qs()
        created = []

        async def _create(**kw):
            created.append(kw)
            return _grant(99, kw["agent_id"], kw["target_type"], kw["target_id"])

        with (
            patch.object(KuaiaiAgentGrant, "filter", MagicMock(return_value=grant_q)),
            patch.object(KuaiaiAgentGrant, "create", new=AsyncMock(side_effect=_create)),
            _patch_tx(),
        ):
            out = await grant_service.replace_grants(
                TENANT, profile, [3, 3, 7], _user()
            )
        assert out["grant_mode"] == "ROLE"
        assert out["target_ids"] == [3, 7]
        assert all(c["target_type"] == "role" for c in created)


class TestUseGrant:
    @pytest.mark.asyncio
    async def test_user_mode_hit_and_miss(self):
        profile = _profile(mode="USER")
        hit = _qs([_grant(1, 1, "user", USER_ID)])
        with patch.object(KuaiaiAgentGrant, "filter", MagicMock(return_value=hit)):
            assert await grant_service.check_use_grant(TENANT, profile, _user()) is True
        miss = _qs([])
        with patch.object(KuaiaiAgentGrant, "filter", MagicMock(return_value=miss)):
            assert (
                await grant_service.check_use_grant(TENANT, profile, _user(99))
                is False
            )

    @pytest.mark.asyncio
    async def test_role_mode_hit_and_dangling_miss(self):
        profile = _profile(mode="ROLE")
        grant_q = _qs([_grant(1, 1, "role", 42)])
        role_q = _qs([42])
        with (
            patch.object(KuaiaiAgentGrant, "filter", MagicMock(return_value=grant_q)),
            patch(
                "core.models.user_role.UserRole.filter",
                MagicMock(return_value=role_q),
            ),
        ):
            assert await grant_service.check_use_grant(TENANT, profile, _user()) is True

        # 悬挂授权：名单里 role=999 但用户无该角色 → 不授权
        grant_q2 = _qs([])
        empty_roles = _qs([])
        with (
            patch.object(KuaiaiAgentGrant, "filter", MagicMock(return_value=grant_q2)),
            patch(
                "core.models.user_role.UserRole.filter",
                MagicMock(return_value=empty_roles),
            ),
        ):
            assert await grant_service.check_use_grant(TENANT, profile, _user()) is False

    @pytest.mark.asyncio
    async def test_fail_closed_on_empty_context(self):
        assert await grant_service.check_use_grant(
            TENANT, _profile(), SimpleNamespace(id=None)
        ) is False
        assert await grant_service.check_use_grant(
            TENANT, _profile(mode="WEIRD"), _user()
        ) is False


class TestOptionsFilter:
    @pytest.mark.asyncio
    async def test_usable_profile_ids_only_enabled_and_granted(self):
        p1 = _profile(aid=1, mode="USER", status="启用")
        p2 = _profile(aid=2, mode="ROLE", status="启用")
        p3 = _profile(aid=3, mode="USER", status="启用")  # 无授权
        p4 = _profile(aid=4, mode="USER", status="停用")  # 停用不进候选
        profiles_q = _qs([p1, p2, p3])
        grants_q = _qs(
            [
                _grant(1, 1, "user", USER_ID),
                _grant(2, 2, "role", 42),
                _grant(3, 3, "user", 999),  # 悬挂：授权他人
            ]
        )
        roles_q = _qs([42])
        with (
            patch.object(
                KuaiaiAgentProfile, "filter", MagicMock(return_value=profiles_q)
            ),
            patch.object(KuaiaiAgentGrant, "filter", MagicMock(return_value=grants_q)),
            patch(
                "core.models.user_role.UserRole.filter",
                MagicMock(return_value=roles_q),
            ),
        ):
            usable = await grant_service.usable_profile_ids(TENANT, _user())
        assert usable == {1, 2}

    @pytest.mark.asyncio
    async def test_profile_options_filters_by_usable(self):
        p1 = _profile(aid=1, status="启用")
        profiles_q = _qs([p1])
        with (
            patch.object(
                grant_service,
                "usable_profile_ids",
                new=AsyncMock(return_value={1}),
            ),
            patch.object(
                KuaiaiAgentProfile, "filter", MagicMock(return_value=profiles_q)
            ),
        ):
            items = await agent_service.profile_options(TENANT, _user())
        assert [p.id for p in items] == [1]


class TestCrossTenant:
    @pytest.mark.asyncio
    async def test_profile_cross_tenant_404(self):
        with patch.object(
            KuaiaiAgentProfile, "get_or_none", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await agent_service.get_profile(OTHER_TENANT, 1)

    @pytest.mark.asyncio
    async def test_provider_cross_tenant_404(self):
        with patch.object(
            KuaiaiLlmProvider, "get_or_none", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await catalog_service.get_provider(OTHER_TENANT, 1)

    @pytest.mark.asyncio
    async def test_model_cross_tenant_404(self):
        with patch.object(
            KuaiaiLlmModel, "get_or_none", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await catalog_service.get_model(OTHER_TENANT, 1)

    @pytest.mark.asyncio
    async def test_create_model_cross_tenant_provider_404(self):
        payload = LlmModelCreate(
            provider_id=9, model_name="m", model_type="chat"
        )
        with patch.object(
            KuaiaiLlmProvider, "get_or_none", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await catalog_service.create_model(TENANT, _user(), payload)

    @pytest.mark.asyncio
    async def test_default_model_cross_tenant_404(self):
        payload = AgentProfileCreate(
            name="a1", grant_mode="USER", default_model_id=55
        )
        with (
            patch.object(
                KuaiaiAgentProfile, "get_or_none", new=AsyncMock(return_value=None)
            ),
            patch.object(
                KuaiaiLlmModel, "get_or_none", new=AsyncMock(return_value=None)
            ),
        ):
            with pytest.raises(NotFoundError):
                await agent_service.create_profile(TENANT, _user(), payload)

    @pytest.mark.asyncio
    async def test_default_model_must_be_enabled_chat(self):
        embed_model = _model(mtype="embed")
        payload = AgentProfileCreate(
            name="a1", grant_mode="USER", default_model_id=2
        )
        with (
            patch.object(
                KuaiaiAgentProfile, "get_or_none", new=AsyncMock(return_value=None)
            ),
            patch.object(
                KuaiaiLlmModel,
                "get_or_none",
                new=AsyncMock(return_value=embed_model),
            ),
        ):
            with pytest.raises(BusinessLogicError) as exc:
                await agent_service.create_profile(TENANT, _user(), payload)
        assert exc.value.status_code == 400

        disabled_chat = _model(mtype="chat", status="停用")
        with (
            patch.object(
                KuaiaiAgentProfile, "get_or_none", new=AsyncMock(return_value=None)
            ),
            patch.object(
                KuaiaiLlmModel,
                "get_or_none",
                new=AsyncMock(return_value=disabled_chat),
            ),
        ):
            with pytest.raises(BusinessLogicError):
                await agent_service.create_profile(TENANT, _user(), payload)


class TestApiKeyMasking:
    def test_provider_out_masks_api_key(self):
        out = catalog_service.provider_out(_provider(api_key="sk-super-secret"))
        assert out["api_key"] == "****"
        assert out["api_key_configured"] is True
        assert "sk-super-secret" not in str(out)
        assert "tenant_id" not in out

    def test_provider_out_blank_key(self):
        out = catalog_service.provider_out(_provider(api_key=None))
        assert out["api_key"] is None
        assert out["api_key_configured"] is False

    @pytest.mark.asyncio
    async def test_update_masked_api_key_keeps_old(self):
        provider = _provider(api_key="sk-old")
        with patch.object(
            KuaiaiLlmProvider, "get_or_none", new=AsyncMock(return_value=provider)
        ):
            await catalog_service.update_provider(
                TENANT, _user(), 1, LlmProviderUpdate(api_key="****")
            )
        data = provider.update_from_dict.call_args.args[0]
        assert "api_key" not in data

        with patch.object(
            KuaiaiLlmProvider, "get_or_none", new=AsyncMock(return_value=provider)
        ):
            await catalog_service.update_provider(
                TENANT, _user(), 1, LlmProviderUpdate(api_key="sk-new")
            )
        data = provider.update_from_dict.call_args.args[0]
        assert data["api_key"] == "sk-new"

    @pytest.mark.asyncio
    async def test_model_options_have_no_connection_fields(self):
        rows = [_model(mid=1), _model(mid=2, mtype="embed")]
        providers = [_provider(pid=1)]
        with (
            patch.object(KuaiaiLlmModel, "filter", MagicMock(return_value=_qs(rows))),
            patch.object(
                KuaiaiLlmProvider, "filter", MagicMock(return_value=_qs(providers))
            ),
        ):
            options = await catalog_service.model_options(TENANT)
        assert len(options) == 2
        for opt in options:
            assert "api_key" not in opt
            assert "base_url" not in opt
            assert "tenant_id" not in opt


class TestModelTypeValidation:
    @pytest.mark.asyncio
    async def test_referenced_model_type_change_400(self):
        """m4：模型行被 Agent 档案 default_model_id 引用时禁止改型。"""
        model = _model(mid=1, mtype="chat")
        profiles_q = _qs([_profile(aid=1)])
        with (
            patch.object(
                KuaiaiLlmModel,
                "get_or_none",
                new=AsyncMock(return_value=model),
            ),
            patch.object(
                KuaiaiAgentProfile,
                "filter",
                MagicMock(return_value=profiles_q),
            ),
        ):
            with pytest.raises(BusinessLogicError) as exc:
                await catalog_service.update_model(
                    TENANT, _user(), 1, LlmModelUpdate(model_type="embed")
                )
        assert exc.value.status_code == 400
        assert "model_type" in exc.value.message
        model.update_from_dict.assert_not_called()

    @pytest.mark.asyncio
    async def test_unreferenced_model_type_change_ok(self):
        """m4：未被档案引用的模型行允许改型。"""
        model = _model(mid=1, mtype="chat")
        with (
            patch.object(
                KuaiaiLlmModel,
                "get_or_none",
                new=AsyncMock(return_value=model),
            ),
            patch.object(
                KuaiaiAgentProfile,
                "filter",
                MagicMock(return_value=_qs([])),
            ),
        ):
            await catalog_service.update_model(
                TENANT, _user(), 1, LlmModelUpdate(model_type="embed")
            )
        data = model.update_from_dict.call_args.args[0]
        assert data["model_type"] == "embed"

    @pytest.mark.asyncio
    async def test_same_model_type_skips_reference_check(self):
        """model_type 未实际变化时不查档案引用（避免无谓查询）。"""
        model = _model(mid=1, mtype="chat")
        with (
            patch.object(
                KuaiaiLlmModel,
                "get_or_none",
                new=AsyncMock(return_value=model),
            ),
            patch.object(
                KuaiaiAgentProfile, "filter", MagicMock()
            ) as mock_filter,
        ):
            await catalog_service.update_model(
                TENANT, _user(), 1, LlmModelUpdate(model_type="chat")
            )
        mock_filter.assert_not_called()
        model.update_from_dict.assert_called()

    @pytest.mark.asyncio
    async def test_bad_model_type_400(self):
        payload = LlmModelCreate(provider_id=1, model_name="m", model_type="audio")
        with patch.object(
            KuaiaiLlmProvider,
            "get_or_none",
            new=AsyncMock(return_value=_provider()),
        ):
            with pytest.raises(BusinessLogicError) as exc:
                await catalog_service.create_model(TENANT, _user(), payload)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_provider_type_free_form_saved(self):
        """provider_type 非闭集：自定义值可保存（KR-D5）。"""
        created = {}

        async def _create(**kw):
            created.update(kw)
            return _provider()

        payload = LlmProviderCreate(
            code="myvendor",
            name="My Vendor",
            base_url="https://x.invalid/v1",
            api_key="sk-1",
            provider_type="whatever-custom",
        )
        with (
            patch.object(
                KuaiaiLlmProvider, "get_or_none", new=AsyncMock(return_value=None)
            ),
            patch.object(
                KuaiaiLlmProvider, "create", new=AsyncMock(side_effect=_create)
            ),
        ):
            await catalog_service.create_provider(TENANT, _user(), payload)
        assert created["provider_type"] == "whatever-custom"
        assert created["api_key"] == "sk-1"
