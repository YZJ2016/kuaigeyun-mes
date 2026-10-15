"""KU-AI spec 184 单测：信任中心 + core stats 语义修复（全部 mock，不触真库）。

代码事实表（真实代码依据）：
- GET /operations/trust 双权限码经 require_permission_codes 闭包提取核对
  （同 test_spec183_corpus 的 _required_permissions 手法）；
- HITL 事实：agent_factory.build_agent(checkpointer=None)（agent_factory.py:22）
  + agent_assembler 固定传 checkpointer=None（agent_assembler.py:146），
  core/api/ai/router.py 无 propose/execute/approve/interrupt 端点；
- 审计：AiAuditMiddleware 覆盖 /api/v1/core/ai/**（core/ai/middleware.py:15），
  审计表 core_ai_audit_logs（core/models/ai_audit_log.py）；
- stats 缺陷修复：apps.kuaiai.services.suggestion_service 不存在（spec 182 以
  pulse registry 实现），原 _pulse_suggestion_count 恒回假 0；修复后为
  Optional[int]，缺失/失败回 None；by_day 改站点时区分桶（Asia/Shanghai）。
  上游提速后改名 `_pulse_suggestion_count_uncached` 并加 `get_overview` 的
  `include_pulse` 参数（默认 False → 响应回 0，不算 Pulse）。

覆盖：三卡状态闭集与文案真实性、当前用户权限（无 user_id 入参）、
HITL not_ready、审计不可用 partial、权限读取失败降级、错误脱敏、
路由双权限、stats pulse/day 语义回归。
"""

from __future__ import annotations

import inspect
import sys
import types
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.routing import APIRoute

import core.ai.stats_service as stats_svc
import core.utils.timezone_utils as tz_utils
from apps.kuaiai.api.router import router
from apps.kuaiai.schemas.operations import TrustOut
from apps.kuaiai.services import operations_service as ops_svc
from core.ai.stats_service import AiStatsService

TENANT = 7
USER_ID = 5


def _user(uid: int = USER_ID):
    return SimpleNamespace(
        id=uid,
        full_name="测试用户",
        username="tester",
        is_tenant_admin=False,
        is_infra_admin=False,
    )


def _qs(rows=()):
    """模拟 Tortoise QuerySet 链（filter → exists/count/all）。"""
    q = MagicMock()
    q.filter = MagicMock(return_value=q)
    q.order_by = MagicMock(return_value=q)
    q.exists = AsyncMock(return_value=bool(rows))
    q.count = AsyncMock(return_value=len(rows))
    q.all = AsyncMock(return_value=list(rows))
    return q


def _required_permissions(route: APIRoute):
    """从 require_permission_codes 依赖闭包中取出权限码。"""
    perms = set()
    for dep in route.dependencies or []:
        fn = getattr(dep, "dependency", None)
        closure = getattr(fn, "__closure__", None)
        if fn is None or closure is None:
            continue
        for name, cell in zip(fn.__code__.co_freevars, closure):
            if name == "codes":
                perms.update(cell.cell_contents or [])
    return perms


def _route_table():
    table = {}
    for r in router.routes:
        if not isinstance(r, APIRoute):
            continue
        for method in r.methods:
            table[(method, r.path)] = _required_permissions(r)
    return table


def _cards_by_key(out):
    return {c["key"]: c for c in out["cards"]}


# ============================================================ 路由注册


class TestTrustRouteRegistration:
    def test_trust_route_requires_both_codes(self):
        table = _route_table()
        key = ("GET", "/operations/trust")
        assert key in table, "路由未注册: GET /operations/trust"
        assert table[key] == {
            "kuaiai:entry:read",
            "kuaiai:trust:display",
        }

    def test_trust_handler_has_no_user_id_param(self):
        """不接收 user_id：签名中禁止出现该查询参数。"""
        from apps.kuaiai.api.operations import api_get_trust

        params = inspect.signature(api_get_trust).parameters
        assert "user_id" not in params

    def test_service_signature_has_no_user_id(self):
        sig = inspect.signature(ops_svc.get_trust)
        assert "user_id" not in sig.parameters


# ============================================================ get_trust 聚合


