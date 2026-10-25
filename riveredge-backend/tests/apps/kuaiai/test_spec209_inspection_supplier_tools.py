"""KU-AI spec 209 单测：query_incoming_inspections / query_process_inspections /
query_finished_inspections / query_oqc_inspections / query_supplier_evaluations。

全部 mock / 假数据，不需要真实数据库。覆盖：
- 闭集参数（status/quality_status/date/status+period_type/period_year）非法回固定文案；
- 各 service 均不接收 current_user：适配层用 _scoped_row_ids 套各 Tool
  自身权限资源键（quality-management-*-inspection / supplier-eval）收敛；
- 摘要字段口径（单号/物料/供应商或工单或客户/检验数/合格与不合格数/结论/
  状态/检验时间；评价含周期/得分/等级）；
- masking：检验员联系方式、供应商联系人/电话/地址、单价/金额不输出；
- 空结果、底层异常、limit 截断与既有 Tool 口径一致。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaiai.services.tools import inspection_supplier as isp
from core.ai.runtime.context import AiRuntimeContext

TENANT = 7
USER_ID = 5


def _ctx():
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
    )


def _inspection_row(**kw):
    base = dict(
        id=101,
        inspection_code="IQ-2026-001",
        material_id=1,
        material_code="M-001",
        material_name="物料一",
        supplier_id=3,
        supplier_name="供应商甲",
        work_order_id=9,
        work_order_code="WO-2026-001",
        operation_name="数控加工",
        customer_name="客户乙",
        shipment_notice_code="SN-2026-001",
        release_decision="released",
        inspection_quantity=Decimal("100"),
        qualified_quantity=Decimal("95"),
        unqualified_quantity=Decimal("5"),
        inspection_result="已检验",
        quality_status="不合格",
        status="已检验",
        inspector_name="张三",
        review_status="待审核",
        inspection_time=datetime(2026, 1, 10, 9, 0),
        nonconformance_reason="尺寸超差",
    )
    base.update(kw)
    return base


def _eval_row(**kw):
    base = dict(
        id=201,
        code="SE-2026-001",
        period_type="quarterly",
        period_year=2026,
        period_quarter=1,
        supplier_id=3,
        supplier_code="SUP-003",
        supplier_name="供应商甲",
        template_code="SET-001",
        template_name="默认评价模板",
        audit_mode="document",
        score=Decimal("87.5"),
        grade="B",
        needs_rectification=True,
        rectification_status="open",
        status="approved",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _eval_result(rows, total=None):
    return SimpleNamespace(
        data=rows, total=len(rows) if total is None else total, success=True
    )


def _scope_patch(visible):
    return patch(
        "apps.kuaiai.services.scene_tools._scoped_row_ids",
        new=AsyncMock(return_value=set(visible)),
    )


_IQC_PATCH = (
    "apps.kuaizhizao.services.quality_service.IncomingInspectionService"
)
_IPQC_PATCH = (
    "apps.kuaizhizao.services.quality_service.ProcessInspectionService"
)
_FQC_PATCH = (
    "apps.kuaizhizao.services.quality_service.FinishedGoodsInspectionService"
)
_OQC_PATCH = (
    "apps.kuaizhizao.services.quality_improvement_service.OQCInspectionService"
)
_EVAL_PATCH = (
    "apps.kuaizhizao.services.supplier_evaluation_service"
    ".SupplierEvaluationService"
)


class TestQueryIncomingInspections:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await isp.query_incoming_inspections(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_enums_and_dates(self):
        out = await isp.query_incoming_inspections(status="bogus", ctx=_ctx())
        assert "status" in out and "待检验" in out
        out = await isp.query_incoming_inspections(
            quality_status="maybe", ctx=_ctx()
        )
        assert "quality_status" in out and "合格" in out
        out = await isp.query_incoming_inspections(
            date_start="2026/01/01", ctx=_ctx()
        )
        assert "date_start" in out
        out = await isp.query_incoming_inspections(date_end="abc", ctx=_ctx())
        assert "date_end" in out

    @pytest.mark.asyncio
    async def test_rows_scoped_and_summarized(self):
        svc = SimpleNamespace(
            list_incoming_inspections=AsyncMock(
                return_value={
                    "data": [
                        _inspection_row(id=101),
                        _inspection_row(id=102, inspection_code="IQ-2026-002"),
                    ],
                    "total": 2,
                    "success": True,
                }
            )
        )
        with patch(_IQC_PATCH, return_value=svc), _scope_patch({101}) as m:
            out = await isp.query_incoming_inspections(ctx=_ctx())
        kw = svc.list_incoming_inspections.await_args.kwargs
        assert svc.list_incoming_inspections.await_args.args[0] == TENANT
        # 范围资源键 = 本 Tool 权限资源段
        assert m.await_args.args[2] == (
            "kuaizhizao:quality-management-incoming-inspection"
        )
        assert "共 1 张来料检验单" in out
        assert "IQ-2026-001" in out and "IQ-2026-002" not in out
        assert "供应商甲" in out and "M-001" in out
        assert "检验 100" in out and "合格 95" in out and "不合格 5" in out
        assert "结论 不合格" in out and "状态 已检验" in out
        assert "2026-01-10" in out
        # 敏感字段不输出（人名/联系方式/商务字段）
        assert "张三" not in out
        assert "电话" not in out and "联系人" not in out and "地址" not in out
        assert "单价" not in out and "金额" not in out

    @pytest.mark.asyncio
    async def test_filters_passed_through(self):
        svc = SimpleNamespace(
            list_incoming_inspections=AsyncMock(
                return_value={"data": [], "total": 0, "success": True}
            )
        )
        with patch(_IQC_PATCH, return_value=svc):
            out = await isp.query_incoming_inspections(
                keyword="IQ",
                supplier_id=3,
                material_id=1,
                status="待检验",
                quality_status="合格",
                date_start="2026-01-01",
                date_end="2026-01-31",
                ctx=_ctx(),
            )
        kw = svc.list_incoming_inspections.await_args.kwargs
        assert kw["keyword"] == "IQ"
        assert kw["supplier_id"] == 3 and kw["material_id"] == 1
        assert kw["status"] == "待检验" and kw["quality_status"] == "合格"
        assert kw["inspection_start_date"] == date(2026, 1, 1)
        assert kw["inspection_end_date"] == date(2026, 1, 31)
        assert "未查询到" in out

    @pytest.mark.asyncio
    async def test_all_out_of_scope_truthful_copy(self):
        svc = SimpleNamespace(
            list_incoming_inspections=AsyncMock(
                return_value={"data": [_inspection_row()], "total": 1}
            )
        )
        with patch(_IQC_PATCH, return_value=svc), _scope_patch(set()):
            out = await isp.query_incoming_inspections(ctx=_ctx())
        assert "数据范围内" in out and "未查询到" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = SimpleNamespace(
            list_incoming_inspections=AsyncMock(
                side_effect=RuntimeError("db down")
            )
        )
        with patch(_IQC_PATCH, return_value=svc):
            out = await isp.query_incoming_inspections(ctx=_ctx())
        assert out == "查询来料检验单失败，请稍后重试"
        assert "db down" not in out

    @pytest.mark.asyncio
    async def test_limit_clamped(self):
        rows = [
            _inspection_row(id=1000 + i, inspection_code=f"IQ-{i}")
            for i in range(30)
        ]
        svc = SimpleNamespace(
            list_incoming_inspections=AsyncMock(
                return_value={"data": rows, "total": 30}
            )
        )
        with patch(_IQC_PATCH, return_value=svc), _scope_patch(
            {r["id"] for r in rows}
        ):
            out = await isp.query_incoming_inspections(limit=99, ctx=_ctx())
        assert svc.list_incoming_inspections.await_args.kwargs["limit"] <= 100
        assert "返回前 20 张" in out


class TestQueryProcessInspections:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await isp.query_process_inspections(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_rows_scoped_and_summarized(self):
        svc = SimpleNamespace(
            list_process_inspections=AsyncMock(
                return_value={
                    "data": [
                        _inspection_row(id=101),
                        _inspection_row(id=102, inspection_code="IP-2026-002"),
                    ],
                    "total": 2,
                }
            )
        )
        with patch(_IPQC_PATCH, return_value=svc), _scope_patch({101, 102}):
            out = await isp.query_process_inspections(
                work_order_id=9, operation_id=5, ctx=_ctx()
            )
        kw = svc.list_process_inspections.await_args.kwargs
        assert svc.list_process_inspections.await_args.args[0] == TENANT
        assert kw["work_order_id"] == 9 and kw["operation_id"] == 5
        assert "共 2 张过程检验单" in out
        assert "工单 WO-2026-001" in out and "工序 数控加工" in out
        # 无供应商段（过程检验按工单）
        assert "供应商" not in out

    @pytest.mark.asyncio
    async def test_invalid_status(self):
        out = await isp.query_process_inspections(status="bogus", ctx=_ctx())
        assert "status" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = SimpleNamespace(
            list_process_inspections=AsyncMock(side_effect=RuntimeError("x"))
        )
        with patch(_IPQC_PATCH, return_value=svc):
            out = await isp.query_process_inspections(ctx=_ctx())
        assert out == "查询过程检验单失败，请稍后重试"

    @pytest.mark.asyncio
    async def test_empty_result(self):
        svc = SimpleNamespace(
            list_process_inspections=AsyncMock(
                return_value={"data": [], "total": 0}
            )
        )
        with patch(_IPQC_PATCH, return_value=svc):
            out = await isp.query_process_inspections(ctx=_ctx())
        assert "未查询到" in out


class TestQueryFinishedInspections:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await isp.query_finished_inspections(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_rows_scoped_and_summarized(self):
        svc = SimpleNamespace(
            list_finished_goods_inspections=AsyncMock(
                return_value={
                    "data": [_inspection_row(id=101)],
                    "total": 1,
                }
            )
        )
        with patch(_FQC_PATCH, return_value=svc), _scope_patch({101}) as m:
            out = await isp.query_finished_inspections(
                work_order_id=9, ctx=_ctx()
            )
        kw = svc.list_finished_goods_inspections.await_args.kwargs
        assert kw["work_order_id"] == 9
        assert m.await_args.args[2] == (
            "kuaizhizao:quality-management-finished-goods-inspection"
        )
        assert "共 1 张成品检验单" in out
        assert "工单 WO-2026-001" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = SimpleNamespace(
            list_finished_goods_inspections=AsyncMock(
                side_effect=RuntimeError("x")
            )
        )
        with patch(_FQC_PATCH, return_value=svc):
            out = await isp.query_finished_inspections(ctx=_ctx())
        assert out == "查询成品检验单失败，请稍后重试"


class TestQueryOqcInspections:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await isp.query_oqc_inspections(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_no_keyword_param(self):
        # OQC service keyword 过滤器引用不存在字段 sales_delivery_code（恒
        # FieldError），Tool 不暴露 keyword 参数
        import inspect as _inspect

        sig = _inspect.signature(isp.query_oqc_inspections)
        assert "keyword" not in sig.parameters

    @pytest.mark.asyncio
    async def test_rows_scoped_and_summarized(self):
        svc = SimpleNamespace(
            list=AsyncMock(
                return_value={
                    "data": [
                        SimpleNamespace(**_inspection_row(id=101)),
                        SimpleNamespace(
                            **_inspection_row(
                                id=102, inspection_code="OQC-2026-002"
                            )
                        ),
                    ],
                    "items": [],
                    "total": 2,
                }
            )
        )
        with patch(_OQC_PATCH, return_value=svc), _scope_patch({101}) as m:
            out = await isp.query_oqc_inspections(
                status="已检验", date_start="2026-01-01", ctx=_ctx()
            )
        kw = svc.list.await_args.kwargs
        assert svc.list.await_args.args[0] == TENANT
        assert kw["status"] == "已检验"
        assert kw["inspection_start_date"] == date(2026, 1, 1)
        assert m.await_args.args[2] == (
            "kuaizhizao:quality-management-oqc-inspection"
        )
        assert "共 1 张出货检验单" in out
        assert "客户 客户乙" in out and "发货通知 SN-2026-001" in out
        assert "放行 released" in out
        assert "OQC-2026-002" not in out

    @pytest.mark.asyncio
    async def test_invalid_status(self):
        out = await isp.query_oqc_inspections(status="bogus", ctx=_ctx())
        assert "status" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = SimpleNamespace(list=AsyncMock(side_effect=RuntimeError("x")))
        with patch(_OQC_PATCH, return_value=svc):
            out = await isp.query_oqc_inspections(ctx=_ctx())
        assert out == "查询出货检验单失败，请稍后重试"

    @pytest.mark.asyncio
    async def test_empty_result(self):
        svc = SimpleNamespace(
            list=AsyncMock(return_value={"data": [], "items": [], "total": 0})
        )
        with patch(_OQC_PATCH, return_value=svc):
            out = await isp.query_oqc_inspections(ctx=_ctx())
        assert "未查询到" in out


class TestQuerySupplierEvaluations:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await isp.query_supplier_evaluations(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_enums_and_year(self):
        out = await isp.query_supplier_evaluations(status="bogus", ctx=_ctx())
        assert "status" in out and "draft" in out
        out = await isp.query_supplier_evaluations(
            period_type="monthly", ctx=_ctx()
        )
        assert "period_type" in out and "annual" in out
        out = await isp.query_supplier_evaluations(
            period_year=1990, ctx=_ctx()
        )
        assert "period_year" in out
        out = await isp.query_supplier_evaluations(
            period_year="abc", ctx=_ctx()
        )
        assert "period_year" in out

    @pytest.mark.asyncio
    async def test_rows_scoped_and_summarized(self):
        svc = SimpleNamespace(
            list=AsyncMock(
                return_value=_eval_result(
                    [_eval_row(id=201), _eval_row(id=202, code="SE-2026-002")]
                )
            )
        )
        with patch(_EVAL_PATCH, return_value=svc), _scope_patch({201}) as m:
            out = await isp.query_supplier_evaluations(
                supplier_id=3,
                period_type="quarterly",
                period_year=2026,
                status="approved",
                ctx=_ctx(),
            )
        kw = svc.list.await_args.kwargs
        assert svc.list.await_args.args[0] == TENANT
        assert kw["supplier_id"] == 3
        assert kw["period_type"] == "quarterly" and kw["period_year"] == 2026
        assert kw["status"] == "approved"
        assert m.await_args.args[2] == "kuaizhizao:supplier-eval"
        assert "共 1 张供应商评价" in out
        assert "SE-2026-001" in out and "SE-2026-002" not in out
        assert "供应商甲" in out and "SUP-003" in out
        assert "2026 年 Q1" in out
        assert "得分 87.5" in out and "等级 B" in out
        assert "状态 approved" in out and "整改 open" in out
        # 商务敏感字段不输出
        assert "联系人" not in out and "电话" not in out and "地址" not in out
        assert "单价" not in out and "金额" not in out

    @pytest.mark.asyncio
    async def test_empty_result(self):
        svc = SimpleNamespace(list=AsyncMock(return_value=_eval_result([])))
        with patch(_EVAL_PATCH, return_value=svc):
            out = await isp.query_supplier_evaluations(ctx=_ctx())
        assert "未查询到" in out

    @pytest.mark.asyncio
    async def test_all_out_of_scope_truthful_copy(self):
        svc = SimpleNamespace(
            list=AsyncMock(return_value=_eval_result([_eval_row()]))
        )
        with patch(_EVAL_PATCH, return_value=svc), _scope_patch(set()):
            out = await isp.query_supplier_evaluations(ctx=_ctx())
        assert "数据范围内" in out and "未查询到" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = SimpleNamespace(list=AsyncMock(side_effect=RuntimeError("x")))
        with patch(_EVAL_PATCH, return_value=svc):
            out = await isp.query_supplier_evaluations(ctx=_ctx())
        assert out == "查询供应商评价失败，请稍后重试"

    @pytest.mark.asyncio
    async def test_limit_clamped(self):
        rows = [_eval_row(id=2000 + i, code=f"SE-{i}") for i in range(25)]
        svc = SimpleNamespace(list=AsyncMock(return_value=_eval_result(rows)))
        with patch(_EVAL_PATCH, return_value=svc), _scope_patch(
            {r.id for r in rows}
        ):
            out = await isp.query_supplier_evaluations(limit=99, ctx=_ctx())
        assert svc.list.await_args.kwargs["limit"] <= 100
        assert "返回前 20 张" in out
