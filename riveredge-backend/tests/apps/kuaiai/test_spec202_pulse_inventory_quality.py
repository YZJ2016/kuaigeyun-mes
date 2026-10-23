"""KU-AI spec 202 单测：Pulse 库存预警 + 质量异常 detector（全部 mock，不触真库）。

代码事实表（写死在本测试固定边界的真实代码依据）：
- InventoryAlert.status 闭集 pending/processing/resolved/ignored
  （models/inventory_alert.py:183）；未处理闭集 =
  document_action_policy.inventory_alert._HANDLEABLE_STATUSES
  （pending/processing）；
- InventoryAlert.alert_level 闭集 info/warning/critical（:179）；
- 预警读权限 kuaizhizao:warehouse-management-inventory-alert:read / 数据范围
  kuaizhizao:warehouse-management-inventory-alert / 路由
  /apps/kuaizhizao/warehouse-management/inventory-alert（manifest 菜单）；
- QualityException.status 未闭环闭集 =
  exception_service.ACTIVE_QUALITY_EXCEPTION_STATUSES
  （pending/investigating/correcting）；终态 closed/cancelled
  （kitting_exceptions._QUALITY_STATUSES、handle 落地值 closed）；
- QualityException.severity 闭集 minor/major/critical
  （exception_service._normalize_severity allowed）；
- 质量读权限 kuaizhizao:production-execution-quality-exceptions:read / 数据
  范围 kuaizhizao:production-execution-quality-exceptions / 路由
  /apps/kuaizhizao/production-execution/quality-exceptions
  （manifest + SCENE_ROUTE_PERMISSIONS 白名单）。

覆盖：严重度/优先级逐值矩阵、状态闭集钉死、权限失败关闭零泄露、租户隔离、
数据范围资源键、200 条批次扫描、空候选、registry 注册与逐域权限失败隔离。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch
from zoneinfo import ZoneInfo

import pytest

import core.utils.timezone_utils as tz_utils
from apps.kuaiai.schemas.pulse import PulseItemOut
from apps.kuaiai.services.pulse import registry as pulse_registry
from apps.kuaiai.services.pulse.base import (
    PulseContext,
    PulsePermissionDenied,
)
from apps.kuaiai.services.pulse.inventory import (
    UNRESOLVED_ALERT_STATUSES,
    InventoryAlertDetector,
)
from apps.kuaiai.services.pulse.quality import QualityExceptionDetector

TENANT = 7
USER_ID = 5
SH = ZoneInfo("Asia/Shanghai")
# 固定业务时刻：UTC 2026-01-09 16:30 → 上海 2026-01-10 00:30
FIXED_NOW = datetime(2026, 1, 9, 16, 30, tzinfo=timezone.utc)
TODAY = date(2026, 1, 10)


def _user(uid: int = USER_ID):
    return SimpleNamespace(id=uid, full_name="测试用户", username="tester")


def _ctx(tenant_id: int = TENANT, user=None):
    return PulseContext(
        tenant_id=tenant_id,
        user=user if user is not None else _user(),
        now=FIXED_NOW,
        today=TODAY,
    )


def _qs(rows=()):
    """模拟 Tortoise QuerySet 链（filter/exclude/order_by/limit → all）。"""
    q = MagicMock()
    for m in ("filter", "exclude", "order_by", "limit", "offset"):
        setattr(q, m, MagicMock(return_value=q))
    q.all = AsyncMock(return_value=list(rows))
    return q


def _paged_qs(rows):
    """模拟 offset/limit 分批读取，保留调用记录供批次边界断言。"""
    q = _qs([])

    async def _all():
        offset = q.offset.call_args.args[0] if q.offset.call_args else 0
        limit = q.limit.call_args.args[0] if q.limit.call_args else len(rows)
        return list(rows[offset : offset + limit])

    q.all = AsyncMock(side_effect=_all)
    return q


def _alert(**kw):
    base = dict(
        id=301,
        uuid="alert-uuid-1",
        alert_type="low_stock",
        material_id=11,
        material_code="M-001",
        material_name="物料一",
        warehouse_id=21,
        warehouse_name="原料仓",
        current_quantity=5,
        threshold_value=10,
        alert_level="warning",
        alert_message="低库存预警",
        status="pending",
        triggered_at=datetime(2026, 1, 9, 8, 0),
        deleted_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _qexc(**kw):
    base = dict(
        id=401,
        uuid="qe-uuid-1",
        exception_type="inspection_failure",
        work_order_id=51,
        work_order_code="WO-051",
        material_id=11,
        material_code="M-001",
        material_name="物料一",
        batch_no="B-01",
        problem_description="来料尺寸超差",
        severity="major",
        status="pending",
        created_at=datetime(2026, 1, 9, 9, 0),
        deleted_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch):
    """固定站点时区与业务时刻（所有脉冲测试共享同一业务日）。"""
    monkeypatch.setattr(
        tz_utils,
        "resolve_business_datetime",
        lambda value=None: FIXED_NOW
        if value is None
        else tz_utils.coerce_business_datetime_to_utc(value),
    )
    monkeypatch.setattr(tz_utils, "site_timezone_name", lambda: "Asia/Shanghai")

    def _to_site(dt):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(SH)

    monkeypatch.setattr(tz_utils, "to_site_timezone", _to_site)


@pytest.fixture
def perm_ok(monkeypatch):
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "core.services.authorization.user_permission_service."
        "UserPermissionService.has_permission",
        mock,
    )
    return mock


@pytest.fixture
def scope_passthrough(monkeypatch):
    mock = AsyncMock(side_effect=lambda qs, **kw: qs)
    monkeypatch.setattr(
        "core.services.authorization.data_scope_service."
        "DataScopeService.apply",
        mock,
    )
    return mock


# ============================================================ 库存预警 detector


class TestInventoryAlertDetector:
    def _patch(self, monkeypatch, rows):
        qs = _qs(rows)
        mock_filter = MagicMock(return_value=qs)
        monkeypatch.setattr(
            "apps.kuaizhizao.models.inventory_alert.InventoryAlert.filter",
            mock_filter,
        )
        return qs, mock_filter

    @pytest.mark.asyncio
    async def test_pending_alert_produces_item(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        self._patch(monkeypatch, [_alert()])
        items = await InventoryAlertDetector().detect(_ctx())
        assert len(items) == 1
        it = items[0]
        assert it.domain == "inventory"
        assert it.rule_code == "inventory_alert"
        assert it.id == "inventory:inventory_alert:301"
        assert it.severity == "warning" and it.priority == "medium"
        assert it.resource_type == "inventory_alert"
        assert it.resource_id == "301"
        assert it.resource_uuid == "alert-uuid-1"
        assert it.route == "/apps/kuaizhizao/warehouse-management/inventory-alert"
        assert "M-001" in it.fact and "原料仓" in it.fact
        assert it.detected_at == FIXED_NOW

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("alert_level", "severity", "priority"),
        (
            ("critical", "critical", "high"),
            ("warning", "warning", "medium"),
            ("info", "info", "low"),
            ("bogus", "warning", "medium"),  # 未知值兜底，不臆造级别
        ),
    )
    async def test_severity_matrix(
        self,
        alert_level,
        severity,
        priority,
        perm_ok,
        scope_passthrough,
        monkeypatch,
    ):
        self._patch(monkeypatch, [_alert(alert_level=alert_level)])
        items = await InventoryAlertDetector().detect(_ctx())
        assert items[0].severity == severity
        assert items[0].priority == priority

    @pytest.mark.asyncio
    async def test_unresolved_status_closed_set_pinned(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        """未处理闭集须与 document_action_policy 可处理闭集一致并下发 DB。"""
        qs, mock_filter = self._patch(monkeypatch, [])
        await InventoryAlertDetector().detect(_ctx())
        from apps.kuaizhizao.services.document_action_policy.inventory_alert import (
            _HANDLEABLE_STATUSES,
        )

        assert set(UNRESOLVED_ALERT_STATUSES) == set(_HANDLEABLE_STATUSES)
        kwargs = mock_filter.call_args.kwargs
        assert kwargs["tenant_id"] == TENANT
        assert kwargs["deleted_at__isnull"] is True
        assert sorted(kwargs["status__in"]) == ["pending", "processing"]
        qs.all.assert_awaited_once()  # 单查询，无逐卡 N+1

    @pytest.mark.asyncio
    async def test_resolved_ignored_not_in_candidates(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        qs, mock_filter = self._patch(monkeypatch, [])
        await InventoryAlertDetector().detect(_ctx())
        assert "resolved" not in mock_filter.call_args.kwargs["status__in"]
        assert "ignored" not in mock_filter.call_args.kwargs["status__in"]

    @pytest.mark.asyncio
    async def test_scans_in_bounded_batches(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        rows = [
            _alert(id=i + 1, uuid=f"a-{i + 1}") for i in range(250)
        ]
        qs = _paged_qs(rows)
        monkeypatch.setattr(
            "apps.kuaizhizao.models.inventory_alert.InventoryAlert.filter",
            MagicMock(return_value=qs),
        )
        items = await InventoryAlertDetector().detect(_ctx())
        assert len(items) == 250
        assert qs.limit.call_args_list == [call(200), call(200)]
        assert qs.offset.call_args_list == [call(0), call(200)]

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        self._patch(monkeypatch, [])
        assert await InventoryAlertDetector().detect(_ctx()) == []

    @pytest.mark.asyncio
    async def test_no_permission_denies_and_leaks_nothing(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        perm_ok.return_value = False
        mock_filter = MagicMock()
        monkeypatch.setattr(
            "apps.kuaizhizao.models.inventory_alert.InventoryAlert.filter",
            mock_filter,
        )
        with pytest.raises(PulsePermissionDenied):
            await InventoryAlertDetector().detect(_ctx())
        mock_filter.assert_not_called()  # 未发起任何领域查询
        scope_passthrough.assert_not_called()

    @pytest.mark.asyncio
    async def test_permission_anchor_pinned(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        self._patch(monkeypatch, [])
        await InventoryAlertDetector().detect(_ctx())
        perm_ok.assert_awaited_once_with(
            USER_ID,
            TENANT,
            "kuaizhizao:warehouse-management-inventory-alert:read",
        )
        assert (
            scope_passthrough.call_args.kwargs["resource"]
            == "kuaizhizao:warehouse-management-inventory-alert"
        )

    @pytest.mark.asyncio
    async def test_tenant_id_carried(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        _qs_obj, mock_filter = self._patch(monkeypatch, [])
        await InventoryAlertDetector().detect(_ctx(tenant_id=42))
        assert mock_filter.call_args.kwargs["tenant_id"] == 42


# ============================================================ 质量异常 detector


class TestQualityExceptionDetector:
    def _patch(self, monkeypatch, rows):
        qs = _qs(rows)
        mock_filter = MagicMock(return_value=qs)
        monkeypatch.setattr(
            "apps.kuaizhizao.models.quality_exception.QualityException.filter",
            mock_filter,
        )
        return qs, mock_filter

    @pytest.mark.asyncio
    async def test_open_exception_produces_item(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        self._patch(monkeypatch, [_qexc()])
        items = await QualityExceptionDetector().detect(_ctx())
        assert len(items) == 1
        it = items[0]
        assert it.domain == "quality"
        assert it.rule_code == "quality_exception"
        assert it.id == "quality:quality_exception:401"
        assert it.severity == "error" and it.priority == "high"
        assert it.resource_type == "quality_exception"
        assert it.resource_id == "401"
        assert it.resource_uuid == "qe-uuid-1"
        assert (
            it.route
            == "/apps/kuaizhizao/production-execution/quality-exceptions"
        )
        assert "WO-051" in it.fact and "来料尺寸超差" in it.fact
        assert it.detected_at == FIXED_NOW

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("severity_in", "severity", "priority"),
        (
            ("critical", "critical", "high"),
            ("major", "error", "high"),
            ("minor", "warning", "medium"),
            ("bogus", "warning", "medium"),  # 未知值兜底，不臆造级别
        ),
    )
    async def test_severity_matrix(
        self,
        severity_in,
        severity,
        priority,
        perm_ok,
        scope_passthrough,
        monkeypatch,
    ):
        self._patch(monkeypatch, [_qexc(severity=severity_in)])
        items = await QualityExceptionDetector().detect(_ctx())
        assert items[0].severity == severity
        assert items[0].priority == priority

    @pytest.mark.asyncio
    async def test_open_status_closed_set_pinned(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        """未闭环闭集须原样下发 ACTIVE_QUALITY_EXCEPTION_STATUSES。"""
        qs, mock_filter = self._patch(monkeypatch, [])
        await QualityExceptionDetector().detect(_ctx())
        from apps.kuaizhizao.services.exception_service import (
            ACTIVE_QUALITY_EXCEPTION_STATUSES,
        )

        kwargs = mock_filter.call_args.kwargs
        assert kwargs["tenant_id"] == TENANT
        assert kwargs["deleted_at__isnull"] is True
        assert kwargs["status__in"] == list(ACTIVE_QUALITY_EXCEPTION_STATUSES)
        assert sorted(kwargs["status__in"]) == [
            "correcting",
            "investigating",
            "pending",
        ]
        assert "closed" not in kwargs["status__in"]
        assert "cancelled" not in kwargs["status__in"]
        qs.all.assert_awaited_once()  # 单查询，无逐卡 N+1

    @pytest.mark.asyncio
    async def test_scans_in_bounded_batches(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        rows = [
            _qexc(id=i + 1, uuid=f"qe-{i + 1}") for i in range(250)
        ]
        qs = _paged_qs(rows)
        monkeypatch.setattr(
            "apps.kuaizhizao.models.quality_exception.QualityException.filter",
            MagicMock(return_value=qs),
        )
        items = await QualityExceptionDetector().detect(_ctx())
        assert len(items) == 250
        assert qs.limit.call_args_list == [call(200), call(200)]
        assert qs.offset.call_args_list == [call(0), call(200)]

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        self._patch(monkeypatch, [])
        assert await QualityExceptionDetector().detect(_ctx()) == []

    @pytest.mark.asyncio
    async def test_no_permission_denies_and_leaks_nothing(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        perm_ok.return_value = False
        mock_filter = MagicMock()
        monkeypatch.setattr(
            "apps.kuaizhizao.models.quality_exception.QualityException.filter",
            mock_filter,
        )
        with pytest.raises(PulsePermissionDenied):
            await QualityExceptionDetector().detect(_ctx())
        mock_filter.assert_not_called()
        scope_passthrough.assert_not_called()

    @pytest.mark.asyncio
    async def test_permission_anchor_pinned(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        self._patch(monkeypatch, [])
        await QualityExceptionDetector().detect(_ctx())
        perm_ok.assert_awaited_once_with(
            USER_ID,
            TENANT,
            "kuaizhizao:production-execution-quality-exceptions:read",
        )
        assert (
            scope_passthrough.call_args.kwargs["resource"]
            == "kuaizhizao:production-execution-quality-exceptions"
        )

    @pytest.mark.asyncio
    async def test_tenant_id_carried(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        _qs_obj, mock_filter = self._patch(monkeypatch, [])
        await QualityExceptionDetector().detect(_ctx(tenant_id=42))
        assert mock_filter.call_args.kwargs["tenant_id"] == 42


# ============================================================ registry 注册与逐域权限


class TestSpec202Registry:
    def test_detectors_registered(self):
        assert isinstance(
            pulse_registry.DETECTORS["inventory"], InventoryAlertDetector
        )
        assert isinstance(
            pulse_registry.DETECTORS["quality"], QualityExceptionDetector
        )
        assert {"inventory", "quality"} <= set(
            pulse_registry.IMPLEMENTED_DOMAINS
        )

    @pytest.mark.asyncio
    async def test_domain_permission_denied_isolated(
        self, monkeypatch, scope_passthrough
    ):
        """仅 inventory 无权限：该域 permission_denied、complete=false，
        quality 正常产出且 summary 不含失败域。"""
        denied_code = "kuaizhizao:warehouse-management-inventory-alert:read"

        async def _perm(uid, tenant_id, code):
            return code != denied_code

        monkeypatch.setattr(
            "core.services.authorization.user_permission_service."
            "UserPermissionService.has_permission",
            AsyncMock(side_effect=_perm),
        )
        monkeypatch.setattr(
            "apps.kuaizhizao.models.inventory_alert.InventoryAlert.filter",
            MagicMock(return_value=_qs([_alert()])),
        )
        monkeypatch.setattr(
            "apps.kuaizhizao.models.quality_exception.QualityException.filter",
            MagicMock(return_value=_qs([_qexc(severity="critical")])),
        )

        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["inventory", "quality"]
        )
        assert out.complete is False
        assert out.summary.total == 1
        codes = {e.domain: e.code for e in out.errors}
        assert codes["inventory"] == "permission_denied"
        assert "quality" not in codes
        assert out.groups[0].domain == "quality"

    @pytest.mark.asyncio
    async def test_requested_domains_no_longer_not_connected(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        """inventory/quality 接入后，请求两域不再返回 not_connected。"""
        monkeypatch.setattr(
            "apps.kuaizhizao.models.inventory_alert.InventoryAlert.filter",
            MagicMock(return_value=_qs([])),
        )
        monkeypatch.setattr(
            "apps.kuaizhizao.models.quality_exception.QualityException.filter",
            MagicMock(return_value=_qs([])),
        )
        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["inventory", "quality"]
        )
        assert out.complete is True
        assert out.errors == []