@pytest.mark.asyncio
class TestGetTrust:
    async def test_shape_and_status_closed_set(self):
        user = _user()
        with patch(
            "core.models.ai_audit_log.AiAuditLog.filter",
            MagicMock(return_value=_qs([SimpleNamespace(id=1)])),
        ), patch(
            "core.services.authorization.user_permission_service.UserPermissionService.is_admin_bypass",
            AsyncMock(return_value=False),
        ), patch(
            "core.services.authorization.user_permission_service.UserPermissionService.get_user_permissions",
            AsyncMock(return_value={"kuaiai:entry:read", "kuaiai:trust:display"}),
        ):
            out = await ops_svc.get_trust(TENANT, user)

        TrustOut.model_validate(out)
        assert set(out.keys()) == {"cards", "permissions", "hitl"}
        assert [c["key"] for c in out["cards"]] == ["rbac", "hitl", "audit"]
        for c in out["cards"]:
            assert c["status"] in {"ready", "partial", "not_ready"}
            assert isinstance(c["evidence"], list)

        cards = _cards_by_key(out)
        # RBAC：本请求已过双码鉴权 + 网关权限映射存在 → ready
        assert cards["rbac"]["status"] == "ready"
        assert any("kuaiai:trust:display" in e for e in cards["rbac"]["evidence"])
        # 审计：表可读 → ready
        assert cards["audit"]["status"] == "ready"

    async def test_hitl_always_not_ready_with_real_evidence(self):
        """checkpointer=None 且无门控端点 → HITL not_ready，文案未完成时态。"""
        user = _user()
        with patch(
            "core.models.ai_audit_log.AiAuditLog.filter",
            MagicMock(return_value=_qs([])),
        ), patch(
            "core.services.authorization.user_permission_service.UserPermissionService.is_admin_bypass",
            AsyncMock(return_value=False),
        ), patch(
            "core.services.authorization.user_permission_service.UserPermissionService.get_user_permissions",
            AsyncMock(return_value=set()),
        ):
            out = await ops_svc.get_trust(TENANT, user)

        cards = _cards_by_key(out)
        assert cards["hitl"]["status"] == "not_ready"
        assert out["hitl"] == {
            "implemented": False,
            "mode": "not_implemented",
        }
        desc = cards["hitl"]["description"] or ""
        assert "尚未接入" in desc
        assert "已完成" not in desc
        assert "propose" not in desc.lower() or "尚未" in desc

    async def test_permissions_current_user_only(self):
        """permissions[] 只反映当前用户持有状态；不枚举角色关系。"""
        user = _user()
        owned = {
            "kuaiai:entry:read",
            "kuaiai:trust:display",
            "kuaiai:act:execute",
        }
        with patch(
            "core.models.ai_audit_log.AiAuditLog.filter",
            MagicMock(return_value=_qs([])),
        ), patch(
            "core.services.authorization.user_permission_service.UserPermissionService.is_admin_bypass",
            AsyncMock(return_value=False),
        ), patch(
            "core.services.authorization.user_permission_service.UserPermissionService.get_user_permissions",
            AsyncMock(return_value=owned),
        ) as perms_mock:
            out = await ops_svc.get_trust(TENANT, user)

        perms_mock.assert_awaited_once_with(user_id=USER_ID, tenant_id=TENANT)
        by_code = {p["code"]: p["granted"] for p in out["permissions"]}
        assert set(by_code.keys()) == set(ops_svc.TRUST_PERMISSION_CODES)
        for code in ops_svc.TRUST_PERMISSION_CODES:
            assert by_code[code] == (code in owned)

    async def test_admin_bypass_marks_all_granted(self):
        user = _user()
        with patch(
            "core.models.ai_audit_log.AiAuditLog.filter",
            MagicMock(return_value=_qs([])),
        ), patch(
            "core.services.authorization.user_permission_service.UserPermissionService.is_admin_bypass",
            AsyncMock(return_value=True),
        ), patch(
            "core.services.authorization.user_permission_service.UserPermissionService.get_user_permissions",
            AsyncMock(return_value=set()),
        ) as perms_mock:
            out = await ops_svc.get_trust(TENANT, user)

        perms_mock.assert_not_awaited()
        assert all(p["granted"] for p in out["permissions"])

    async def test_audit_unavailable_partial_and_masked(self):
        """审计表查询异常 → partial；evidence 不回异常详情/路径。"""
        user = _user()
        boom = MagicMock(side_effect=RuntimeError("db down: /opt/secret/xx.py:42"))
        with patch(
            "core.models.ai_audit_log.AiAuditLog.filter", boom
        ), patch(
            "core.services.authorization.user_permission_service.UserPermissionService.is_admin_bypass",
            AsyncMock(return_value=False),
        ), patch(
            "core.services.authorization.user_permission_service.UserPermissionService.get_user_permissions",
            AsyncMock(return_value=set()),
        ):
            out = await ops_svc.get_trust(TENANT, user)

        cards = _cards_by_key(out)
        assert cards["audit"]["status"] == "partial"
        blob = " ".join(cards["audit"]["evidence"])
        assert "db down" not in blob
        assert "/opt/secret" not in blob
        assert "xx.py" not in blob

    async def test_permission_read_failure_degrades_to_false(self):
        user = _user()
        with patch(
            "core.models.ai_audit_log.AiAuditLog.filter",
            MagicMock(return_value=_qs([])),
        ), patch(
            "core.services.authorization.user_permission_service.UserPermissionService.is_admin_bypass",
            AsyncMock(side_effect=RuntimeError("perm store down")),
        ):
            out = await ops_svc.get_trust(TENANT, user)

        assert out["permissions"]
        assert all(p["granted"] is False for p in out["permissions"])

# ============================================================ stats_service 回归（T2）


class _LogRow:
    def __init__(self, *, created_at, latency_ms=None, capability=None):
        self.created_at = created_at
        self.latency_ms = latency_ms
        self.capability = capability


