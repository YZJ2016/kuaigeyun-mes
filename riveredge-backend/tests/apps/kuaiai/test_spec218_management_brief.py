"""KU-AI spec 218 单测：get_management_brief 管理层聚合简报。

全部 mock / 假数据，不需要真实数据库。覆盖：
- period/focus 闭集校验固定文案；
- 各域小节口径与数值断言（与各领域 service 返回值同源透传/确定性计数）；
- 域权限：无权限域显示「无 XX 域查看权限」不省略、部分无权限标注、
  四域全无权限返回固定文案、ctx 管理员标志位放行；
- 域级超时降级「数据获取超时」、域内源异常降级小节文案；
- 行级数据范围计数（_scoped_row_ids / _scoped_exception_rows 收敛后计数）；
- focus 过滤只调对应域；
- period → 站点时区日期范围换算（datetime 参数=站点日界 naive UTC）。
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaiai.services.tools import management_brief as mb
from core.ai.runtime.context import AiRuntimeContext
from core.utils import timezone_utils as tz_utils

TENANT = 7
USER_ID = 5

UPS = (
    "core.services.authorization.user_permission_service"
    ".UserPermissionService.has_permission"
)
WO_SVC = "apps.kuaizhizao.services.work_order_service.WorkOrderService"
REPORT_SVC = "apps.kuaizhizao.services.reporting_service.ReportingService"
DAILY_SVC = (
    "apps.kuaizhizao.services.production_daily_service"
    ".ProductionDailyReportService"
)
FPY_SVC = (
    "apps.kuaizhizao.services.first_pass_yield_service.FirstPassYieldService"
)
EXC_SVC = "apps.kuaizhizao.services.exception_service.ExceptionService"
KT_SCOPE = (
    "apps.kuaiai.services.tools.kitting_exceptions._scoped_exception_rows"
)
OEE_SVC = "apps.kuaizhizao.services.equipment_oee_service.EquipmentOEEService"
FAULT_SVC = (
    "apps.kuaizhizao.services.equipment_fault_service.EquipmentFaultService"
)
ALERT_SVC = (
    "apps.kuaizhizao.services.inventory_alert_service.InventoryAlertService"
)
STK_SVC = "apps.kuaizhizao.services.stocktaking_service.StocktakingService"
SCOPED_IDS = "apps.kuaiai.services.scene_tools._scoped_row_ids"

PERM_WO = "kuaizhizao:work-order:read"
PERM_REPORT = "kuaizhizao:production-execution-reporting:read"
PERM_DAILY = "kuaizhizao:production-daily:read"
PERM_FPY = "kuaizhizao:production-execution-reports-first-pass-yield:read"
PERM_QEXC = "kuaizhizao:production-execution-quality-exceptions:read"
PERM_OEE = "kuaizhizao:equipment-management-equipment:read"
PERM_FAULT = "kuaizhizao:equipment-fault:read"
PERM_ALERT = "kuaizhizao:warehouse-management-inventory-alert:read"
PERM_STK = "kuaizhizao:warehouse-management-stocktaking:read"

ALL_PERMS = frozenset(
    {
        PERM_WO,
        PERM_REPORT,
        PERM_DAILY,
        PERM_FPY,
        PERM_QEXC,
        PERM_OEE,
        PERM_FAULT,
        PERM_ALERT,
        PERM_STK,
    }
)

# 固定「今天」= 站点日 2026-01-15（周四，Asia/Shanghai）
NOW_UTC = datetime(2026, 1, 15, 2, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch):
    monkeypatch.setattr(tz_utils, "site_timezone_name", lambda: "Asia/Shanghai")
    monkeypatch.setattr(tz_utils, "now_utc", lambda: NOW_UTC)


def _ctx(**kw):
    base = dict(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
    )
    base.update(kw)
    return AiRuntimeContext(**base)


def _perm_mock(allowed):
    allowed = frozenset(allowed)

    async def _hp(user_id, tenant_id, permission_code, **kw):
        return permission_code in allowed

    return AsyncMock(side_effect=_hp)


# ------------------------------------------------------------ 假 service 返回


def _wo_svc():
    async def _list(tenant_id, **kw):
        if kw.get("planned_end_from"):
            return [], 8
        if kw.get("status") == "released":
            return [], 3
        if kw.get("status") == "in_progress":
            return [], 12
        return [], 0

    return SimpleNamespace(list_work_orders=AsyncMock(side_effect=_list))


def _report_svc():
    return SimpleNamespace(
        get_reporting_statistics=AsyncMock(
            return_value={
                "total_count": 42,
                "total_reported_quantity": 1200.0,
                "total_qualified_quantity": 1180.0,
                "total_unqualified_quantity": 20.0,
                "total_work_hours": 160.0,
                "qualification_rate": 98.3,
                "first_pass_yield_rate": 95.8,
            }
        )
    )


def _daily_svc():
    async def _list(tenant_id, **kw):
        if kw.get("status") == "submitted":
            return SimpleNamespace(items=[], total=2)
        return SimpleNamespace(items=[], total=3)

    return SimpleNamespace(list_reports=AsyncMock(side_effect=_list))


def _fpy_svc():
    return SimpleNamespace(
        get_summary=AsyncMock(
            return_value={
                "first_pass_qualified_quantity": 1150.0,
                "first_pass_reported_quantity": 1200.0,
                "first_pass_yield_rate": 95.8,
                "qualification_rate": 98.3,
            }
        )
    )


def _exc_rows(n, start=1):
    return [
        SimpleNamespace(id=i, work_order_id=10 + i)
        for i in range(start, start + n)
    ]


def _exc_svc(new_rows=None, open_rows=None):
    new_rows = _exc_rows(2) if new_rows is None else new_rows
    open_rows = _exc_rows(1, 100) if open_rows is None else open_rows

    async def _list(tenant_id, **kw):
        if kw.get("statuses"):
            return list(open_rows), len(open_rows)
        return list(new_rows), len(new_rows)

    return SimpleNamespace(list_quality_exceptions=AsyncMock(side_effect=_list))


async def _scope_rows_echo(rows, ctx, err_text, **kw):
    return list(rows), None


def _oee_svc(rows=None):
    if rows is None:
        rows = [
            {"oee": {"oee_value": 60.0}},
            {"oee": {"oee_value": 80.0}},
            {"oee": {"oee_value": None}},
        ]
    return SimpleNamespace(list_equipment_oee=AsyncMock(return_value=rows))


def _fault_rows(n, start=1):
    return [SimpleNamespace(id=i) for i in range(start, start + n)]


def _fault_svc():
    async def _list(tenant_id, **kw):
        if kw.get("status") == "待处理":
            return _fault_rows(1, 10), 1
        if kw.get("status") == "处理中":
            return _fault_rows(2, 20), 2
        return _fault_rows(3), 3

    return SimpleNamespace(list_equipment_faults=AsyncMock(side_effect=_list))


def _alert_rows(n, start=1, levels=None):
    levels = levels or ["info"] * n
    return [
        SimpleNamespace(id=i, alert_level=levels[i - start])
        for i in range(start, start + n)
    ]


def _alert_svc():
    rows = _alert_rows(4, levels=["info", "critical", "warning", "info"])

    async def _get(tenant_id, **kw):
        if kw.get("status") == "pending":
            return _alert_rows(2, 50), 2
        return list(rows), 4

    return SimpleNamespace(get_alerts=AsyncMock(side_effect=_get))


def _stk_svc():
    async def _list(tenant_id, **kw):
        if kw.get("status") == "in_progress":
            return SimpleNamespace(
                items=[SimpleNamespace(id=9)], total=1
            )
        return SimpleNamespace(
            items=[SimpleNamespace(id=1), SimpleNamespace(id=2)], total=2
        )

    return SimpleNamespace(list_stocktakings=AsyncMock(side_effect=_list))


@contextlib.contextmanager
def _patched(allowed=ALL_PERMS, **overrides):
    """组合 patch：权限 + 全部域 service + 行级范围（默认可见全部）。"""
    svcs = dict(
        wo=_wo_svc(),
        report=_report_svc(),
        daily=_daily_svc(),
        fpy=_fpy_svc(),
        exc=_exc_svc(),
        oee=_oee_svc(),
        fault=_fault_svc(),
        alert=_alert_svc(),
        stk=_stk_svc(),
    )
    svcs.update(overrides)
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch(UPS, new=_perm_mock(allowed)))
        stack.enter_context(patch(WO_SVC, return_value=svcs["wo"]))
        stack.enter_context(patch(REPORT_SVC, return_value=svcs["report"]))
        stack.enter_context(patch(DAILY_SVC, return_value=svcs["daily"]))
        stack.enter_context(patch(FPY_SVC, return_value=svcs["fpy"]))
        stack.enter_context(patch(EXC_SVC, return_value=svcs["exc"]))
        stack.enter_context(
            patch(KT_SCOPE, new=AsyncMock(side_effect=_scope_rows_echo))
        )
        stack.enter_context(patch(OEE_SVC, return_value=svcs["oee"]))
        stack.enter_context(patch(FAULT_SVC, svcs["fault"]))
        stack.enter_context(patch(ALERT_SVC, return_value=svcs["alert"]))
        stack.enter_context(patch(STK_SVC, return_value=svcs["stk"]))
        stack.enter_context(
            patch(
                SCOPED_IDS,
                new=AsyncMock(side_effect=lambda m, c, r, ids: set(ids)),
            )
        )
        yield svcs


# ================================================================ 参数校验


class TestParams:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await mb.get_management_brief(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_period(self):
        out = await mb.get_management_brief(period="this_month", ctx=_ctx())
        assert out == "period 仅支持 today/yesterday/this_week/last_week"

    @pytest.mark.asyncio
    async def test_invalid_focus(self):
        out = await mb.get_management_brief(focus="sales", ctx=_ctx())
        assert out == (
            "focus 仅支持 production/quality/equipment/inventory/all"
        )

    @pytest.mark.asyncio
    async def test_period_labels(self):
        expected = {
            "today": "2026-01-15~2026-01-15",
            "yesterday": "2026-01-14~2026-01-14",
            "this_week": "2026-01-12~2026-01-15",
            "last_week": "2026-01-05~2026-01-11",
        }
        for period, rng in expected.items():
            with _patched():
                out = await mb.get_management_brief(
                    period=period, ctx=_ctx()
                )
            assert f"统计期间 {rng}" in out


# ================================================================ 全量小节


class TestAllSections:
    @pytest.mark.asyncio
    async def test_sections_and_values(self):
        with _patched():
            out = await mb.get_management_brief(period="today", ctx=_ctx())
        assert "管理层简报" in out
        # 生产
        assert "【生产】" in out
        assert "期间计划完工 8 张，当前进行中 15 张" in out
        assert "已审批 42 笔" in out
        assert "报工数量 1200" in out and "合格 1180" in out
        assert "不合格 20" in out and "合格率 98.3%" in out
        assert "工时 160h" in out
        assert "期间填报 3 份，已提交 2 份" in out
        # 质量
        assert "【质量】" in out
        assert "首次合格 1150/首次报工 1200 = 95.8%" in out
        assert "综合合格率 98.3%" in out
        assert "期间新增 2 条" in out and "未闭环 1 条" in out
        # 设备
        assert "【设备】" in out
        assert "3 台设备有统计" in out and "平均 OEE 70.0%" in out
        assert "1 台指标不可用" in out
        assert "期间新增 3 条" in out and "待处理/处理中 3 条" in out
        # 库存
        assert "【库存】" in out
        assert "期间触发 4 条" in out and "critical 1 条" in out
        assert "待处理 2 条" in out
        assert "期间盘点单 2 张" in out and "进行中 1 张" in out
        # 口径标注
        assert "报工时间口径" in out
        assert "计划完工日口径" in out
        assert "触发时间口径" in out

    @pytest.mark.asyncio
    async def test_service_params_timezone_bounds(self):
        """datetime 参数 = 站点日界转 naive UTC（Shanghai 日界）。"""
        with _patched() as svcs:
            await mb.get_management_brief(period="today", ctx=_ctx())
        kw = svcs["report"].get_reporting_statistics.await_args.kwargs
        # 2026-01-15 站点日 [08:00 前一日 UTC, 本日 16:00 UTC)
        assert kw["date_start"] == datetime(2026, 1, 14, 16, 0, 0)
        assert kw["date_end"] == datetime(2026, 1, 15, 15, 59, 59, 999999)
        assert kw["date_start"].tzinfo is None
        # 工单计划完工日 = 站点日历日
        calls = svcs["wo"].list_work_orders.await_args_list
        planned_kw = next(
            c.kwargs for c in calls if c.kwargs.get("planned_end_from")
        )
        assert planned_kw["planned_end_from"] == "2026-01-15"
        assert planned_kw["planned_end_to"] == "2026-01-15"

    @pytest.mark.asyncio
    async def test_work_order_counts_sum_released_in_progress(self):
        """进行中 = released + in_progress（与 KPI 卡同口径）。"""
        with _patched():
            out = await mb.get_management_brief(ctx=_ctx())
        assert "当前进行中 15 张" in out  # 3 + 12

    @pytest.mark.asyncio
    async def test_oee_all_unavailable(self):
        svc = _oee_svc(rows=[{"oee": {"oee_value": None}}])
        with _patched(oee=svc):
            out = await mb.get_management_brief(ctx=_ctx())
        assert "平均 OEE 不可用" in out

    @pytest.mark.asyncio
    async def test_oee_cap_note_only_when_over_sample_max(self):
        """OEE 恰达取样上限不误标截断；确有第 101 台才注明。"""
        rows_100 = [{"oee": {"oee_value": 50.0}} for _ in range(100)]
        with _patched(oee=_oee_svc(rows=rows_100)):
            out = await mb.get_management_brief(ctx=_ctx())
        assert "100 台设备有统计" in out
        assert "取样上限" not in out
        rows_101 = [{"oee": {"oee_value": 50.0}} for _ in range(101)]
        with _patched(oee=_oee_svc(rows=rows_101)):
            out = await mb.get_management_brief(ctx=_ctx())
        assert "已达 100 台取样上限" in out

    @pytest.mark.asyncio
    async def test_header_period_note_two_calibres(self):
        """头部口径注记分列两类：datetime 参数源=站点时区日界，
        单据日期参数源=日历日含界。"""
        with _patched():
            out = await mb.get_management_brief(ctx=_ctx())
        assert "站点时区日界" in out and "日历日含界" in out

    @pytest.mark.asyncio
    async def test_no_personal_info_no_detail_rows(self):
        with _patched():
            out = await mb.get_management_brief(ctx=_ctx())
        # 不输出报工人/操作员明细与单号级明细行
        assert "worker" not in out.lower()
        assert "WO-" not in out
        assert "PD-" not in out


# ================================================================ 权限


class TestPermissions:
    @pytest.mark.asyncio
    async def test_denied_domain_placeholder(self):
        """质量域全部源无权限 → 占位小节不省略。"""
        with _patched(allowed=ALL_PERMS - {PERM_FPY, PERM_QEXC}):
            out = await mb.get_management_brief(ctx=_ctx())
        assert "【质量】无质量域查看权限" in out
        assert "【生产】" in out and "【设备】" in out and "【库存】" in out

    @pytest.mark.asyncio
    async def test_partial_permission_marks_denied_source(self):
        """域内部分源无权限：有权限源照常输出，无权限源标注。"""
        with _patched(allowed=ALL_PERMS - {PERM_STK}):
            out = await mb.get_management_brief(ctx=_ctx())
        assert "库存预警：期间触发 4 条" in out
        assert "另有无权限查看：盘点" in out
        assert "期间盘点单" not in out

    @pytest.mark.asyncio
    async def test_all_denied_fixed_text(self):
        with _patched(allowed=frozenset()):
            out = await mb.get_management_brief(ctx=_ctx())
        assert out == (
            "当前用户没有生产/质量/设备/库存任一领域的查看权限，"
            "无法生成管理层简报"
        )
        assert "【" not in out

    @pytest.mark.asyncio
    async def test_admin_flag_bypasses_permission_check(self):
        """ctx 管理员标志位放行（与 tool_bridge 同口径），不调 has_permission。"""
        hp = _perm_mock(frozenset())
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch(UPS, new=hp))
            for target, svc in (
                (WO_SVC, _wo_svc()),
                (REPORT_SVC, _report_svc()),
                (DAILY_SVC, _daily_svc()),
                (FPY_SVC, _fpy_svc()),
                (EXC_SVC, _exc_svc()),
                (OEE_SVC, _oee_svc()),
                (ALERT_SVC, _alert_svc()),
                (STK_SVC, _stk_svc()),
            ):
                stack.enter_context(patch(target, return_value=svc))
            stack.enter_context(patch(FAULT_SVC, _fault_svc()))
            stack.enter_context(
                patch(KT_SCOPE, new=AsyncMock(side_effect=_scope_rows_echo))
            )
            stack.enter_context(
                patch(
                    SCOPED_IDS,
                    new=AsyncMock(side_effect=lambda m, c, r, ids: set(ids)),
                )
            )
            out = await mb.get_management_brief(
                ctx=_ctx(is_tenant_admin=True)
            )
        assert "【生产】" in out and "无生产域查看权限" not in out
        hp.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_permission_error_fails_closed(self):
        """has_permission 异常 → 失败关闭按无权限处理。"""
        hp = AsyncMock(side_effect=RuntimeError("rbac down"))
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch(UPS, new=hp))
            out = await mb.get_management_brief(ctx=_ctx())
        assert "任一领域的查看权限" in out


# ================================================================ 超时与降级


class TestDegradation:
    @pytest.mark.asyncio
    async def test_domain_timeout_degrades(self, monkeypatch):
        async def _slow(tenant_id, **kw):
            await asyncio.sleep(5)
            return [], 0

        svc = SimpleNamespace(
            list_quality_exceptions=AsyncMock(side_effect=_slow)
        )
        monkeypatch.setattr(mb, "_DOMAIN_TIMEOUT_SECONDS", 0.05)
        with _patched(exc=svc):
            out = await mb.get_management_brief(ctx=_ctx())
        assert "【质量】数据获取超时" in out
        # 其他域不受影响
        assert "【生产】" in out and "期间计划完工 8 张" in out

    @pytest.mark.asyncio
    async def test_source_error_degrades_to_line(self):
        async def _boom(tenant_id, **kw):
            raise RuntimeError("db down")

        svc = SimpleNamespace(list_reports=AsyncMock(side_effect=_boom))
        with _patched(daily=svc):
            out = await mb.get_management_brief(ctx=_ctx())
        assert "生产日报：数据获取失败" in out
        # 同域其他源正常
        assert "期间计划完工 8 张" in out and "已审批 42 笔" in out
        # 不泄露底层异常文本
        assert "db down" not in out


# ================================================================ focus 过滤


class TestFocus:
    @pytest.mark.asyncio
    async def test_focus_single_domain(self):
        with _patched() as svcs:
            out = await mb.get_management_brief(
                focus="quality", ctx=_ctx()
            )
        assert "【质量】" in out
        assert "【生产】" not in out and "【设备】" not in out
        assert "【库存】" not in out
        svcs["wo"].list_work_orders.assert_not_awaited()
        svcs["oee"].list_equipment_oee.assert_not_awaited()
        svcs["alert"].get_alerts.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_focus_denied_domain(self):
        with _patched(allowed=ALL_PERMS - {PERM_FPY, PERM_QEXC}):
            out = await mb.get_management_brief(
                focus="quality", ctx=_ctx()
            )
        # focus=quality 且该域全无权限 → 按 focus 给对应域文案
        assert out == "当前用户没有质量领域的查看权限，无法生成管理层简报"


# ================================================================ 数据范围计数


class TestScopedCounting:
    @pytest.mark.asyncio
    async def test_alert_visible_count_after_scope(self):
        """行级范围收敛后计数：4 条预警可见 2 条，critical 只计可见行。"""
        rows = _alert_rows(4, levels=["info", "critical", "warning", "info"])

        async def _get(tenant_id, **kw):
            if kw.get("status") == "pending":
                return _alert_rows(2, 50), 2
            return list(rows), 4

        alert = SimpleNamespace(get_alerts=AsyncMock(side_effect=_get))

        async def _scope(model, ctx, res, ids):
            return {1, 2} if res == "kuaizhizao:inventory" else set(ids)

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch(UPS, new=_perm_mock(ALL_PERMS)))
            for target, svc in (
                (WO_SVC, _wo_svc()),
                (REPORT_SVC, _report_svc()),
                (DAILY_SVC, _daily_svc()),
                (FPY_SVC, _fpy_svc()),
                (EXC_SVC, _exc_svc()),
                (OEE_SVC, _oee_svc()),
                (FAULT_SVC, _fault_svc()),
                (STK_SVC, _stk_svc()),
            ):
                if target == FAULT_SVC:
                    stack.enter_context(patch(target, svc))
                else:
                    stack.enter_context(patch(target, return_value=svc))
            stack.enter_context(patch(ALERT_SVC, return_value=alert))
            stack.enter_context(
                patch(KT_SCOPE, new=AsyncMock(side_effect=_scope_rows_echo))
            )
            stack.enter_context(
                patch(SCOPED_IDS, new=AsyncMock(side_effect=_scope))
            )
            out = await mb.get_management_brief(ctx=_ctx())
        # 可见 id={1,2} → 触发 2 条，critical 只有 id=2 一条
        assert "期间触发 2 条" in out and "critical 1 条" in out

    @pytest.mark.asyncio
    async def test_quality_exception_scope_filter(self):
        """_scoped_exception_rows 收敛后计数（工单可见集求交由 mock 模拟）。"""

        async def _scope_half(rows, ctx, err_text, **kw):
            return list(rows or [])[:1], None

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch(UPS, new=_perm_mock(ALL_PERMS)))
            for target, svc in (
                (WO_SVC, _wo_svc()),
                (REPORT_SVC, _report_svc()),
                (DAILY_SVC, _daily_svc()),
                (FPY_SVC, _fpy_svc()),
                (EXC_SVC, _exc_svc()),
                (OEE_SVC, _oee_svc()),
                (ALERT_SVC, _alert_svc()),
                (STK_SVC, _stk_svc()),
            ):
                stack.enter_context(patch(target, return_value=svc))
            stack.enter_context(patch(FAULT_SVC, _fault_svc()))
            stack.enter_context(
                patch(KT_SCOPE, new=AsyncMock(side_effect=_scope_half))
            )
            stack.enter_context(
                patch(
                    SCOPED_IDS,
                    new=AsyncMock(side_effect=lambda m, c, r, ids: set(ids)),
                )
            )
            out = await mb.get_management_brief(ctx=_ctx())
        # 期间新增 2 条收敛为 1 条；未闭环 1 条收敛为 1 条（[:1]）
        assert "期间新增 1 条" in out
