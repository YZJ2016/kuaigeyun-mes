"""KU-AI spec 223 Batch 1A-ii 单测（全部 mock，不触真库）。

覆盖：
1. 新租户初始化 / 初始项加载 FAQ 种子入口收敛到唯一真源
   ``corpus_service.seed_default_faqs_for_tenant``（消除 ``FaqSeedService`` 死导入）；
2. ``/operations/hub`` 默认 ``include_pulse=False`` 不阻塞五域 Pulse 扫描，
   显式 ``include_pulse=True`` 才同步调用 ``_pulse_total``；
3. ``GET /core/ai/stats/pulse-count`` 走 ``pulse_registry.pulse_total_count``（60s 缓存）。
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.api.operations import api_get_hub
from apps.kuaiai.models.knowledge import KuaiaiKnowledgeBase
from apps.kuaiai.services import corpus_service, operations_service
from core.api.ai.router import ai_stats_pulse_count
from core.services.tenant.tenant_init_data_service import TenantInitDataService

TENANT = 7
USER_ID = 5


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
    return q


# ============================================================ Task 1: FAQ Seed 真源


@pytest.mark.asyncio
class TestTenantFaqSeedTruthSource:
    async def test_seed_default_faqs_creates_kb_when_missing(self):
        user = _user()
        created_kb = SimpleNamespace(id=42, name="默认知识库", status="启用")
        with patch(
            "infra.models.user.User.get_or_none",
            AsyncMock(return_value=user),
        ), patch.object(
            KuaiaiKnowledgeBase, "filter", MagicMock(return_value=_qs([]))
        ), patch.object(
            KuaiaiKnowledgeBase, "get_or_none", AsyncMock(return_value=None)
        ), patch.object(
            KuaiaiKnowledgeBase,
            "create",
            AsyncMock(return_value=created_kb),
        ) as mock_create_kb, patch.object(
            corpus_service,
            "seed_faqs",
            AsyncMock(return_value={"created": 6, "skipped": 0}),
        ) as mock_seed:
            count = await corpus_service.seed_default_faqs_for_tenant(
                TENANT, user_id=USER_ID
            )

        assert count == 6
        mock_create_kb.assert_awaited_once()
        create_kwargs = mock_create_kb.await_args.kwargs
        assert create_kwargs["tenant_id"] == TENANT
        assert create_kwargs["created_by"] == USER_ID
        assert create_kwargs["updated_by"] == USER_ID
        mock_seed.assert_awaited_once_with(TENANT, user, 42)

    async def test_seed_default_faqs_reuses_existing_enabled_kb(self):
        existing_kb = SimpleNamespace(id=19, name="企业知识库", status="启用")
        with patch.object(
            KuaiaiKnowledgeBase,
            "filter",
            MagicMock(return_value=_qs([existing_kb])),
        ), patch.object(
            KuaiaiKnowledgeBase, "create", AsyncMock()
        ) as mock_create_kb, patch.object(
            corpus_service,
            "seed_faqs",
            AsyncMock(return_value={"created": 2, "skipped": 4}),
        ) as mock_seed:
            count = await corpus_service.seed_default_faqs_for_tenant(TENANT)

        assert count == 2
        mock_create_kb.assert_not_awaited()
        mock_seed.assert_awaited_once_with(TENANT, None, 19)

    async def test_seed_default_faqs_skips_when_default_kb_disabled(self):
        disabled_default = SimpleNamespace(id=21, name="默认知识库", status="停用")
        with patch.object(
            KuaiaiKnowledgeBase, "filter", MagicMock(return_value=_qs([]))
        ), patch.object(
            KuaiaiKnowledgeBase,
            "get_or_none",
            AsyncMock(return_value=disabled_default),
        ), patch.object(
            KuaiaiKnowledgeBase, "create", AsyncMock()
        ) as mock_create_kb, patch.object(
            corpus_service, "seed_faqs", AsyncMock()
        ) as mock_seed:
            count = await corpus_service.seed_default_faqs_for_tenant(TENANT)

        assert count == 0
        mock_create_kb.assert_not_awaited()
        mock_seed.assert_not_awaited()

    async def test_tenant_init_run_single_kuaiai_faq_preset_calls_truth_source(self):
        with patch(
            "apps.common.optional_pro.pro_app_available",
            MagicMock(return_value=True),
        ), patch.object(
            corpus_service,
            "seed_default_faqs_for_tenant",
            AsyncMock(return_value=6),
        ) as mock_seed:
            count = await TenantInitDataService.run_single(
                TENANT, "kuaiai_faq_preset", current_user_id=USER_ID
            )

        assert count == 6
        mock_seed.assert_awaited_once_with(TENANT, user_id=USER_ID)

    async def test_tenant_init_run_single_skips_when_kuaiai_unavailable(self):
        with patch(
            "apps.common.optional_pro.pro_app_available",
            MagicMock(return_value=False),
        ), patch.object(
            corpus_service,
            "seed_default_faqs_for_tenant",
            AsyncMock(),
        ) as mock_seed:
            count = await TenantInitDataService.run_single(
                TENANT, "kuaiai_faq_preset", current_user_id=USER_ID
            )

        assert count == 0
        mock_seed.assert_not_awaited()


class TestNoDeadFaqSeedReferences:
    def test_no_dead_faq_seed_service_references(self):
        src_root = Path(__file__).resolve().parents[3] / "src"
        for rel in (
            "core/services/tenant/tenant_init_data_service.py",
            "infra/services/tenant_service.py",
        ):
            content = (src_root / rel).read_text(encoding="utf-8")
            assert "faq_seed_service" not in content
            assert "FaqSeedService" not in content


# ============================================================ Task 2: Hub Pulse 解耦


@pytest.mark.asyncio
class TestHubPulseDecoupling:
    async def test_get_hub_skips_pulse_by_default(self):
        with patch.object(
            operations_service,
            "_model_public_status",
            AsyncMock(
                return_value={
                    "configured": True,
                    "enabled": True,
                    "model": "gpt-test",
                    "connection_uuid": "conn-1",
                }
            ),
        ), patch.object(
            operations_service,
            "_metrics",
            AsyncMock(
                return_value={
                    "total_calls": 12,
                    "pulse_count": None,
                    "corpus_count": 8,
                    "avg_latency_ms": 210,
                }
            ),
        ), patch.object(
            operations_service,
            "_pulse_total",
            AsyncMock(return_value=99),
        ) as mock_pulse, patch.object(
            operations_service,
            "_build_capabilities",
            AsyncMock(return_value=[]),
        ):
            out = await operations_service.get_hub(TENANT, 7, _user())

        mock_pulse.assert_not_awaited()
        assert out["metrics"]["pulse_count"] is None
        assert out["metrics"]["total_calls"] == 12
        assert out["metrics"]["corpus_count"] == 8
        assert out["metrics"]["avg_latency_ms"] == 210

    async def test_get_hub_computes_pulse_when_requested(self):
        user = _user()
        with patch.object(
            operations_service,
            "_model_public_status",
            AsyncMock(
                return_value={
                    "configured": True,
                    "enabled": True,
                    "model": "gpt-test",
                    "connection_uuid": "conn-1",
                }
            ),
        ), patch.object(
            operations_service,
            "_metrics",
            AsyncMock(
                return_value={
                    "total_calls": 5,
                    "pulse_count": None,
                    "corpus_count": 3,
                    "avg_latency_ms": 150,
                }
            ),
        ), patch.object(
            operations_service,
            "_pulse_total",
            AsyncMock(return_value=4),
        ) as mock_pulse, patch.object(
            operations_service,
            "_build_capabilities",
            AsyncMock(return_value=[]),
        ):
            out = await operations_service.get_hub(
                TENANT, 7, user, include_pulse=True
            )

        mock_pulse.assert_awaited_once_with(TENANT, user)
        assert out["metrics"]["pulse_count"] == 4

    async def test_api_get_hub_forwards_include_pulse(self):
        params = inspect.signature(api_get_hub).parameters
        assert "include_pulse" in params
        assert params["include_pulse"].default.default is False

        user = _user()
        with patch.object(
            operations_service,
            "get_hub",
            AsyncMock(return_value={"days": 7, "model": {}, "metrics": {}, "capabilities": []}),
        ) as mock_get_hub:
            await api_get_hub(
                days=7,
                include_pulse=False,
                tenant_id=TENANT,
                current_user=user,
            )
        mock_get_hub.assert_awaited_once_with(
            TENANT, 7, user, include_pulse=False
        )

    async def test_core_stats_pulse_count_uses_pulse_registry(self):
        user = _user()
        auth = SimpleNamespace(tenant_id=TENANT, user=user)
        with patch(
            "apps.common.optional_pro.pro_app_available",
            MagicMock(return_value=True),
        ), patch(
            "apps.kuaiai.services.pulse.registry.pulse_total_count",
            AsyncMock(return_value=7),
        ) as mock_total:
            res = await ai_stats_pulse_count(ai_auth=auth)

        mock_total.assert_awaited_once_with(TENANT, user)
        assert res == {"pulse_suggestion_count": 7}

    async def test_core_stats_pulse_count_returns_none_when_kuaiai_unavailable(self):
        auth = SimpleNamespace(tenant_id=TENANT, user=_user())
        with patch(
            "apps.common.optional_pro.pro_app_available",
            MagicMock(return_value=False),
        ):
            res = await ai_stats_pulse_count(ai_auth=auth)

        assert res == {"pulse_suggestion_count": None}
