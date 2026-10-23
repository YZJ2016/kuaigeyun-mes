"""评审闭环测试：manifest/场景开关失败关闭 + 性能优化回归。

覆盖：
- B-M1  manifest 读失败/结构非法/kind 非法 → 装配拒绝，写 Tool 不裸奔
- minor-9 场景总开关读失败 → fail-closed 拒绝；键缺失才默认启用
- minor-7 query_process_routes 统计口径 = 范围收敛后条数；
        get_process_route_tree 只按已收敛 route_ids 取树
- 性能   pulse_total_count TTL 缓存（tenant+user 隔离、失败不缓存）
        _route_permissions_for_user 批量权限
        _inventory_visible_pairs 候选收窄
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.services import agent_assembler, agent_scene_service
from apps.kuaiai.services import tool_catalog_service
from apps.kuaiai.services.tools import process_routes
from infra.exceptions.exceptions import (
    BusinessLogicError,
    ConfigurationError,
)

TENANT = 7
AGENT_ID = 10


def _user(uid: int = 42):
    return SimpleNamespace(id=uid, username=f"u{uid}", full_name="用户")


def _ctx(tenant_id: int = TENANT, uid: int = 42):
    return SimpleNamespace(tenant_id=tenant_id, user=_user(uid))


# ============================================================ B-M1 manifest


_GOOD_MANIFEST = {
    "ai_tools": [
        {"name": "query_work_orders", "kind": "read", "label": "查工单"},
        {
            "name": "submit_production_feedback",
            "kind": "write",
            "label": "报工",
        },
    ]
}


def _profile(**over):
    base = dict(
        id=AGENT_ID,
        tenant_id=TENANT,
        name="档案A",
        system_prompt="你是助手",
        default_model_id=42,
        enabled_tools=["query_work_orders"],
        status="启用",
        grant_mode="USER",
        mcp_server_ids=[],
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestManifestFailClosed:
    def test_manifest_tool_meta_raises_on_unreadable_manifest(self):
        with patch.object(
            tool_catalog_service,
            "_load_manifest",
            side_effect=FileNotFoundError("missing"),
        ):
            with pytest.raises(ConfigurationError):
                tool_catalog_service.manifest_tool_meta()

    def test_manifest_tool_meta_rejects_bad_kind(self):
        bad = {"ai_tools": [{"name": "t", "kind": "dangerous"}]}
        with patch.object(
            tool_catalog_service, "_load_manifest", return_value=bad
        ):
            with pytest.raises(ConfigurationError):
                tool_catalog_service.manifest_tool_meta()

    def test_manifest_tool_meta_rejects_non_list_ai_tools(self):
        with patch.object(
            tool_catalog_service,
            "_load_manifest",
            return_value={"ai_tools": {"name": "t"}},
        ):
            with pytest.raises(ConfigurationError):
                tool_catalog_service.manifest_tool_meta()

    def test_write_names_fail_closed_when_enabled_tool_missing(self):
        """ENABLED_TOOL_NAMES 中 manifest 未声明的 Tool 按 write 处理。"""
        manifest = {"ai_tools": [{"name": "query_work_orders",
                                  "kind": "read"}]}
        with patch.object(
            tool_catalog_service, "_load_manifest", return_value=manifest
        ):
            write = tool_catalog_service.manifest_write_tool_names()
        # query_work_orders 声明 read 故不写入；其余 ENABLED 全部按 write
        assert "query_work_orders" not in write
        assert "submit_production_feedback" in write

    @pytest.mark.asyncio
    async def test_assemble_rejects_broken_manifest_no_bare_write(self):
        """manifest 损坏 → 拒绝装配，且不会构造裸写 Tool agent。"""
        profile = _profile(
            enabled_tools=["query_work_orders", "submit_production_feedback"]
        )
        with (
            patch.object(
                agent_assembler.KuaiaiAgentProfile,
                "get_or_none",
                new=AsyncMock(return_value=profile),
            ),
            patch.object(
                agent_assembler.grant_service,
                "check_use_grant",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                tool_catalog_service,
                "_load_manifest",
                side_effect=OSError("corrupt"),
            ),
            patch.object(
                agent_assembler, "build_chat_model", new=AsyncMock()
            ) as mock_model,
            patch.object(
                agent_assembler, "build_agent", new=MagicMock()
            ) as mock_agent,
        ):
            with pytest.raises(ConfigurationError):
                await agent_assembler.assemble(
                    TENANT,
                    _user(),
                    False,
                    False,
                    AGENT_ID,
                    agent_path=False,
                    has_session=True,
                )
        # 拒绝点先于模型/agent 构造：无任何上游触达
        mock_model.assert_not_called()
        mock_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_assemble_rejects_invalid_kind_manifest(self):
        """kind 非法 → 装配期抛错而非静默降级为 read。"""
        bad = {"ai_tools": [{"name": "query_work_orders",
                             "kind": "admin"}]}
        with (
            patch.object(
                agent_assembler.KuaiaiAgentProfile,
                "get_or_none",
                new=AsyncMock(return_value=_profile()),
            ),
            patch.object(
                agent_assembler.grant_service,
                "check_use_grant",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                tool_catalog_service, "_load_manifest", return_value=bad
            ),
            patch.object(
                agent_assembler, "build_agent", new=MagicMock()
            ) as mock_agent,
        ):
            with pytest.raises(ConfigurationError):
                await agent_assembler.assemble(
                    TENANT,
                    _user(),
                    False,
                    False,
                    AGENT_ID,
                    agent_path=False,
                    has_session=True,
                )
        mock_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_tools_get_hitl_and_checkpointer(self):
        """manifest 声明 write → HITL middleware + checkpointer 必须挂。"""
        from apps.kuaiai.services.checkpoint_saver import (
            TortoiseCheckpointSaver,
        )

        profile = _profile(
            enabled_tools=["query_work_orders", "submit_production_feedback"]
        )
        with (
            patch.object(
                agent_assembler.KuaiaiAgentProfile,
                "get_or_none",
                new=AsyncMock(return_value=profile),
            ),
            patch.object(
                agent_assembler.grant_service,
                "check_use_grant",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                tool_catalog_service,
                "_load_manifest",
                return_value=_GOOD_MANIFEST,
            ),
            patch.object(
                agent_assembler,
                "build_chat_model",
                new=AsyncMock(
                    return_value=SimpleNamespace(model_name="m")
                ),
            ),
            patch.object(
                agent_assembler,
                "registry_to_lc_tools",
                new=MagicMock(return_value=[]),
            ),
            patch.object(
                agent_assembler,
                "build_mcp_aware_tool_guard",
                new=MagicMock(return_value=MagicMock()),
            ),
            patch.object(
                agent_assembler,
                "build_agent",
                new=MagicMock(return_value="agent-obj"),
            ) as mock_agent,
        ):
            out = await agent_assembler.assemble(
                TENANT,
                _user(),
                False,
                False,
                AGENT_ID,
                agent_path=False,
                has_session=True,
            )
        assert out.agent == "agent-obj"
        assert out.write_tools == frozenset({"submit_production_feedback"})
        kwargs = mock_agent.call_args.kwargs
        assert any(
            type(m).__name__ == "HumanInTheLoopMiddleware"
            for m in kwargs.get("middleware", [])
        )
        assert isinstance(
            kwargs.get("checkpointer"), TortoiseCheckpointSaver
        )


# ============================================================ minor-9 场景开关


def _scene(template_key="inventory-insight", instance_key=None):
    return SimpleNamespace(
        id=101,
        instance_key=instance_key or template_key,
        template_key=template_key,
        overrides={},
        enabled=True,
        agent_profile_id=AGENT_ID,
    )


def _broken_site_settings():
    return patch(
        "core.services.system.site_setting_service."
        "SiteSettingService.get_settings",
        AsyncMock(side_effect=RuntimeError("db down")),
    )


def _qs_chain(rows):
    qs = MagicMock()
    qs.order_by = MagicMock(return_value=qs)
    qs.all = AsyncMock(return_value=rows)
    return qs


class TestSceneSwitchFailClosed:
    @pytest.mark.asyncio
    async def test_switches_default_true_when_key_missing(self):
        """站点设置正常但键缺失 → 默认启用（非失败关闭语义）。"""
        with patch(
            "core.services.system.site_setting_service."
            "SiteSettingService.get_settings",
            AsyncMock(return_value=SimpleNamespace(settings={})),
        ):
            switches = await agent_scene_service.agent_switches(TENANT)
        assert switches
        assert all(v is True for v in switches.values())

    @pytest.mark.asyncio
    async def test_switches_fail_closed_on_read_error(self):
        with _broken_site_settings():
            switches = await agent_scene_service.agent_switches(
                TENANT, fail_closed=True
            )
        assert switches
        assert all(v is False for v in switches.values())

    @pytest.mark.asyncio
    async def test_switches_non_guard_path_keeps_default_true(self):
        """非放行判定路径读失败仍按「未配置」回落（键缺失默认 True）。"""
        with _broken_site_settings():
            switches = await agent_scene_service.agent_switches(
                TENANT, fail_closed=False
            )
        assert all(v is True for v in switches.values())

    @pytest.mark.asyncio
    async def test_guard_rejects_when_switch_read_fails(self):
        with (
            patch.object(
                agent_scene_service.KuaiaiAgentScene,
                "get_or_none",
                new=AsyncMock(return_value=_scene()),
            ),
            _broken_site_settings(),
        ):
            with pytest.raises(BusinessLogicError):
                await agent_scene_service.guard_scene_agent_key(
                    TENANT, "inventory-insight", AGENT_ID, _user()
                )

    @pytest.mark.asyncio
    async def test_library_cards_fail_closed_on_read_error(self):
        """智能体库卡片构建读开关失败 → 绑定实例卡 not_ready（总开关停用）。"""
        scene = _scene()
        profile = SimpleNamespace(id=AGENT_ID, status="启用")
        with (
            patch.object(
                agent_scene_service.KuaiaiAgentScene,
                "filter",
                new=MagicMock(return_value=_qs_chain([scene])),
            ),
            patch.object(
                agent_scene_service.KuaiaiAgentProfile,
                "filter",
                new=MagicMock(return_value=_qs_chain([profile])),
            ),
            patch.object(
                agent_scene_service.grant_service,
                "usable_profile_ids",
                new=AsyncMock(return_value=set()),
            ),
            _broken_site_settings(),
        ):
            view = await agent_scene_service.list_agent_library(
                TENANT, _user()
            )
        items = view["items"]
        assert items
        assert all(i["status"] == "not_ready" for i in items)
        bound = next(i for i in items if i["key"] == scene.instance_key)
        assert bound["disabled_reason"] == "场景总开关已停用"


# ============================================================ minor-7 工艺路线


def _route(i: int):
    return SimpleNamespace(
        id=i, code=f"PR-{i}", name=f"路线{i}", is_active=True, version="1.0"
    )


def _process_service_patches(items, total, tree):
    from apps.master_data.services.process_service import ProcessService

    return (
        patch.object(
            ProcessService,
            "list_process_routes",
            new=AsyncMock(return_value=(items, total)),
        ),
        patch.object(
            ProcessService,
            "get_process_route_tree",
            new=AsyncMock(return_value=tree),
        ),
    )


class TestProcessRouteCount:
    @pytest.mark.asyncio
    async def test_count_uses_scoped_items_not_service_total(self):
        route = _route(5)
        tree = SimpleNamespace(id=5, operations=[])
        p1, p2 = _process_service_patches([route], 999, [tree])
        with (
            p1,
            p2,
            patch(
                "apps.kuaiai.services.scene_tools._scoped_row_ids",
                AsyncMock(side_effect=lambda _m, _c, _r, ids: ids),
            ),
        ):
            result = await process_routes.query_process_routes(
                ctx=_ctx(), limit=10
            )
        # 不回显未收敛的全租户 total
        assert "999" not in result
        assert "共 1 条工艺路线（当前用户数据范围内" in result
        assert "PR-5" in result

    @pytest.mark.asyncio
    async def test_tree_fetch_only_scoped_route_ids(self):
        routes = [_route(1), _route(2)]
        p1, p2 = _process_service_patches(routes, 2, [])
        with (
            p1,
            p2 as m_tree,
            patch(
                "apps.kuaiai.services.scene_tools._scoped_row_ids",
                AsyncMock(side_effect=lambda _m, _c, _r, ids: ids),
            ),
        ):
            await process_routes.query_process_routes(ctx=_ctx(), limit=10)
        assert set(m_tree.await_args.kwargs["route_ids"]) == {1, 2}
        assert m_tree.await_args.kwargs["is_active"] is None

    @pytest.mark.asyncio
    async def test_scope_filter_narrows_reported_count(self):
        """scope 只放行 1/2 行 → 文案报 1 条，树只查 1 个 id。"""
        routes = [_route(1), _route(2)]
        tree = SimpleNamespace(id=1, operations=[])
        p1, p2 = _process_service_patches(routes, 2, [tree])
        with (
            p1,
            p2 as m_tree,
            patch(
                "apps.kuaiai.services.scene_tools._scoped_row_ids",
                AsyncMock(return_value={1}),
            ),
        ):
            result = await process_routes.query_process_routes(
                ctx=_ctx(), limit=10
            )
        assert "共 1 条工艺路线（当前用户数据范围内" in result
        assert m_tree.await_args.kwargs["route_ids"] == [1]


# ============================================================ 性能回归


class TestRoutePermissionsBatch:
    @pytest.mark.asyncio
    async def test_admin_bypasses_permission_lookup(self):
        db_user = SimpleNamespace(
            id=42, is_tenant_admin=True, is_infra_admin=False
        )
        with (
            patch.object(
                agent_scene_service.User,
                "get_or_none",
                new=AsyncMock(return_value=db_user),
            ),
            patch(
                "core.services.authorization.user_permission_service."
                "UserPermissionService.get_user_permissions",
                new=AsyncMock(),
            ) as m_perm,
        ):
            out = await agent_scene_service._route_permissions_for_user(
                TENANT, _user()
            )
        m_perm.assert_not_awaited()
        assert out
        assert all(out.values())

    @pytest.mark.asyncio
    async def test_batch_lookup_local_intersection(self):
        db_user = SimpleNamespace(
            id=42, is_tenant_admin=False, is_infra_admin=False
        )
        granted_code = next(
            iter(agent_scene_service.SCENE_ROUTE_PERMISSIONS.values())
        )
        with (
            patch.object(
                agent_scene_service.User,
                "get_or_none",
                new=AsyncMock(return_value=db_user),
            ),
            patch(
                "core.services.authorization.user_permission_service."
                "UserPermissionService.get_user_permissions",
                new=AsyncMock(return_value={granted_code}),
            ) as m_perm,
        ):
            out = await agent_scene_service._route_permissions_for_user(
                TENANT, _user()
            )
        m_perm.assert_awaited_once_with(42, TENANT)
        assert out[granted_code] is True
        assert sum(1 for v in out.values() if v) == 1


class _CountingDetector:
    def __init__(self, domain, calls, items=None):
        self.domain = domain
        self._calls = calls
        self._items = items or []
        self.timeout_seconds = 8.0

    async def detect(self, ctx):
        self._calls.append(self.domain)
        return list(self._items)


class TestPulseCountCache:
    @pytest.mark.asyncio
    async def test_ttl_cache_keyed_by_tenant_and_user(self, monkeypatch):
        from apps.kuaiai.schemas.pulse import PulseItemOut
        from apps.kuaiai.services.pulse import registry as pulse_registry

        pulse_registry._pulse_count_cache.clear()
        import datetime as _dt

        item = PulseItemOut(
            id="production:x:1",
            domain="production",
            rule_code="x",
            severity="warning",
            priority="medium",
            resource_type="work_order",
            resource_id="1",
            title="t",
            fact="f",
            suggestion="s",
            route="/r",
            detected_at=_dt.datetime.now(),
        )
        calls: list[str] = []
        monkeypatch.setattr(
            pulse_registry,
            "DETECTORS",
            {"production": _CountingDetector("production", calls, [item])},
        )
        monkeypatch.setattr(
            pulse_registry,
            "IMPLEMENTED_DOMAINS",
            frozenset({"production"}),
        )
        assert await pulse_registry.pulse_total_count(TENANT, _user()) == 1
        # 命中缓存：同 tenant+user 不重跑 detector
        assert await pulse_registry.pulse_total_count(TENANT, _user()) == 1
        assert len(calls) == 1
        # 换 tenant → 独立缓存键
        assert await pulse_registry.pulse_total_count(888, _user()) == 1
        assert len(calls) == 2
        # 换 user → 独立缓存键
        assert await pulse_registry.pulse_total_count(TENANT, _user(9)) == 1
        assert len(calls) == 3
        # TTL 过期 → 重算（TTL 缩到 0，下一次调用必 miss）
        monkeypatch.setattr(pulse_registry, "_PULSE_COUNT_TTL_SECONDS", 0.0)
        assert await pulse_registry.pulse_total_count(TENANT, _user()) == 1
        assert len(calls) == 4
        pulse_registry._pulse_count_cache.clear()


class TestInventoryVisiblePairs:
    @pytest.mark.asyncio
    async def test_empty_needed_skips_queries(self):
        from apps.kuaiai.services import scene_tools

        with patch(
            "apps.kuaiai.services.scene_tools._apply_scope",
            AsyncMock(),
        ) as m_scope:
            out = await scene_tools._inventory_visible_pairs(_ctx(), set())
        m_scope.assert_not_awaited()
        assert out == set()

    @pytest.mark.asyncio
    async def test_candidates_narrowed_by_needed_pairs(self):
        """line_side/batch 两类源先按 needed pairs 收窄，再套数据范围。"""
        from apps.kuaiai.services import scene_tools

        def _qs(rows):
            qs = MagicMock()
            qs.filter = MagicMock(return_value=qs)
            qs.values = AsyncMock(return_value=rows)
            return qs

        lqs = _qs([{"material_id": 1, "warehouse_id": 10}])
        bqs = _qs(
            [
                {"material_id": 2, "warehouse_id": 20},
                {"material_id": 9, "warehouse_id": 99},
            ]
        )
        with (
            patch(
                "apps.kuaizhizao.models.line_side_inventory."
                "LineSideInventory.filter",
                MagicMock(return_value=lqs),
            ) as m_lf,
            patch(
                "apps.master_data.models.material_batch.MaterialBatch.filter",
                MagicMock(return_value=bqs),
            ) as m_bf,
            patch(
                "apps.kuaiai.services.scene_tools._apply_scope",
                AsyncMock(side_effect=lambda qs, *_a, **_k: qs),
            ),
        ):
            out = await scene_tools._inventory_visible_pairs(
                _ctx(), {(2, 20)}
            )
        # 候选收窄：两类源链上 filter 都带 needed pairs 的 id__in
        for m in (m_lf, m_bf):
            assert m.call_args.kwargs["tenant_id"] == TENANT
        narrowed = [
            c.kwargs for c in lqs.filter.call_args_list
        ] + [c.kwargs for c in bqs.filter.call_args_list]
        assert any(
            "material_id__in" in kw and set(kw["material_id__in"]) == {2}
            for kw in narrowed
        )
        assert any(
            "warehouse_id__in" in kw and set(kw["warehouse_id__in"]) == {20}
            for kw in narrowed
        )
        # 只返回与 needed 交集的可见对
        assert out == {(2, 20)}
