"""KU-AI spec 205 单测：query_mrp_exceptions。

全部 mock / 假数据，不需要真实数据库。覆盖：
- ctx/租户缺失回 _ERR_NO_CONTEXT 固定文案；
- severity 非闭集值（error|warning|info 之外）回固定错误文案；
- computation_id 非法值回固定错误文案；
- tenant_id / computation_id / code / severity / limit 透传 service，
  limit 钳到 ≤20；不传 current_user（与路由同口径）；
- 有界摘要：总数 + 错误/警告/提示计数 + 按例外码分布 + 前 N 条，
  行内含例外码/严重级/物料/需求日期/计算编号/说明；
- 空结果真实文案、底层异常固定错误文案；
- 不输出单价/金额等敏感字段。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaiai.services.tools import mrp_exceptions as mx
from core.ai.runtime.context import AiRuntimeContext

TENANT = 7
USER_ID = 5
SVC_PATH = (
    "apps.kuaizhizao.services.demand_computation_service"
    ".DemandComputationService"
)


def _ctx():
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
    )


def _row(**kw):
    base = dict(
        inbox_key="11:55:SHORTAGE_WITHIN_LEAD_TIME:0",
        computation_id=11,
        computation_code="MRP-2026-001",
        computation_end_time=datetime(2026, 1, 20, 10, 30),
        item_id=55,
        material_id=9,
        material_code="M-001",
        material_name="物料一",
        code="SHORTAGE_WITHIN_LEAD_TIME",
        severity="error",
        message="2026-02-01 短缺发生在提前期内（lead=5天）",
        qty=120,
        bucket_date="2026-02-01",
        document_id=88,
        document_code="WO-1001",
        document_source_type="work_order",
    )
    base.update(kw)
    return base


def _result(rows, **kw):
    error_count = sum(1 for r in rows if r.get("severity") == "error")
    warning_count = sum(1 for r in rows if r.get("severity") == "warning")
    summary = {}
    for r in rows:
        c = r.get("code") or ""
        summary[c] = summary.get(c, 0) + 1
    base = dict(
        total=len(rows),
        error_count=error_count,
        warning_count=warning_count,
        summary_by_code=summary,
        items=rows,
    )
    base.update(kw)
    return base


def _service(result=None, side_effect=None):
    svc = SimpleNamespace()
    svc.get_mrp_exception_inbox = AsyncMock(
        return_value=result, side_effect=side_effect
    )
    return svc


class TestQueryMrpExceptionsParams:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await mx.query_mrp_exceptions(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_ctx_missing_tenant(self):
        ctx = AiRuntimeContext(
            tenant_id=0,
            user=SimpleNamespace(id=USER_ID),
        )
        out = await mx.query_mrp_exceptions(ctx=ctx)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_severity(self):
        out = await mx.query_mrp_exceptions(severity="fatal", ctx=_ctx())
        assert out == "severity 仅支持 error/warning/info"

    @pytest.mark.asyncio
    async def test_invalid_computation_id(self):
        out = await mx.query_mrp_exceptions(
            computation_id="abc", ctx=_ctx()
        )
        assert "computation_id" in out
        out = await mx.query_mrp_exceptions(computation_id=-3, ctx=_ctx())
        assert "computation_id" in out


class TestQueryMrpExceptions:
    @pytest.mark.asyncio
    async def test_filters_passed_and_no_current_user(self):
        svc = _service(result=_result([_row()]))
        with patch(SVC_PATH, return_value=svc):
            out = await mx.query_mrp_exceptions(
                computation_id=11,
                code="SHORTAGE_WITHIN_LEAD_TIME",
                severity="error",
                ctx=_ctx(),
            )
        args = svc.get_mrp_exception_inbox.await_args
        assert args.args[0] == TENANT
        kw = args.kwargs
        assert kw["computation_id"] == 11
        assert kw["code"] == "SHORTAGE_WITHIN_LEAD_TIME"
        assert kw["severity"] == "error"
        assert kw["skip"] == 0
        # 与路由同口径：不向 service 传 current_user
        assert "current_user" not in kw
        assert "MRP-2026-001" in out
        assert "SHORTAGE_WITHIN_LEAD_TIME" in out

    @pytest.mark.asyncio
    async def test_limit_clamped_to_20(self):
        svc = _service(result=_result([]))
        with patch(SVC_PATH, return_value=svc):
            await mx.query_mrp_exceptions(limit=99, ctx=_ctx())
        assert svc.get_mrp_exception_inbox.await_args.kwargs["limit"] == 20

    @pytest.mark.asyncio
    async def test_summary_counts_and_rows(self):
        rows = [
            _row(),
            _row(
                item_id=56,
                code="RESCHEDULE_IN",
                severity="warning",
                message="供应 WO-1002 建议提前",
                document_code="WO-1002",
            ),
            _row(
                item_id=57,
                code="BUCKET_RANGE_CLAMPED",
                severity="info",
                message="桶范围被钳制",
                document_code=None,
            ),
        ]
        svc = _service(result=_result(rows))
        with patch(SVC_PATH, return_value=svc):
            out = await mx.query_mrp_exceptions(ctx=_ctx())
        assert "共 3 条 MRP 例外" in out
        assert "错误 1" in out and "警告 1" in out and "提示 1" in out
        assert "错误优先" in out
        assert "SHORTAGE_WITHIN_LEAD_TIME×1" in out
        assert "RESCHEDULE_IN×1" in out
        assert "[错误]" in out and "[警告]" in out and "[提示]" in out
        assert "M-001" in out and "物料一" in out
        assert "120" in out
        assert "2026-02-01" in out
        assert "WO-1001" in out
        assert "MRP-2026-001" in out
        assert "短缺发生在提前期内" in out
        # 不输出敏感商务字段
        assert "单价" not in out and "金额" not in out

    @pytest.mark.asyncio
    async def test_error_rows_first_from_service_order(self):
        # service 已按 严重级→码序→最新计算 排好序，适配层不重排
        rows = [
            _row(code="FENCE_SHORTAGE", severity="error"),
            _row(code="RESCHEDULE_IN", severity="warning"),
        ]
        svc = _service(result=_result(rows))
        with patch(SVC_PATH, return_value=svc):
            out = await mx.query_mrp_exceptions(ctx=_ctx())
        assert out.index("FENCE_SHORTAGE") < out.index("RESCHEDULE_IN")

    @pytest.mark.asyncio
    async def test_empty_result(self):
        svc = _service(result=_result([]))
        with patch(SVC_PATH, return_value=svc):
            out = await mx.query_mrp_exceptions(ctx=_ctx())
        assert "未查询到" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = _service(side_effect=RuntimeError("db down"))
        with patch(SVC_PATH, return_value=svc):
            out = await mx.query_mrp_exceptions(ctx=_ctx())
        assert out == "查询 MRP 例外失败，请稍后重试"
        assert "db down" not in out
