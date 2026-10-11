"""KU-AI spec 182 单测：Pulse detector 框架 + 生产/销售规则（全部 mock，不触真库）。

代码事实表（写死在本测试固定边界的真实代码依据）：
- WorkOrder.status 延期排除闭集 = work_order_service.WORK_ORDER_DELAY_EXCLUDED_STATUSES
  （completed/已完成/COMPLETED/cancelled/已取消/CANCELLED/split/已拆分/SPLIT），
  work_order_service.py:521；
- WorkOrder.planned_end_date DatetimeField 可空，naive 视作站点墙钟
  （work_order_service._normalize_naive_local_datetime 口径），work_order.py:154；
- 工单读权限 kuaizhizao:work-order:read / 数据范围 kuaizhizao:work-order /
  路由 /apps/kuaizhizao/production-execution/work-orders（kuaizhizao manifest）；
- SalesOrder.delivery_date DateField 必填；履约终态对齐
  SalesOrderService._is_terminal_business_status
  （closed/completed/cancelled/rejected + 存量别名），sales_order.py:33/47；
- 销售读权限 kuaizhizao:sales-order:read / 数据范围 kuaizhizao:sales-order /
  路由 /apps/kuaizhizao/sales-management/sales-orders；
- 阈值 TenantService.get_tenant_config → infra_tenant_configs.config_value
  .warning_days，非布尔 int 0..365，回落 3（tenant_service.py:866）。

覆盖：今天/昨天/未来交期、阈值缺省/非法/0/3/365/读取失败、完成/关闭态、
空日期、重复资源去重、跨租户、无权限泄露检查、单 detector 超时、
去重+稳定排序、summary 排除失败领域、分页边界、422 参数校验、N+1（
单 detector 恰好一次过滤查询）。
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

import core.utils.timezone_utils as tz_utils
from apps.kuaiai.schemas.pulse import PulseItemOut
from apps.kuaiai.services.pulse import registry as pulse_registry
from apps.kuaiai.services.pulse.base import (
    PulseContext,
    PulsePermissionDenied,
)
from apps.kuaiai.services.pulse.production import ProductionDelayDetector
from apps.kuaiai.services.pulse.sales import (
    DEFAULT_WARNING_DAYS,
    SALES_TERMINAL_STATUSES,
    SalesDeliveryRiskDetector,
)

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


def _wo(**kw):
    base = dict(
        id=101,
        uuid="wo-uuid-1",
        code="WO-001",
        name="工单一",
        status="in_progress",
        priority="normal",
        planned_end_date=datetime(2026, 1, 9, 18, 0),  # 站点墙钟 naive
        quantity=100,
        completed_quantity=40,
        deleted_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _so(**kw):
    base = dict(
        id=201,
        uuid="so-uuid-1",
        order_code="SO-001",
        status="AUDITED",
        is_active=True,
        delivery_date=TODAY,
        deleted_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _item(**kw):
    base = dict(
        id="production:production.delay:101",
        domain="production",
        severity="warning",
        priority="medium",
        title="t",
        fact="f",
        suggestion="s",
        resource_type="work_order",
        resource_id="101",
        resource_uuid="u",
        route="/apps/kuaizhizao/production-execution/work-orders",
        detected_at=FIXED_NOW,
        rule_code="production.delay",
    )
    base.update(kw)
    return PulseItemOut(**base)


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


# ============================================================ 生产延期 detector


class TestProductionDelayDetector:
    @pytest.mark.asyncio
    async def test_overdue_7_days_is_critical_high(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        qs = _qs([_wo(planned_end_date=datetime(2026, 1, 3, 23, 59))])
        monkeypatch.setattr(
            "apps.kuaizhizao.models.work_order.WorkOrder.filter",
            MagicMock(return_value=qs),
        )
        items = await ProductionDelayDetector().detect(_ctx())
        assert len(items) == 1
        it = items[0]
        assert it.severity == "critical" and it.priority == "high"
        assert "已逾期 7 天" in it.fact
        assert it.domain == "production"
        assert it.rule_code == "production.delay"
        assert it.resource_type == "work_order"
        assert it.resource_id == "101"
        assert it.resource_uuid == "wo-uuid-1"
        assert it.route == "/apps/kuaizhizao/production-execution/work-orders"

    @pytest.mark.asyncio
    async def test_overdue_3_days_is_error(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        qs = _qs([_wo(planned_end_date=datetime(2026, 1, 7, 0, 0))])
        monkeypatch.setattr(
            "apps.kuaizhizao.models.work_order.WorkOrder.filter",
            MagicMock(return_value=qs),
        )
        items = await ProductionDelayDetector().detect(_ctx())
        assert items[0].severity == "error"
        assert "已逾期 3 天" in items[0].fact

    @pytest.mark.asyncio
    async def test_planned_earlier_today_reports_elapsed_not_one_day(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        # 计划今日 08:00（已过站点 00:30 之后？用 00:00 确保早于 now 00:30）
        qs = _qs(
            [
                _wo(
                    planned_end_date=datetime(2026, 1, 10, 0, 0),
                    priority="urgent",
                )
            ]
        )
        monkeypatch.setattr(
            "apps.kuaizhizao.models.work_order.WorkOrder.filter",
            MagicMock(return_value=qs),
        )
        items = await ProductionDelayDetector().detect(_ctx())
        assert items[0].severity == "warning"
        assert items[0].priority == "high"  # 工单自身 urgent → priority 升档
        assert "今日已逾时" in items[0].fact
        assert "已逾期 1 天" not in items[0].fact

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("row_count", "expected_batches"),
        ((200, 2), (201, 2), (400, 3), (401, 3)),
    )
    async def test_scans_production_in_bounded_batches(
        self,
        row_count,
        expected_batches,
        perm_ok,
        scope_passthrough,
        monkeypatch,
    ):
        rows = [
            _wo(
                id=i + 1,
                uuid=f"wo-{i + 1}",
                code=f"WO-{i + 1:03d}",
            )
            for i in range(row_count)
        ]
        qs = _paged_qs(rows)
        monkeypatch.setattr(
            "apps.kuaizhizao.models.work_order.WorkOrder.filter",
            MagicMock(return_value=qs),
        )

        items = await ProductionDelayDetector().detect(_ctx())

        assert len(items) == row_count
        assert qs.limit.call_args_list == [
            call(200) for _ in range(expected_batches)
        ]
        assert qs.offset.call_args_list == [
            call(i * 200) for i in range(expected_batches)
        ]

    @pytest.mark.asyncio
    async def test_terminal_status_closed_set_pinned(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        """完成/取消/拆分闭集必须以真实常量下发到 DB exclude（T1 代码事实）。"""
        qs = _qs([])
        mock_filter = MagicMock(return_value=qs)
        monkeypatch.setattr(
            "apps.kuaizhizao.models.work_order.WorkOrder.filter", mock_filter
        )
        await ProductionDelayDetector().detect(_ctx())
        from apps.kuaizhizao.services.work_order_service import (
            WORK_ORDER_DELAY_EXCLUDED_STATUSES,
        )

        mock_filter.assert_called_once()
        kwargs = mock_filter.call_args.kwargs
        assert kwargs["tenant_id"] == TENANT
        assert kwargs["deleted_at__isnull"] is True
        assert kwargs["planned_end_date__isnull"] is False
        assert "planned_end_date__lt" in kwargs
        qs.exclude.assert_called_once_with(
            status__in=list(WORK_ORDER_DELAY_EXCLUDED_STATUSES)
        )
        qs.limit.assert_called_once_with(200)
        qs.all.assert_awaited_once()  # 单查询，无逐卡 N+1

    @pytest.mark.asyncio
    async def test_future_planned_end_skipped_in_python(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        qs = _qs([_wo(planned_end_date=datetime(2026, 1, 11, 0, 0))])
        monkeypatch.setattr(
            "apps.kuaizhizao.models.work_order.WorkOrder.filter",
            MagicMock(return_value=qs),
        )
        items = await ProductionDelayDetector().detect(_ctx())
        assert items == []

    @pytest.mark.asyncio
    async def test_null_planned_end_skipped(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        qs = _qs([_wo(planned_end_date=None)])
        monkeypatch.setattr(
            "apps.kuaizhizao.models.work_order.WorkOrder.filter",
            MagicMock(return_value=qs),
        )
        items = await ProductionDelayDetector().detect(_ctx())
        assert items == []

    @pytest.mark.asyncio
    async def test_no_permission_denies_and_leaks_nothing(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        perm_ok.return_value = False
        mock_filter = MagicMock()
        monkeypatch.setattr(
            "apps.kuaizhizao.models.work_order.WorkOrder.filter", mock_filter
        )
        with pytest.raises(PulsePermissionDenied):
            await ProductionDelayDetector().detect(_ctx())
        mock_filter.assert_not_called()  # 未发起任何领域查询

    @pytest.mark.asyncio
    async def test_tenant_id_carried(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        qs = _qs([])
        mock_filter = MagicMock(return_value=qs)
        monkeypatch.setattr(
            "apps.kuaizhizao.models.work_order.WorkOrder.filter", mock_filter
        )
        await ProductionDelayDetector().detect(_ctx(tenant_id=42))
        assert mock_filter.call_args.kwargs["tenant_id"] == 42


# ============================================================ 销售交期 detector


class TestSalesDeliveryRiskDetector:
    def _patch_order(self, monkeypatch, rows):
        qs = _qs(rows)
        mock_filter = MagicMock(return_value=qs)
        monkeypatch.setattr(
            "apps.kuaizhizao.models.sales_order.SalesOrder.filter", mock_filter
        )
        return qs, mock_filter

    def _patch_config(self, monkeypatch, config):
        mock = AsyncMock(return_value=config)
        monkeypatch.setattr(
            "infra.services.tenant_service.TenantService.get_tenant_config",
            mock,
        )
        return mock

    @pytest.mark.asyncio
    async def test_due_today_is_error_high(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        self._patch_order(monkeypatch, [_so(delivery_date=TODAY)])
        self._patch_config(monkeypatch, None)
        items = await SalesDeliveryRiskDetector().detect(_ctx())
        assert items[0].severity == "error" and items[0].priority == "high"
        assert "今日到期" in items[0].fact

    @pytest.mark.asyncio
    async def test_scans_sales_over_200_in_bounded_batches(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        rows = [
            _so(
                id=i + 1,
                uuid=f"so-{i + 1}",
                order_code=f"SO-{i + 1:03d}",
            )
            for i in range(250)
        ]
        qs = _paged_qs(rows)
        monkeypatch.setattr(
            "apps.kuaizhizao.models.sales_order.SalesOrder.filter",
            MagicMock(return_value=qs),
        )
        self._patch_config(monkeypatch, None)

        items = await SalesDeliveryRiskDetector().detect(_ctx())

        assert len(items) == 250
        assert qs.limit.call_args_list == [call(200), call(200)]
        assert qs.offset.call_args_list == [call(0), call(200)]

    @pytest.mark.asyncio
    async def test_cancellation_stops_sales_batch_scan(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        rows = [_so(id=i + 1, uuid=f"so-{i + 1}") for i in range(200)]
        second_batch_started = asyncio.Event()
        release_second_batch = asyncio.Event()
        qs = _qs([])

        async def paged_all():
            if qs.all.await_count == 1:
                return rows
            second_batch_started.set()
            await release_second_batch.wait()
            return []

        qs.all = AsyncMock(side_effect=paged_all)
        monkeypatch.setattr(
            "apps.kuaizhizao.models.sales_order.SalesOrder.filter",
            MagicMock(return_value=qs),
        )
        self._patch_config(monkeypatch, None)

        task = asyncio.create_task(SalesDeliveryRiskDetector().detect(_ctx()))
        await second_batch_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert qs.all.await_count == 2

    @pytest.mark.asyncio
    async def test_overdue_yesterday_is_error(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        self._patch_order(
            monkeypatch, [_so(delivery_date=TODAY - timedelta(days=1))]
        )
        self._patch_config(monkeypatch, None)
        items = await SalesDeliveryRiskDetector().detect(_ctx())
        assert items[0].severity == "error"
        assert "已逾期 1 天" in items[0].fact

    @pytest.mark.asyncio
    async def test_overdue_7_plus_is_critical(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        self._patch_order(
            monkeypatch, [_so(delivery_date=TODAY - timedelta(days=8))]
        )
        self._patch_config(monkeypatch, None)
        items = await SalesDeliveryRiskDetector().detect(_ctx())
        assert items[0].severity == "critical"

    @pytest.mark.asyncio
    async def test_due_within_threshold_is_warning(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        self._patch_order(
            monkeypatch, [_so(delivery_date=TODAY + timedelta(days=3))]
        )
        self._patch_config(monkeypatch, None)  # 未配置 → 默认 3
        items = await SalesDeliveryRiskDetector().detect(_ctx())
        assert items[0].severity == "warning"
        assert items[0].priority == "medium"
        assert "距交期 3 天" in items[0].fact

    @pytest.mark.asyncio
    async def test_threshold_default_3_when_config_missing(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        qs, mock_filter = self._patch_order(monkeypatch, [])
        cfg = self._patch_config(monkeypatch, None)
        await SalesDeliveryRiskDetector().detect(_ctx())
        cfg.assert_awaited_once_with(TENANT, "kuaiai.pulse.sales_delivery_risk")
        kwargs = mock_filter.call_args.kwargs
        assert kwargs["delivery_date__lte"] == TODAY + timedelta(
            days=DEFAULT_WARNING_DAYS
        )
        assert kwargs["is_active"] is True
        assert kwargs["tenant_id"] == TENANT
        qs.exclude.assert_called_once_with(
            status__in=list(SALES_TERMINAL_STATUSES)
        )
        qs.all.assert_awaited_once()  # 单查询，无逐卡 N+1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("days", [0, 3, 365])
    async def test_threshold_valid_values(
        self, perm_ok, scope_passthrough, monkeypatch, days
    ):
        _qs_obj, mock_filter = self._patch_order(monkeypatch, [])
        self._patch_config(
            monkeypatch,
            SimpleNamespace(config_value={"warning_days": days}),
        )
        await SalesDeliveryRiskDetector().detect(_ctx())
        assert mock_filter.call_args.kwargs[
            "delivery_date__lte"
        ] == TODAY + timedelta(days=days)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_value",
        ["3", True, -1, 366, 1.5, None],
    )
    async def test_threshold_invalid_falls_back_3(
        self, perm_ok, scope_passthrough, monkeypatch, bad_value
    ):
        _qs_obj, mock_filter = self._patch_order(monkeypatch, [])
        self._patch_config(
            monkeypatch,
            SimpleNamespace(config_value={"warning_days": bad_value}),
        )
        await SalesDeliveryRiskDetector().detect(_ctx())
        assert mock_filter.call_args.kwargs[
            "delivery_date__lte"
        ] == TODAY + timedelta(days=3)

    @pytest.mark.asyncio
    async def test_threshold_config_value_not_dict(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        _qs_obj, mock_filter = self._patch_order(monkeypatch, [])
        self._patch_config(
            monkeypatch, SimpleNamespace(config_value="oops")
        )
        await SalesDeliveryRiskDetector().detect(_ctx())
        assert mock_filter.call_args.kwargs[
            "delivery_date__lte"
        ] == TODAY + timedelta(days=3)

    @pytest.mark.asyncio
    async def test_config_read_failure_is_detector_failure(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        mock_filter = MagicMock()
        monkeypatch.setattr(
            "apps.kuaizhizao.models.sales_order.SalesOrder.filter", mock_filter
        )
        monkeypatch.setattr(
            "infra.services.tenant_service.TenantService.get_tenant_config",
            AsyncMock(side_effect=RuntimeError("db down")),
        )
        with pytest.raises(RuntimeError):
            await SalesDeliveryRiskDetector().detect(_ctx())
        mock_filter.assert_not_called()  # 不伪装默认业务事实

    @pytest.mark.asyncio
    async def test_terminal_status_not_returned(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        """履约终态闭集钉死：closed/completed/cancelled/rejected + 存量别名。"""
        for st in ("CLOSED", "已完成", "cancelled", "已驳回", "FINISHED"):
            assert st in SALES_TERMINAL_STATUSES
        self._patch_order(monkeypatch, [])
        self._patch_config(monkeypatch, None)
        await SalesDeliveryRiskDetector().detect(_ctx())

    @pytest.mark.asyncio
    async def test_no_permission_denies_and_leaks_nothing(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        perm_ok.return_value = False
        mock_filter = MagicMock()
        monkeypatch.setattr(
            "apps.kuaizhizao.models.sales_order.SalesOrder.filter", mock_filter
        )
        cfg_mock = AsyncMock()
        monkeypatch.setattr(
            "infra.services.tenant_service.TenantService.get_tenant_config",
            cfg_mock,
        )
        with pytest.raises(PulsePermissionDenied):
            await SalesDeliveryRiskDetector().detect(_ctx())
        mock_filter.assert_not_called()
        cfg_mock.assert_not_called()  # 阈值/单据都不查，零泄露

    @pytest.mark.asyncio
    async def test_tenant_id_carried(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        _qs_obj, mock_filter = self._patch_order(monkeypatch, [])
        cfg = self._patch_config(monkeypatch, None)
        await SalesDeliveryRiskDetector().detect(_ctx(tenant_id=42))
        cfg.assert_awaited_once_with(42, "kuaiai.pulse.sales_delivery_risk")
        assert mock_filter.call_args.kwargs["tenant_id"] == 42


# ============================================================ registry 编排


class _StubDetector:
    def __init__(self, domain, items=None, exc=None, delay=0.0, timeout=8.0):
        self.domain = domain
        self._items = items or []
        self._exc = exc
        self._delay = delay
        self.timeout_seconds = timeout

    async def detect(self, ctx):
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._exc:
            raise self._exc
        return list(self._items)


@pytest.fixture
def stub_detectors(monkeypatch):
    """替换 registry 的 detector 表；返回 dict 供各用例填充。"""
    holders: dict = {}
    monkeypatch.setattr(pulse_registry, "DETECTORS", holders)
    monkeypatch.setattr(
        pulse_registry,
        "IMPLEMENTED_DOMAINS",
        frozenset({"production", "sales"}),
    )
    return holders


class TestRegistry:
    @pytest.mark.asyncio
    async def test_partial_failure_masked_and_complete_false(
        self, stub_detectors
    ):
        stub_detectors["production"] = _StubDetector(
            "production", items=[_item()]
        )
        stub_detectors["sales"] = _StubDetector(
            "sales", exc=RuntimeError("boom")
        )
        out = await pulse_registry.run_pulse(TENANT, _user())
        assert out.complete is False
        assert out.summary.total == 1  # 只统计成功领域
        codes = {e.domain: e.code for e in out.errors}
        assert codes["sales"] == "detector_error"
        assert "boom" not in next(
            e.message for e in out.errors if e.domain == "sales"
        )

    @pytest.mark.asyncio
    async def test_permission_denied_error_and_complete_false(
        self, stub_detectors
    ):
        stub_detectors["production"] = _StubDetector(
            "production", exc=PulsePermissionDenied()
        )
        stub_detectors["sales"] = _StubDetector(
            "sales",
            items=[
                _item(
                    id="sales:sales.delivery_risk:1",
                    domain="sales",
                    rule_code="sales.delivery_risk",
                    resource_id="1",
                )
            ],
        )
        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["production", "sales"]
        )
        assert out.complete is False
        assert out.summary.total == 1
        codes = {e.domain: e.code for e in out.errors}
        assert codes["production"] == "permission_denied"

    @pytest.mark.asyncio
    async def test_not_connected_domains_do_not_break_complete(
        self, stub_detectors
    ):
        stub_detectors["production"] = _StubDetector(
            "production", items=[_item()]
        )
        stub_detectors["sales"] = _StubDetector("sales")
        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["inventory", "production", "quality"]
        )
        assert out.complete is True
        codes = {e.domain: e.code for e in out.errors}
        assert codes["inventory"] == "not_connected"
        assert codes["quality"] == "not_connected"
        assert "尚未接入检测器" in next(
            e.message for e in out.errors if e.domain == "inventory"
        )

    @pytest.mark.asyncio
    async def test_one_detector_timeout_does_not_block_others(
        self, stub_detectors
    ):
        stub_detectors["production"] = _StubDetector(
            "production", delay=0.5, timeout=0.05
        )
        stub_detectors["sales"] = _StubDetector(
            "sales",
            items=[
                _item(
                    id="sales:sales.delivery_risk:9",
                    domain="sales",
                    rule_code="sales.delivery_risk",
                    resource_id="9",
                )
            ],
        )
        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["production", "sales"]
        )
        assert out.complete is False
        assert out.summary.total == 1
        assert {e.domain: e.code for e in out.errors}["production"] == "timeout"

    @pytest.mark.asyncio
    async def test_dedup_and_stable_sort(self, stub_detectors):
        dup = _item(
            id="production:production.delay:55",
            resource_id="55",
            severity="warning",
            priority="medium",
        )
        items = [
            _item(
                id="production:production.delay:9",
                resource_id="9",
                severity="info",
                priority="low",
            ),
            dup,
            _item(
                id="production:production.delay:55",
                resource_id="55",
                severity="warning",
                priority="medium",
            ),  # 同 domain+rule+resource → 去重
            _item(
                id="production:production.delay:1",
                resource_id="1",
                severity="critical",
                priority="high",
            ),
            _item(
                id="production:production.delay:2",
                resource_id="2",
                severity="error",
                priority="high",
            ),
            _item(
                id="production:production.delay:3",
                resource_id="3",
                severity="error",
                priority="medium",
            ),
        ]
        stub_detectors["production"] = _StubDetector(
            "production", items=items
        )
        stub_detectors["sales"] = _StubDetector("sales")
        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["production"]
        )
        flat = [
            it.resource_id
            for g in out.groups
            for it in g.items
        ]
        assert flat == ["1", "2", "3", "55", "9"]  # sev→priority 稳定排序+去重
        assert out.summary.total == 5

    @pytest.mark.asyncio
    async def test_summary_excludes_failed_domains(self, stub_detectors):
        stub_detectors["production"] = _StubDetector(
            "production", exc=RuntimeError()
        )
        stub_detectors["sales"] = _StubDetector(
            "sales",
            items=[
                _item(
                    id="sales:sales.delivery_risk:1",
                    domain="sales",
                    severity="critical",
                    priority="high",
                    rule_code="sales.delivery_risk",
                    resource_id="1",
                )
            ],
        )
        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["production", "sales"]
        )
        assert out.summary.total == 1
        assert out.summary.critical == 1
        assert out.summary.high_priority == 1
        assert out.summary.warning_or_error == 0
        assert out.summary.domain_count == 1

    @pytest.mark.asyncio
    async def test_severity_filter(self, stub_detectors):
        stub_detectors["production"] = _StubDetector(
            "production",
            items=[
                _item(resource_id="1", severity="warning"),
                _item(
                    id="production:production.delay:2",
                    resource_id="2",
                    severity="critical",
                ),
            ],
        )
        out = await pulse_registry.run_pulse(
            TENANT,
            _user(),
            domains=["production"],
            severity="critical",
        )
        assert out.summary.total == 1
        assert out.groups[0].items[0].severity == "critical"

    @pytest.mark.asyncio
    async def test_pagination_group_count_is_domain_total(
        self, stub_detectors
    ):
        items = [
            _item(
                id=f"production:production.delay:{i}",
                resource_id=str(i),
                severity="warning",
            )
            for i in range(5)
        ]
        stub_detectors["production"] = _StubDetector(
            "production", items=items
        )
        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["production"], page=2, page_size=2
        )
        assert out.summary.total == 5
        assert len(out.groups) == 1
        assert out.groups[0].count == 5  # 领域总数，非本页条数
        assert len(out.groups[0].items) == 2  # 第 2 页第 3-4 条

    @pytest.mark.asyncio
    async def test_over_200_items_keep_exact_summary_and_third_page(
        self, stub_detectors
    ):
        items = [
            _item(
                id=f"production:production.delay:{i:03d}",
                resource_id=f"{i:03d}",
                severity="warning",
            )
            for i in range(250)
        ]
        stub_detectors["production"] = _StubDetector(
            "production", items=items
        )
        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["production"], page=3, page_size=100
        )
        assert out.summary.total == 250
        assert out.groups[0].count == 250
        assert len(out.groups[0].items) == 50

    @pytest.mark.asyncio
    async def test_page_beyond_range_returns_empty_groups(
        self, stub_detectors
    ):
        stub_detectors["production"] = _StubDetector(
            "production", items=[_item()]
        )
        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["production"], page=99, page_size=60
        )
        assert out.groups == []
        assert out.summary.total == 1

    @pytest.mark.asyncio
    async def test_empty_domain_means_all_domains(self, stub_detectors):
        stub_detectors["production"] = _StubDetector("production")
        stub_detectors["sales"] = _StubDetector("sales")
        out = await pulse_registry.run_pulse(TENANT, _user(), domains=None)
        assert {e.domain for e in out.errors} == {
            "inventory",
            "quality",
            "equipment",
        }
        assert all(e.code == "not_connected" for e in out.errors)
        assert out.complete is True

    @pytest.mark.asyncio
    async def test_pulse_total_count(self, stub_detectors, monkeypatch):
        monkeypatch.setattr(
            pulse_registry,
            "IMPLEMENTED_DOMAINS",
            frozenset({"production", "sales"}),
        )
        stub_detectors["production"] = _StubDetector(
            "production", items=[_item()]
        )
        stub_detectors["sales"] = _StubDetector("sales")
        assert (
            await pulse_registry.pulse_total_count(TENANT, _user()) == 1
        )
        stub_detectors["sales"] = _StubDetector(
            "sales", exc=RuntimeError()
        )
        assert (
            await pulse_registry.pulse_total_count(TENANT, _user()) == 1
        )  # 部分失败仍给真实计数
        stub_detectors["production"] = _StubDetector(
            "production", exc=RuntimeError()
        )
        assert (
            await pulse_registry.pulse_total_count(TENANT, _user()) is None
        )  # 全部失败 → 降级 null 而非伪造 0


# ============================================================ 参数解析与路由


class TestParamParsing:
    def test_parse_domains_valid(self):
        assert pulse_registry.parse_domains("production,sales") == [
            "production",
            "sales",
        ]
        assert pulse_registry.parse_domains(" production , production") == [
            "production"
        ]
        assert pulse_registry.parse_domains(None) is None
        assert pulse_registry.parse_domains("  ") is None

    def test_parse_domains_invalid(self):
        for raw in ("foo", "production,foo", ",,"):
            with pytest.raises(ValueError):
                pulse_registry.parse_domains(raw)

    @pytest.mark.asyncio
    async def test_api_422_on_bad_domain(self):
        from apps.kuaiai.api.operations import api_get_pulse

        with pytest.raises(HTTPException) as ei:
            await api_get_pulse(
                domain="foo",
                severity=None,
                page=1,
                page_size=60,
                tenant_id=TENANT,
                current_user=_user(),
            )
        assert ei.value.status_code == 422

    @pytest.mark.asyncio
    async def test_api_calls_registry_with_parsed_args(self, monkeypatch):
        from apps.kuaiai.api.operations import api_get_pulse

        captured = {}

        async def _fake(tenant_id, user, **kw):
            captured.update(kw)
            captured["tenant_id"] = tenant_id
            return MagicMock()

        monkeypatch.setattr(pulse_registry, "run_pulse", _fake)
        await api_get_pulse(
            domain="sales,production",
            severity="error",
            page=2,
            page_size=30,
            tenant_id=TENANT,
            current_user=_user(),
        )
        assert captured["domains"] == ["sales", "production"]
        assert captured["severity"] == "error"
        assert captured["page"] == 2
        assert captured["page_size"] == 30
        assert captured["tenant_id"] == TENANT
