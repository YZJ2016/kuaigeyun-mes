"""KU-AI spec 198 单测：analyze_first_pass_yield / analyze_defect_pareto。

全部 mock / 假数据，不需要真实数据库。覆盖：
- view 闭集、日期非法、days 越界回固定文案；
- 三视图与 service 同参数调用（start→日初 / end→日末，含界）；
- operations 按一次合格率升序（最差在前），数值同 service；
- 帕累托适配层按 defect_type 聚合数量/占比/累计占比，注明样本范围；
- 空结果、底层异常与既有 Tool 口径一致；不输出员工姓名维度。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaiai.services.tools import quality_analytics as qa
from core.ai.runtime.context import AiRuntimeContext

TENANT = 7
USER_ID = 5


def _ctx():
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
    )


def _fpy_svc(**kw):
    base = dict(
        get_summary=AsyncMock(
            return_value={
                "first_pass_qualified_quantity": 90.0,
                "first_pass_reported_quantity": 100.0,
                "first_pass_yield_rate": 90.0,
                "qualification_rate": 95.0,
            }
        ),
        get_operation_breakdown=AsyncMock(return_value=[]),
        get_daily_trend=AsyncMock(return_value=[]),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _op_row(name, rate, count=10, reported=100.0, fpq=90.0, qual=95.0):
    return {
        "operation_name": name,
        "count": count,
        "reported_quantity": reported,
        "qualified_quantity": reported * qual / 100,
        "unqualified_quantity": reported * (100 - qual) / 100,
        "qualification_rate": qual,
        "first_pass_reported_quantity": reported,
        "first_pass_qualified_quantity": fpq,
        "first_pass_unqualified_quantity": reported - fpq,
        "first_pass_yield_rate": rate,
    }


def _defect_rows(*specs):
    return [
        {
            "code": f"D-{i}",
            "defect_code": f"D-{i}",
            "product_name": "产品A",
            "material_name": "产品A",
            "defect_type": t,
            "defect_quantity": q,
            "created_at": "2026-01-10",
            "defect_reason": "原因",
        }
        for i, (t, q) in enumerate(specs)
    ]


class TestAnalyzeFirstPassYield:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await qa.analyze_first_pass_yield(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_view(self):
        out = await qa.analyze_first_pass_yield(view="evil", ctx=_ctx())
        assert "summary" in out and "trend" in out

    @pytest.mark.asyncio
    async def test_invalid_dates(self):
        out = await qa.analyze_first_pass_yield(
            date_start="2026/01/01", ctx=_ctx()
        )
        assert "date_start" in out
        out = await qa.analyze_first_pass_yield(date_end="abc", ctx=_ctx())
        assert "date_end" in out

    @pytest.mark.asyncio
    async def test_summary_view_calls_service_with_day_bounds(self):
        svc = _fpy_svc()
        with patch(
            "apps.kuaizhizao.services.first_pass_yield_service"
            ".FirstPassYieldService",
            return_value=svc,
        ):
            out = await qa.analyze_first_pass_yield(
                view="summary",
                date_start="2026-01-01",
                date_end="2026-01-31",
                ctx=_ctx(),
            )
        kw = svc.get_summary.await_args.kwargs
        assert svc.get_summary.await_args.args[0] == TENANT
        assert kw["date_start"] == datetime(2026, 1, 1, 0, 0, 0)
        assert kw["date_end"] == datetime(2026, 1, 31, 23, 59, 59, 999999)
        assert "90.0%" in out and "95.0%" in out
        assert "首次合格" in out

    @pytest.mark.asyncio
    async def test_operations_sorted_worst_first(self):
        svc = _fpy_svc(
            get_operation_breakdown=AsyncMock(
                return_value=[
                    _op_row("组装", 98.0),
                    _op_row("焊接", 60.0),
                    _op_row("涂装", 85.0),
                ]
            )
        )
        with patch(
            "apps.kuaizhizao.services.first_pass_yield_service"
            ".FirstPassYieldService",
            return_value=svc,
        ):
            out = await qa.analyze_first_pass_yield(
                view="operations", ctx=_ctx()
            )
        # 最差在前
        assert out.index("焊接") < out.index("涂装") < out.index("组装")
        assert "60.0%" in out and "98.0%" in out
        # 不出现员工维度
        assert "worker" not in out.lower()

    @pytest.mark.asyncio
    async def test_operations_empty(self):
        svc = _fpy_svc()
        with patch(
            "apps.kuaizhizao.services.first_pass_yield_service"
            ".FirstPassYieldService",
            return_value=svc,
        ):
            out = await qa.analyze_first_pass_yield(
                view="operations", ctx=_ctx()
            )
        assert "未查询到" in out

    @pytest.mark.asyncio
    async def test_trend_days_bounds_and_output(self):
        svc = _fpy_svc(
            get_daily_trend=AsyncMock(
                return_value=[
                    {"date": "2026-01-09", "first_pass_yield_rate": 88.0,
                     "qualification_rate": 92.0},
                    {"date": "2026-01-10", "first_pass_yield_rate": 91.0,
                     "qualification_rate": 94.0},
                ]
            )
        )
        with patch(
            "apps.kuaizhizao.services.first_pass_yield_service"
            ".FirstPassYieldService",
            return_value=svc,
        ):
            out = await qa.analyze_first_pass_yield(
                view="trend", days=2, ctx=_ctx()
            )
        assert svc.get_daily_trend.await_args.kwargs["days"] == 2
        assert "2026-01-09" in out and "91.0%" in out

        out = await qa.analyze_first_pass_yield(
            view="trend", days=0, ctx=_ctx()
        )
        assert "days" in out
        out = await qa.analyze_first_pass_yield(
            view="trend", days=99, ctx=_ctx()
        )
        assert "days" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = _fpy_svc(
            get_summary=AsyncMock(side_effect=RuntimeError("db down"))
        )
        with patch(
            "apps.kuaizhizao.services.first_pass_yield_service"
            ".FirstPassYieldService",
            return_value=svc,
        ):
            out = await qa.analyze_first_pass_yield(ctx=_ctx())
        assert out == "查询一次合格率失败，请稍后重试"
        assert "db down" not in out


class TestAnalyzeDefectPareto:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await qa.analyze_defect_pareto(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_dates(self):
        out = await qa.analyze_defect_pareto(
            date_start="bad", ctx=_ctx()
        )
        assert "date_start" in out

    @pytest.mark.asyncio
    async def test_aggregation_share_and_cumulative(self):
        svc = SimpleNamespace(
            get_quality_report=AsyncMock(
                return_value={
                    "data": _defect_rows(
                        ("划伤", 30), ("尺寸不良", 20), ("划伤", 10), ("脏污", 5)
                    ),
                    "success": True,
                }
            )
        )
        with patch(
            "apps.kuaizhizao.services.report_service.ReportService",
            return_value=svc,
        ):
            out = await qa.analyze_defect_pareto(ctx=_ctx())
        kw = svc.get_quality_report.await_args.kwargs
        assert svc.get_quality_report.await_args.args[0] == TENANT
        assert svc.get_quality_report.await_args.args[1] == (
            "defect-pareto-analysis"
        )
        # 划伤 40/65=61.5% → 累计 61.5；尺寸不良 20/65=30.8 → 累计 92.3
        assert "划伤" in out and "40" in out and "61.5%" in out
        assert "尺寸不良" in out and "92.3%" in out
        # 降序：划伤第一
        assert out.index("划伤") < out.index("尺寸不良")
        # 样本范围说明
        assert "4 条" in out

    @pytest.mark.asyncio
    async def test_sample_limit_note_when_100(self):
        rows = _defect_rows(*(("类型A", 1) for _ in range(100)))
        svc = SimpleNamespace(
            get_quality_report=AsyncMock(
                return_value={"data": rows, "success": True}
            )
        )
        with patch(
            "apps.kuaizhizao.services.report_service.ReportService",
            return_value=svc,
        ):
            out = await qa.analyze_defect_pareto(ctx=_ctx())
        assert "样本达上限 100 条" in out and "非全量" in out

    @pytest.mark.asyncio
    async def test_filters_passed_through(self):
        svc = SimpleNamespace(
            get_quality_report=AsyncMock(
                return_value={"data": [], "success": True}
            )
        )
        with patch(
            "apps.kuaizhizao.services.report_service.ReportService",
            return_value=svc,
        ):
            out = await qa.analyze_defect_pareto(
                material_id=3,
                date_start="2026-01-01",
                date_end="2026-01-31",
                ctx=_ctx(),
            )
        kw = svc.get_quality_report.await_args.kwargs
        assert kw["material_id"] == 3
        assert kw["date_start"] == datetime(2026, 1, 1, 0, 0, 0)
        assert kw["date_end"] == datetime(2026, 1, 31, 23, 59, 59, 999999)
        assert "未查询到" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = SimpleNamespace(
            get_quality_report=AsyncMock(side_effect=RuntimeError("x"))
        )
        with patch(
            "apps.kuaizhizao.services.report_service.ReportService",
            return_value=svc,
        ):
            out = await qa.analyze_defect_pareto(ctx=_ctx())
        assert out == "查询缺陷帕累托失败，请稍后重试"
