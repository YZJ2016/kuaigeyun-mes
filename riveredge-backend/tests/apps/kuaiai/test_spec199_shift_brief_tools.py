"""KU-AI spec 199 单测：query_production_daily / query_pulse_signals。

全部 mock / 假数据，不需要真实数据库。覆盖：
- query_pulse_signals 直调 run_pulse（不复制 detector 逻辑）；domain 逗号
  分隔闭集、severity 闭集；errors[]/complete=false 如实透传，不把失败领域
  说成「无异常」；
- query_production_daily 两视图、日期校验、limit；不调用 list_templates
  （ensure_seed=True 会写预置模板）；
- 空结果、底层异常与既有 Tool 口径一致。
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaiai.services.tools import shift_brief as sb
from core.ai.runtime.context import AiRuntimeContext

TENANT = 7
USER_ID = 5


def _ctx():
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
    )


def _pulse_item(domain="production", severity="critical", title="工单延期"):
    return SimpleNamespace(
        domain=domain,
        severity=severity,
        priority="high",
        title=title,
        fact="WO-1 已超期 2 天",
        suggestion="尽快排产",
        resource_type="work_order",
        resource_id="1",
        detected_at=datetime(2026, 1, 10),
        rule_code="wo_delay",
    )


def _pulse_out(items=None, errors=None, complete=True):
    items = items or []
    groups = []
    if items:
        by_domain = {}
        for i in items:
            by_domain.setdefault(i.domain, []).append(i)
        for d, its in by_domain.items():
            groups.append(
                SimpleNamespace(
                    domain=d,
                    label=d,
                    count=len(its),
                    items=its,
                )
            )
    return SimpleNamespace(
        summary=SimpleNamespace(
            total=len(items),
            high_priority=len(items),
            critical=sum(1 for i in items if i.severity == "critical"),
            warning_or_error=0,
            domain_count=len({i.domain for i in items}),
        ),
        groups=groups,
        errors=errors or [],
        complete=complete,
    )


def _daily_row(**kw):
    base = dict(
        id=1,
        code="PD-2026-001",
        template_code="T-DAY",
        template_name="日常报工",
        report_date=date(2026, 1, 9),
        team_name="一班",
        shift_name="早班",
        workshop_name="一车间",
        plant_name="一厂",
        status="submitted",
        remarks=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestQueryPulseSignals:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await sb.query_pulse_signals(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_domain_and_severity(self):
        out = await sb.query_pulse_signals(domain="evil", ctx=_ctx())
        assert "production" in out
        out = await sb.query_pulse_signals(severity="bad", ctx=_ctx())
        assert "severity" in out

    @pytest.mark.asyncio
    async def test_calls_run_pulse_with_ctx_user(self):
        out_mock = _pulse_out(items=[_pulse_item()])
        with patch(
            "apps.kuaiai.services.pulse.registry.run_pulse",
            new=AsyncMock(return_value=out_mock),
        ) as m_pulse:
            out = await sb.query_pulse_signals(
                domain="production,sales",
                severity="critical",
                limit=5,
                ctx=_ctx(),
            )
        args, kwargs = m_pulse.await_args
        assert args[0] == TENANT
        assert args[1].id == USER_ID
        assert kwargs["domains"] == ["production", "sales"]
        assert kwargs["severity"] == "critical"
        assert kwargs["page_size"] == 5
        assert "工单延期" in out and "WO-1" in out
        assert "critical" in out and "尽快排产" in out

    @pytest.mark.asyncio
    async def test_errors_and_incomplete_transparent(self):
        out_mock = _pulse_out(
            items=[],
            errors=[
                SimpleNamespace(
                    domain="quality",
                    code="not_connected",
                    message="该领域尚未接入检测器",
                ),
                SimpleNamespace(
                    domain="sales",
                    code="permission_denied",
                    message="当前用户缺少该领域数据读取权限",
                ),
            ],
            complete=False,
        )
        with patch(
            "apps.kuaiai.services.pulse.registry.run_pulse",
            new=AsyncMock(return_value=out_mock),
        ):
            out = await sb.query_pulse_signals(ctx=_ctx())
        # 不把失败/未接入领域说成「无异常」
        assert "尚未接入" in out
        assert "缺少该领域数据读取权限" in out
        assert "检测未完成" in out

    @pytest.mark.asyncio
    async def test_empty_clean(self):
        with patch(
            "apps.kuaiai.services.pulse.registry.run_pulse",
            new=AsyncMock(return_value=_pulse_out()),
        ):
            out = await sb.query_pulse_signals(ctx=_ctx())
        assert "无异常信号" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        with patch(
            "apps.kuaiai.services.pulse.registry.run_pulse",
            new=AsyncMock(side_effect=RuntimeError("x")),
        ):
            out = await sb.query_pulse_signals(ctx=_ctx())
        assert out == "查询异常信号失败，请稍后重试"


class TestQueryProductionDaily:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await sb.query_production_daily(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_view_and_dates(self):
        out = await sb.query_production_daily(view="evil", ctx=_ctx())
        assert "reports" in out and "summary" in out
        out = await sb.query_production_daily(date_start="bad", ctx=_ctx())
        assert "date_start" in out
        out = await sb.query_production_daily(date_end="bad", ctx=_ctx())
        assert "date_end" in out

    @pytest.mark.asyncio
    async def test_reports_view_fields(self):
        svc = SimpleNamespace(
            list_reports=AsyncMock(
                return_value=SimpleNamespace(
                    items=[_daily_row()], total=1
                )
            )
        )
        with patch(
            "apps.kuaizhizao.services.production_daily_service"
            ".ProductionDailyReportService",
            return_value=svc,
        ):
            out = await sb.query_production_daily(ctx=_ctx())
        kw = svc.list_reports.await_args.kwargs
        assert svc.list_reports.await_args.args[0] == TENANT
        assert kw["limit"] <= 20
        assert "PD-2026-001" in out and "一班" in out
        assert "日常报工" in out and "submitted" in out
        assert "共 1 条" in out

    @pytest.mark.asyncio
    async def test_summary_view_numeric_fields(self):
        svc = SimpleNamespace(
            summarize=AsyncMock(
                return_value={
                    "items": [
                        {
                            "id": 1,
                            "code": "PD-001",
                            "report_date": "2026-01-09",
                            "team_name": "一班",
                            "template_name": "日常报工",
                            "status": "submitted",
                            "f_output_qty": 120,
                            "f_qualified_qty": 115,
                            "f_scrap_qty": 5,
                            "f_note": "文本不取",
                            "f_extra1": 1,
                            "f_extra2": 2,
                        }
                    ],
                    "total": 1,
                    "summary": {},
                }
            )
        )
        with patch(
            "apps.kuaizhizao.services.production_daily_service"
            ".ProductionDailyReportService",
            return_value=svc,
        ):
            out = await sb.query_production_daily(
                view="summary", ctx=_ctx()
            )
        assert "output_qty=120" in out
        assert "qualified_qty=115" in out
        assert "scrap_qty=5" in out
        # 文本字段与超上限数值字段不输出
        assert "文本不取" not in out and "extra1" not in out

    @pytest.mark.asyncio
    async def test_filters_passed_through(self):
        svc = SimpleNamespace(
            list_reports=AsyncMock(
                return_value=SimpleNamespace(items=[], total=0)
            )
        )
        with patch(
            "apps.kuaizhizao.services.production_daily_service"
            ".ProductionDailyReportService",
            return_value=svc,
        ):
            out = await sb.query_production_daily(
                team_name="一班",
                template_code="T-DAY",
                date_start="2026-01-01",
                date_end="2026-01-31",
                ctx=_ctx(),
            )
        kw = svc.list_reports.await_args.kwargs
        assert kw["team_name"] == "一班"
        assert kw["template_code"] == "T-DAY"
        assert kw["date_start"] == date(2026, 1, 1)
        assert kw["date_end"] == date(2026, 1, 31)
        assert "未查询到" in out

    @pytest.mark.asyncio
    async def test_no_template_list_call(self):
        """只读 Tool 不触达 list_templates（ensure_seed 会写库）。"""
        svc = SimpleNamespace(
            list_reports=AsyncMock(
                return_value=SimpleNamespace(items=[], total=0)
            ),
            list_templates=AsyncMock(),
        )
        with patch(
            "apps.kuaizhizao.services.production_daily_service"
            ".ProductionDailyReportService",
            return_value=svc,
        ):
            await sb.query_production_daily(ctx=_ctx())
        svc.list_templates.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = SimpleNamespace(
            list_reports=AsyncMock(side_effect=RuntimeError("db"))
        )
        with patch(
            "apps.kuaizhizao.services.production_daily_service"
            ".ProductionDailyReportService",
            return_value=svc,
        ):
            out = await sb.query_production_daily(ctx=_ctx())
        assert out == "查询生产日报失败，请稍后重试"