def _patch_audit_rows(rows):
    def _filter(**kwargs):
        # created_at__gte 过滤在 mock 层近似实现：直接返回全部行
        qs = _qs(rows)
        # 上游提速后改查聚合列 .values()，回 dict 序列
        qs.values = MagicMock(
            return_value=AsyncMock(
                return_value=[
                    {
                        "created_at": r.created_at,
                        "latency_ms": getattr(r, "latency_ms", None),
                        "capability": getattr(r, "capability", None),
                    }
                    for r in rows
                ]
            )()
        )
        return qs

    return patch(
        "core.models.ai_audit_log.AiAuditLog.filter",
        MagicMock(side_effect=_filter),
    )


@pytest.mark.asyncio
class TestStatsServiceSemantics:
    async def test_pulse_count_none_when_suggestion_service_missing(self):
        """apps.kuaiai.services.suggestion_service 不存在 → None（非假 0）。"""
        assert (
            "apps.kuaiai.services.suggestion_service" not in sys.modules
        )
        count = await AiStatsService._pulse_suggestion_count_uncached(TENANT)
        assert count is None

    async def test_pulse_count_none_when_service_raises(self):
        fake_mod = types.ModuleType("apps.kuaiai.services.suggestion_service")

        class _Boom:
            async def get_pulse_suggestions(self, tenant_id):
                raise RuntimeError("boom")

        fake_mod.SuggestionService = _Boom
        with patch.dict(
            sys.modules,
            {"apps.kuaiai.services.suggestion_service": fake_mod},
        ):
            count = await AiStatsService._pulse_suggestion_count_uncached(TENANT)
        assert count is None

    async def test_pulse_count_real_value_when_service_exists(self):
        fake_mod = types.ModuleType("apps.kuaiai.services.suggestion_service")

        class _Svc:
            async def get_pulse_suggestions(self, tenant_id):
                return [{"id": 1}, {"id": 2}]

        fake_mod.SuggestionService = _Svc
        with patch.dict(
            sys.modules,
            {"apps.kuaiai.services.suggestion_service": fake_mod},
        ):
            count = await AiStatsService._pulse_suggestion_count_uncached(TENANT)
        assert count == 2

    async def test_by_day_buckets_use_site_timezone(self):
        """站点次日 00:30（UTC 仍属前一日）→ 记入站点次日桶，不记前一日。"""
        sh = ZoneInfo("Asia/Shanghai")
        site_today = tz_utils.to_site_date(datetime.now(timezone.utc))
        row = _LogRow(
            created_at=datetime(
                site_today.year, site_today.month, site_today.day,
                0, 30, tzinfo=sh,
            ).astimezone(timezone.utc),
            latency_ms=10,
            capability="chat",
        )
        with _patch_audit_rows([row]):
            out = await AiStatsService.get_overview(tenant_id=TENANT, days=7)

        day_map = {d.day: d.count for d in out.by_day}
        assert day_map.get(site_today.isoformat()) == 1
        prev_day = (site_today - timedelta(days=1)).isoformat()
        assert day_map.get(prev_day, 0) == 0
        # by_day 覆盖连续站点日期序列，缺失日为 0
        days = [d.day for d in out.by_day]
        assert days == sorted(days)
        assert days[-1] == site_today.isoformat()
        assert len(set(days)) == len(days)

    async def test_overview_pulse_none_empty_reason_and_naive_created_at(self):
        """naive created_at 按 UTC 解释（Tortoise USE_TZ 口径）。"""
        sh = ZoneInfo("Asia/Shanghai")
        site_today = tz_utils.to_site_date(datetime.now(timezone.utc))
        aware_sh = datetime(
            site_today.year, site_today.month, site_today.day,
            0, 30, tzinfo=sh,
        )
        # 同一瞬时的 naive UTC（模拟 Tortoise USE_TZ 落库口径）
        row = _LogRow(
            created_at=aware_sh.astimezone(timezone.utc).replace(tzinfo=None)
        )
        with _patch_audit_rows([row]):
            stats_svc._PULSE_COUNT_CACHE.clear()
            out = await AiStatsService.get_overview(
                tenant_id=TENANT, days=7, include_pulse=True
            )
        day_map = {d.day: d.count for d in out.by_day}
        assert day_map.get(site_today.isoformat()) == 1
        # pulse 数据源缺失 → None
        assert out.pulse_suggestion_count is None
        assert out.total_calls == 1
        assert out.empty_reason is None

    async def test_empty_overview_has_reason_and_none_pulse(self):
        with _patch_audit_rows([]):
            stats_svc._PULSE_COUNT_CACHE.clear()
            out = await AiStatsService.get_overview(
                tenant_id=TENANT, days=7, include_pulse=True
            )
        assert out.total_calls == 0
        assert out.empty_reason
        assert out.pulse_suggestion_count is None
        # 空结果仍回完整日期序列
        assert len(out.by_day) >= 7
        assert all(d.count == 0 for d in out.by_day)
