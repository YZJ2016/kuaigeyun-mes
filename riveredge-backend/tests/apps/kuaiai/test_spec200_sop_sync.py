"""KU-AI spec 200 单测：SOP→知识库同步 + query_process_routes（全部 mock，不触真库）。

覆盖要点：
- S1-a 配置：read_sop_sync 读视图回落、validate_sop_sync_payload 闭集校验；
  设置页 PUT 写回 sop_sync 键、启用时目标库启用复核（失败 422 不写库）；
- 同步链路：未配置跳过、SOP 缺失跳过、作废/纸质/无正文下架（delete_document）、
  生效电子正文建/更新同一文档（source_ref 幂等、系统审计、pending →
  index_document 直调）、目标库停用失败关闭；
- 投递：enqueue_sop_sync.kiq 参数与失败吞没；文控 _enqueue 探测 ImportError
  不报错；Taskiq 任务 with_tenant 内执行、异常回 failed 不抛；
- Tool：material_id 解析（物料级→分组兜底）、keyword 列表 + 数据范围收敛、
  工序序列来自 get_process_route_tree、空/错误文案、limit≤20。
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.models.knowledge import KuaiaiKnowledgeDocument, KuaiaiKnowledgeBase
from apps.kuaiai.services import settings_service as svc
from apps.kuaiai.services import sop_sync_service as sss
from apps.kuaiai.services.tools import process_routes as pr
from apps.kuaiai.schemas.operations import SettingsUpdateIn
from apps.master_data.models.material import Material, MaterialGroup
from apps.master_data.models.process import SOP, Operation, ProcessRoute
from core.ai.runtime.context import AiRuntimeContext
from core.models.site_setting import SiteSetting
from core.utils.integration_settings import (
    read_sop_sync,
    validate_sop_sync_payload,
)
from infra.exceptions.exceptions import ValidationError

TENANT = 7
USER_ID = 5
SOP_ID = 88
KB_ID = 42

TEMPLATE_KEYS = tuple(
    t.key
    for t in __import__(
        "apps.kuaiai.services.agent_scene_service", fromlist=["SCENE_TEMPLATES"]
    ).SCENE_TEMPLATES
)


def _ctx():
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
    )


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
    q.values = AsyncMock(return_value=list(rows))
    q.values_list = AsyncMock(return_value=list(rows))
    return q


class _FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _site(settings=None):
    return SimpleNamespace(
        id=3,
        uuid="site-uuid-1",
        tenant_id=TENANT,
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        settings=settings or {},
        save=AsyncMock(),
    )


def _sop(**kw):
    base = dict(
        id=SOP_ID,
        tenant_id=TENANT,
        code="SOP-WELD-01",
        name="焊接作业指导",
        version="1.0",
        current_revision="1.0",
        carrier="electronic",
        control_status="effective",
        content="第一步：准备焊枪；第二步：按轨迹焊接。",
        operation_id=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _kb(enabled=True):
    return SimpleNamespace(
        id=KB_ID,
        tenant_id=TENANT,
        name="工艺知识库",
        status="启用" if enabled else "停用",
    )


# ============================================================ S1 配置读写


class TestSopSyncSettings:
    def test_read_fallbacks(self):
        assert read_sop_sync({}) == {"enabled": False, "knowledge_id": None}
        assert read_sop_sync({"sop_sync": "bad"})["enabled"] is False
        out = read_sop_sync(
            {"sop_sync": {"enabled": True, "knowledge_id": 9, "junk": 1}}
        )
        assert out == {"enabled": True, "knowledge_id": 9}

    def test_validate_closed_set(self):
        assert validate_sop_sync_payload(
            {"enabled": True, "knowledge_id": 3}
        ) == {"enabled": True, "knowledge_id": 3}
        assert validate_sop_sync_payload({"enabled": False}) == {
            "enabled": False,
            "knowledge_id": None,
        }
        for bad in (
            None,
            {"enabled": "yes", "knowledge_id": 1},
            {"enabled": True, "knowledge_id": None},
            {"enabled": True, "knowledge_id": "x"},
            {"enabled": False, "knowledge_id": 0},
        ):
            with pytest.raises(ValidationError):
                validate_sop_sync_payload(bad)

    def test_schema_sop_sync_model(self):
        payload = SettingsUpdateIn(
            version="v1",
            chat_connection_uuid="c",
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
            sop_sync={"enabled": True, "knowledge_id": 9},
        )
        assert payload.sop_sync.enabled is True
        assert payload.sop_sync.knowledge_id == 9


# ============================================================ 同步服务


class TestGetSopSyncConfig:
    @pytest.mark.asyncio
    async def test_disabled_or_missing(self):
        site = _site({"integrations": {"kuaiai": {}}})
        with patch(
            "core.services.system.site_setting_service"
            ".SiteSettingService.get_settings",
            AsyncMock(return_value=site),
        ):
            assert await sss.get_sop_sync_config(TENANT) is None

    @pytest.mark.asyncio
    async def test_enabled(self):
        site = _site(
            {
                "integrations": {
                    "kuaiai": {"sop_sync": {"enabled": True, "knowledge_id": KB_ID}}
                }
            }
        )
        with patch(
            "core.services.system.site_setting_service"
            ".SiteSettingService.get_settings",
            AsyncMock(return_value=site),
        ):
            cfg = await sss.get_sop_sync_config(TENANT)
        assert cfg == {"enabled": True, "knowledge_id": KB_ID}


class TestEnqueue:
    @pytest.mark.asyncio
    async def test_kiq_params_and_swallow(self):
        task = SimpleNamespace(kiq=AsyncMock())
        with patch.dict(
            sys.modules,
            {"core.tasks.ai_tasks": SimpleNamespace(run_sop_knowledge_sync=task)},
        ):
            await sss.enqueue_sop_sync(TENANT, SOP_ID)
        task.kiq.assert_awaited_once_with(tenant_id=TENANT, sop_id=SOP_ID)

        task2 = SimpleNamespace(kiq=AsyncMock(side_effect=RuntimeError("mq")))
        with patch.dict(
            sys.modules,
            {"core.tasks.ai_tasks": SimpleNamespace(run_sop_knowledge_sync=task2)},
        ):
            await sss.enqueue_sop_sync(TENANT, SOP_ID)  # 不抛


class TestSyncSopDocument:
    def _base_patches(self, sop, kb, doc=None):
        return (
            patch.object(
                sss,
                "get_sop_sync_config",
                AsyncMock(return_value={"enabled": True, "knowledge_id": KB_ID}),
            ),
            patch.object(SOP, "filter", MagicMock(return_value=_qs([sop]))),
            patch.object(
                KuaiaiKnowledgeBase, "filter", MagicMock(return_value=_qs([kb]))
            ),
            patch.object(
                KuaiaiKnowledgeDocument,
                "filter",
                MagicMock(return_value=_qs([doc] if doc else [])),
            ),
        )

    @pytest.mark.asyncio
    async def test_not_configured_skip(self):
        with patch.object(
            sss, "get_sop_sync_config", AsyncMock(return_value=None)
        ):
            out = await sss.sync_sop_document(TENANT, SOP_ID)
        assert out == {"skipped": "not_configured"}

    @pytest.mark.asyncio
    async def test_sop_missing_skip(self):
        p_cfg, p_sop, p_kb, p_doc = self._base_patches(None, _kb())
        with p_cfg, patch.object(
            SOP, "filter", MagicMock(return_value=_qs([]))
        ), p_kb, p_doc:
            out = await sss.sync_sop_document(TENANT, SOP_ID)
        assert out == {"skipped": "sop_missing"}

    @pytest.mark.asyncio
    async def test_obsolete_takedown(self):
        doc = SimpleNamespace(id=500, tenant_id=TENANT)
        p_cfg, p_sop, p_kb, p_doc = self._base_patches(
            _sop(control_status="obsolete"), _kb(), doc
        )
        with p_cfg, p_sop, p_kb, p_doc, patch(
            "apps.kuaiai.services.knowledge_service"
            ".KnowledgeService.delete_document",
            AsyncMock(),
        ) as m_del:
            out = await sss.sync_sop_document(TENANT, SOP_ID)
        m_del.assert_awaited_once_with(TENANT, 500)
        assert out == {"skipped": "not_effective", "removed": True}

    @pytest.mark.asyncio
    async def test_paper_carrier_skipped_no_doc(self):
        p_cfg, p_sop, p_kb, p_doc = self._base_patches(
            _sop(carrier="paper"), _kb()
        )
        with p_cfg, p_sop, p_kb, p_doc:
            out = await sss.sync_sop_document(TENANT, SOP_ID)
        assert out == {"skipped": "no_electronic_content", "removed": False}

    @pytest.mark.asyncio
    async def test_publish_creates_doc_and_indexes(self):
        p_cfg, p_sop, p_kb, p_doc = self._base_patches(_sop(), _kb())
        create_mock = AsyncMock(
            return_value=SimpleNamespace(id=600, tenant_id=TENANT)
        )
        with p_cfg, p_sop, p_kb, p_doc, patch.object(
            KuaiaiKnowledgeDocument, "create", create_mock
        ), patch.object(
            Operation, "filter", MagicMock(return_value=_qs([]))
        ), patch(
            "apps.kuaiai.services.knowledge_service"
            ".KnowledgeService.index_document",
            AsyncMock(),
        ) as m_index:
            out = await sss.sync_sop_document(TENANT, SOP_ID)
        kw = create_mock.await_args.kwargs
        assert kw["tenant_id"] == TENANT
        assert kw["knowledge_id"] == KB_ID
        assert kw["source_type"] == "md"
        assert kw["source_ref_type"] == "sop"
        assert kw["source_ref_id"] == SOP_ID
        assert kw["status"] == "pending"
        assert kw["created_by"] == 0 and kw["created_by_name"] == "系统"
        assert "焊接作业指导" in kw["raw_content"]
        assert "SOP-WELD-01" in kw["raw_content"]
        m_index.assert_awaited_once_with(tenant_id=TENANT, document_id=600)
        assert out["synced"] is True and out["document_id"] == 600

    @pytest.mark.asyncio
    async def test_republish_updates_same_doc(self):
        doc = MagicMock()
        doc.id = 601
        doc.save = AsyncMock()
        p_cfg, p_sop, p_kb, p_doc = self._base_patches(
            _sop(current_revision="2.0"), _kb(), doc
        )
        create_mock = AsyncMock()
        with p_cfg, p_sop, p_kb, p_doc, patch.object(
            KuaiaiKnowledgeDocument, "create", create_mock
        ), patch.object(
            Operation, "filter", MagicMock(return_value=_qs([]))
        ), patch(
            "apps.kuaiai.services.knowledge_service"
            ".KnowledgeService.index_document",
            AsyncMock(),
        ) as m_index:
            out = await sss.sync_sop_document(TENANT, SOP_ID)
        create_mock.assert_not_awaited()
        assert doc.status == "pending"
        assert "2.0" in doc.raw_content
        m_index.assert_awaited_once_with(tenant_id=TENANT, document_id=601)
        assert out["document_id"] == 601

    @pytest.mark.asyncio
    async def test_disabled_kb_closed(self):
        p_cfg, p_sop, p_kb, p_doc = self._base_patches(
            _sop(), _kb(enabled=False)
        )
        with p_cfg, p_sop, p_kb, p_doc, patch.object(
            KuaiaiKnowledgeBase, "filter", MagicMock(return_value=_qs([]))
        ):
            out = await sss.sync_sop_document(TENANT, SOP_ID)
        assert out == {"skipped": "knowledge_base_unavailable"}


class TestSopControlHook:
    @pytest.mark.asyncio
    async def test_enqueue_probe_and_call(self):
        from apps.master_data.services.sop_control_service import (
            _enqueue_sop_knowledge_sync,
        )

        with patch(
            "apps.kuaiai.services.sop_sync_service.enqueue_sop_sync",
            AsyncMock(),
        ) as m_enq:
            await _enqueue_sop_knowledge_sync(TENANT, SOP_ID)
        m_enq.assert_awaited_once_with(TENANT, SOP_ID)

    @pytest.mark.asyncio
    async def test_enqueue_import_error_noop(self):
        from apps.master_data.services.sop_control_service import (
            _enqueue_sop_knowledge_sync,
        )

        with patch.dict(
            sys.modules, {"apps.kuaiai.services.sop_sync_service": None}
        ):
            await _enqueue_sop_knowledge_sync(TENANT, SOP_ID)  # 不抛


class TestSyncTask:
    @pytest.mark.asyncio
    async def test_task_calls_sync_in_tenant_scope(self):
        from core.tasks.ai_tasks import run_sop_knowledge_sync

        with patch(
            "apps.kuaiai.services.sop_sync_service.sync_sop_document",
            AsyncMock(return_value={"synced": True}),
        ) as m_sync:
            out = await run_sop_knowledge_sync(TENANT, SOP_ID)
        m_sync.assert_awaited_once_with(TENANT, SOP_ID)
        assert out == {"synced": True}

    @pytest.mark.asyncio
    async def test_task_failure_redacted(self):
        from core.tasks.ai_tasks import run_sop_knowledge_sync

        with patch(
            "apps.kuaiai.services.sop_sync_service.sync_sop_document",
            AsyncMock(side_effect=RuntimeError("db secret")),
        ):
            out = await run_sop_knowledge_sync(TENANT, SOP_ID)
        assert out["status"] == "failed"
        assert out["error_type"] == "RuntimeError"
        assert "secret" not in str(out)


# ============================================================ 设置页 PUT 写回


@pytest.mark.asyncio
class TestPutSopSync:
    def _run_save(self, site, payload):
        from unittest.mock import MagicMock as MM
        from core.models.integration_config import IntegrationConfig

        def _conn_filter(**kwargs):
            uuid = kwargs.get("uuid")
            if uuid is not None:
                return _qs([SimpleNamespace(
                    uuid=uuid,
                    type="deepseek",
                    is_active=True,
                    get_config=lambda: {
                        "model_role": "chat",
                        "base_url": "https://x",
                        "model": "m",
                        "api_key": "k",
                    },
                )])
            return _qs([])

        return patch.object(
            IntegrationConfig, "filter", MM(side_effect=_conn_filter)
        ), patch(
            "core.services.system.site_setting_service"
            ".SiteSettingService.get_settings",
            AsyncMock(return_value=site),
        ), patch.object(
            SiteSetting, "filter", MM(return_value=_qs([site]))
        ), patch(
            "apps.kuaiai.services.settings_service.in_transaction",
            MagicMock(return_value=_FakeTx()),
        ), patch(
            "core.ai.runtime.model_factory.evict_model_cache", MagicMock()
        ), patch.object(
            svc, "get_settings", AsyncMock(return_value={"ok": True})
        )

    def _payload(self, site, **over):
        base = dict(
            version=svc._version_of(site),
            chat_connection_uuid="c1",
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

    async def test_sop_sync_written(self):
        site = _site({"integrations": {"kuaiai": {}}})
        payload = self._payload(
            site, sop_sync={"enabled": True, "knowledge_id": KB_ID}
        )
        p1, p2, p3, p4, p5, p6 = self._run_save(site, payload)
        with p1, p2, p3, p4, p5, p6, patch.object(
            KuaiaiKnowledgeBase,
            "filter",
            MagicMock(return_value=_qs([_kb()])),
        ):
            await svc.update_settings(
                TENANT, SimpleNamespace(id=USER_ID), payload
            )
        kuaiai = site.settings["integrations"]["kuaiai"]
        assert kuaiai["sop_sync"] == {"enabled": True, "knowledge_id": KB_ID}

    async def test_sop_sync_disabled_kb_422_no_save(self):
        site = _site({"integrations": {"kuaiai": {}}})
        payload = self._payload(
            site, sop_sync={"enabled": True, "knowledge_id": 999}
        )
        p1, p2, p3, p4, p5, p6 = self._run_save(site, payload)
        with p1, p2, p3, p4, p5, p6, patch.object(
            KuaiaiKnowledgeBase, "filter", MagicMock(return_value=_qs([]))
        ):
            with pytest.raises(ValidationError):
                await svc.update_settings(
                    TENANT, SimpleNamespace(id=USER_ID), payload
                )
        site.save.assert_not_awaited()

    async def test_sop_sync_absent_untouched(self):
        site = _site(
            {"integrations": {"kuaiai": {"sop_sync": {"enabled": True, "knowledge_id": 1}}}}
        )
        payload = self._payload(site)
        p1, p2, p3, p4, p5, p6 = self._run_save(site, payload)
        with p1, p2, p3, p4, p5, p6:
            await svc.update_settings(
                TENANT, SimpleNamespace(id=USER_ID), payload
            )
        kuaiai = site.settings["integrations"]["kuaiai"]
        assert kuaiai["sop_sync"] == {"enabled": True, "knowledge_id": 1}


# ============================================================ query_process_routes


def _route(id_, code, name, version="1.0", is_active=True):
    return SimpleNamespace(
        id=id_,
        tenant_id=TENANT,
        code=code,
        name=name,
        version=version,
        is_active=is_active,
    )


def _tree(routes_ops):
    """{route_id: [op,...]} → tree list of SimpleNamespace(id, operations)."""
    return [
        SimpleNamespace(id=rid, operations=list(ops))
        for rid, ops in routes_ops.items()
    ]


def _op(code, name):
    return SimpleNamespace(code=code, name=name)


class TestQueryProcessRoutes:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await pr.query_process_routes(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_material_id_invalid(self):
        out = await pr.query_process_routes(material_id="x", ctx=_ctx())
        assert "material_id" in out

    @pytest.mark.asyncio
    async def test_material_unbound(self):
        mat = SimpleNamespace(
            id=9, process_route_id=None, group_id=None
        )
        with patch.object(
            Material, "filter", MagicMock(return_value=_qs([mat]))
        ):
            out = await pr.query_process_routes(material_id=9, ctx=_ctx())
        assert "未绑定工艺路线" in out or "不存在" in out

    @pytest.mark.asyncio
    async def test_material_group_fallback(self):
        mat = SimpleNamespace(id=9, process_route_id=None, group_id=5)
        grp = SimpleNamespace(id=5, process_route_id=77)
        route = _route(77, "RT-WELD", "焊接路线")
        with patch.object(
            Material, "filter", MagicMock(return_value=_qs([mat]))
        ), patch.object(
            MaterialGroup, "filter", MagicMock(return_value=_qs([grp]))
        ), patch(
            "apps.master_data.services.process_service"
            ".ProcessService.list_process_routes",
            AsyncMock(return_value=([], 0)),
        ), patch.object(
            ProcessRoute, "filter", MagicMock(return_value=_qs([route]))
        ), patch(
            "apps.master_data.services.process_service"
            ".ProcessService.get_process_route_tree",
            AsyncMock(return_value=_tree({77: [_op("OP10", "焊接")]}) ),
        ), patch(
            "apps.kuaiai.services.scene_tools._scoped_row_ids",
            AsyncMock(return_value={77}),
        ):
            out = await pr.query_process_routes(material_id=9, ctx=_ctx())
        assert "RT-WELD" in out and "OP10" in out and "焊接" in out

    @pytest.mark.asyncio
    async def test_keyword_list_scope_filter(self):
        routes = [_route(1, "RT-A", "路线A"), _route(2, "RT-B", "路线B")]
        with patch(
            "apps.master_data.services.process_service"
            ".ProcessService.list_process_routes",
            AsyncMock(return_value=(routes, 2)),
        ) as m_list, patch(
            "apps.master_data.services.process_service"
            ".ProcessService.get_process_route_tree",
            AsyncMock(
                return_value=_tree(
                    {1: [_op("OP10", "下料"), _op("OP20", "焊接")]}
                )
            ),
        ), patch(
            "apps.kuaiai.services.scene_tools._scoped_row_ids",
            AsyncMock(return_value={1}),
        ):
            out = await pr.query_process_routes(keyword="RT", ctx=_ctx())
        assert "RT-A" in out and "下料" in out and "焊接" in out
        assert "RT-B" not in out
        kw = m_list.await_args.kwargs
        assert kw["keyword"] == "RT"
        assert kw["limit"] <= 20

    @pytest.mark.asyncio
    async def test_empty_and_error(self):
        with patch(
            "apps.master_data.services.process_service"
            ".ProcessService.list_process_routes",
            AsyncMock(return_value=([], 0)),
        ):
            out = await pr.query_process_routes(ctx=_ctx())
        assert "未查询到" in out

        with patch(
            "apps.master_data.services.process_service"
            ".ProcessService.list_process_routes",
            AsyncMock(side_effect=RuntimeError("db")),
        ):
            out = await pr.query_process_routes(ctx=_ctx())
        assert out == "查询工艺路线失败，请稍后重试"
