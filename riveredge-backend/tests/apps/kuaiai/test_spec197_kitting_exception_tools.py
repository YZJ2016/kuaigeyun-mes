"""KU-AI spec 197 单测：analyze_kitting + 三个异常 Tool。

全部 mock / 假数据，不需要真实数据库。覆盖：
- analyze_kitting 只调 compute_work_order_kitting_analysis（纯计算），
  persist_kitting_analysis_result 不被触达（K1-b 无写副作用）；
- by-ID 前 _work_order_in_scope 复核，范围外按「不存在」回复；
- 三个异常 Tool 闭集枚举、双层行级范围收敛（异常自身资源键 ∩
  kuaizhizao:work-order 关联工单）；
- 无工单行口径与 page_context 一致（评审 minor-8 / spec 197 §4）：
  质量异常 work_order_id 可空保留（仍须过自身资源范围），
  缺料/延期异常 work_order_id 必填、缺关联按不存在剔除；
- 空结果、底层异常、limit 截断与既有 Tool 口径一致。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaiai.services.tools import kitting_exceptions as ke
from core.ai.runtime.context import AiRuntimeContext

TENANT = 7
USER_ID = 5


def _ctx():
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
    )


def _kitting_item(**kw):
    base = dict(
        material_id=1,
        material_code="M-001",
        material_name="物料一",
        kitting_applicable=True,
        required_quantity=Decimal("10"),
        shortage_quantity=Decimal("4"),
        main_warehouse_available=Decimal("3"),
        line_side_available=Decimal("3"),
        status="shortage",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _kitting_resp(items, rate="60.0", status="partial"):
    return SimpleNamespace(
        work_order_id=9,
        work_order_code="WO-009",
        kitting_rate=Decimal(rate),
        status=status,
        items=items,
    )


def _shortage_row(**kw):
    base = dict(
        id=1,
        work_order_id=9,
        work_order_code="WO-009",
        material_code="M-001",
        material_name="物料一",
        required_quantity=Decimal("10"),
        available_quantity=Decimal("6"),
        shortage_quantity=Decimal("4"),
        alert_level="high",
        status="pending",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _delay_row(**kw):
    base = dict(
        id=2,
        work_order_id=9,
        work_order_code="WO-009",
        planned_end_date="2026-02-01",
        delay_days=5,
        delay_reason="物料未到",
        alert_level="critical",
        status="pending",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _quality_row(**kw):
    base = dict(
        id=3,
        work_order_id=9,
        work_order_code="WO-009",
        exception_type="inspection_failure",
        material_code="M-001",
        material_name="物料一",
        batch_no="B-1",
        severity="major",
        status="pending",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _scope_patch(visible, own_visible=None):
    """行级范围替身：工单资源键回 ``visible``；异常自身资源键默认
    全放行（``own_visible`` 可指定收窄集）。"""

    async def _fake(model, ctx, resource, ids):
        if resource == "kuaizhizao:work-order":
            return set(visible)
        if own_visible is not None:
            return set(own_visible)
        return set(ids)

    return patch(
        "apps.kuaiai.services.scene_tools._scoped_row_ids",
        new=AsyncMock(side_effect=_fake),
    )


class TestAnalyzeKitting:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await ke.analyze_kitting(work_order_id=9, ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_work_order_id(self):
        out = await ke.analyze_kitting(work_order_id="abc", ctx=_ctx())
        assert "work_order_id" in out
        out = await ke.analyze_kitting(work_order_id=0, ctx=_ctx())
        assert "work_order_id" in out

    @pytest.mark.asyncio
    async def test_out_of_scope_as_not_found(self):
        with patch(
            "apps.kuaiai.services.chat_tools._work_order_in_scope",
            new=AsyncMock(return_value=False),
        ):
            out = await ke.analyze_kitting(work_order_id=9, ctx=_ctx())
        assert "不存在" in out

    @pytest.mark.asyncio
    async def test_calls_pure_compute_only_no_persist(self):
        svc = SimpleNamespace(
            compute_work_order_kitting_analysis=AsyncMock(
                return_value=_kitting_resp(
                    [
                        _kitting_item(shortage_quantity=Decimal("4")),
                        _kitting_item(
                            material_code="M-002",
                            shortage_quantity=Decimal("8"),
                            status="partial",
                        ),
                        _kitting_item(
                            material_code="M-003", shortage_quantity=Decimal("0")
                        ),
                    ]
                )
            ),
            get_work_order_kitting_analysis=AsyncMock(),
        )
        with patch(
            "apps.kuaiai.services.chat_tools._work_order_in_scope",
            new=AsyncMock(return_value=True),
        ), patch(
            "apps.kuaizhizao.services.work_order_service.WorkOrderService",
            return_value=svc,
        ), patch(
            "apps.kuaizhizao.services.work_order_readiness_service"
            ".persist_kitting_analysis_result",
            new=AsyncMock(),
        ) as m_persist:
            out = await ke.analyze_kitting(work_order_id=9, ctx=_ctx())
        # 纯计算调用、持久化包装不被触达（K1-b 无写副作用）
        svc.compute_work_order_kitting_analysis.assert_awaited_once_with(7, 9)
        svc.get_work_order_kitting_analysis.assert_not_awaited()
        m_persist.assert_not_awaited()
        assert "WO-009" in out and "60.0%" in out
        # 缺口降序：M-002(8) 在 M-001(4) 前；M-003(0) 不出现
        assert out.index("M-002") < out.index("M-001")
        assert "M-003" not in out

    @pytest.mark.asyncio
    async def test_not_found(self):
        class NotFoundError(Exception):
            pass

        svc = SimpleNamespace(
            compute_work_order_kitting_analysis=AsyncMock(
                side_effect=NotFoundError("工单不存在")
            )
        )
        with patch(
            "apps.kuaiai.services.chat_tools._work_order_in_scope",
            new=AsyncMock(return_value=True),
        ), patch(
            "apps.kuaizhizao.services.work_order_service.WorkOrderService",
            return_value=svc,
        ):
            # 真实 NotFoundError 类名判定
            exc = type("NotFoundError", (Exception,), {})
            svc.compute_work_order_kitting_analysis = AsyncMock(
                side_effect=exc("x")
            )
            out = await ke.analyze_kitting(work_order_id=9, ctx=_ctx())
        assert "不存在" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = SimpleNamespace(
            compute_work_order_kitting_analysis=AsyncMock(
                side_effect=RuntimeError("db down")
            )
        )
        with patch(
            "apps.kuaiai.services.chat_tools._work_order_in_scope",
            new=AsyncMock(return_value=True),
        ), patch(
            "apps.kuaizhizao.services.work_order_service.WorkOrderService",
            return_value=svc,
        ):
            out = await ke.analyze_kitting(work_order_id=9, ctx=_ctx())
        assert out == "查询工单齐套分析失败，请稍后重试"
        assert "db down" not in out


class TestQueryMaterialShortages:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await ke.query_material_shortages(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_enums(self):
        out = await ke.query_material_shortages(
            statuses="pending,bogus", ctx=_ctx()
        )
        assert "statuses" in out
        out = await ke.query_material_shortages(
            alert_level="bad", ctx=_ctx()
        )
        assert "alert_level" in out

    @pytest.mark.asyncio
    async def test_rows_scoped_by_work_order(self):
        svc = SimpleNamespace(
            list_material_shortage_exceptions=AsyncMock(
                return_value=(
                    [_shortage_row(id=1, work_order_id=9),
                     _shortage_row(id=2, work_order_id=10)],
                    2,
                )
            )
        )
        with patch(
            "apps.kuaizhizao.services.exception_service.ExceptionService",
            return_value=svc,
        ), _scope_patch({9}) as m_scope:
            out = await ke.query_material_shortages(ctx=_ctx())
        kw = svc.list_material_shortage_exceptions.await_args.kwargs
        assert kw["limit"] <= 100
        assert m_scope.await_args.args[2] == "kuaizhizao:work-order"
        assert m_scope.await_args.args[3] == {9, 10}
        assert "共 1 条" in out
        assert "WO-009" in out and "M-001" in out
        assert "high" in out and "pending" in out
        assert "金额" not in out

    @pytest.mark.asyncio
    async def test_null_work_order_row_dropped(self):
        """缺料异常 work_order_id 为必填字段：缺关联行按不存在剔除
        （与 page_context._material_shortage_summary 同口径）。"""
        svc = SimpleNamespace(
            list_material_shortage_exceptions=AsyncMock(
                return_value=(
                    [_shortage_row(id=1, work_order_id=9),
                     _shortage_row(id=2, work_order_id=None,
                                 work_order_code=None, material_code="M-009")],
                    2,
                )
            )
        )
        with patch(
            "apps.kuaizhizao.services.exception_service.ExceptionService",
            return_value=svc,
        ), _scope_patch({9}):
            out = await ke.query_material_shortages(ctx=_ctx())
        assert "共 1 条" in out
        assert "M-009" not in out

    @pytest.mark.asyncio
    async def test_own_resource_scope_filters_rows(self):
        """异常行先过自身资源键范围：缺料行 id 不在可见集即剔除。"""
        svc = SimpleNamespace(
            list_material_shortage_exceptions=AsyncMock(
                return_value=(
                    [_shortage_row(id=1, work_order_id=9),
                     _shortage_row(id=2, work_order_id=9,
                                 material_code="M-009")],
                    2,
                )
            )
        )
        with patch(
            "apps.kuaizhizao.services.exception_service.ExceptionService",
            return_value=svc,
        ), _scope_patch({9}, own_visible={1}) as m_scope:
            out = await ke.query_material_shortages(ctx=_ctx())
        # 第一次调用为自身资源键，候选为异常行 id 集合
        first = m_scope.await_args_list[0].args
        assert first[2] == (
            "kuaizhizao:production-execution-material-shortage-exceptions"
        )
        assert first[3] == {1, 2}
        assert "共 1 条" in out
        assert "M-009" not in out

    @pytest.mark.asyncio
    async def test_empty_result(self):
        svc = SimpleNamespace(
            list_material_shortage_exceptions=AsyncMock(return_value=([], 0))
        )
        with patch(
            "apps.kuaizhizao.services.exception_service.ExceptionService",
            return_value=svc,
        ):
            out = await ke.query_material_shortages(ctx=_ctx())
        assert "未查询到" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = SimpleNamespace(
            list_material_shortage_exceptions=AsyncMock(
                side_effect=RuntimeError("x")
            )
        )
        with patch(
            "apps.kuaizhizao.services.exception_service.ExceptionService",
            return_value=svc,
        ):
            out = await ke.query_material_shortages(ctx=_ctx())
        assert out == "查询缺料异常失败，请稍后重试"


class TestQueryDeliveryDelays:
    @pytest.mark.asyncio
    async def test_invalid_enums(self):
        out = await ke.query_delivery_delays(statuses="x", ctx=_ctx())
        assert "statuses" in out
        out = await ke.query_delivery_delays(alert_level="x", ctx=_ctx())
        assert "alert_level" in out

    @pytest.mark.asyncio
    async def test_rows_scoped_and_summarized(self):
        svc = SimpleNamespace(
            list_delivery_delay_exceptions=AsyncMock(
                return_value=([_delay_row()], 1)
            )
        )
        with patch(
            "apps.kuaizhizao.services.exception_service.ExceptionService",
            return_value=svc,
        ), _scope_patch({9}):
            out = await ke.query_delivery_delays(ctx=_ctx())
        assert "共 1 条" in out
        assert "WO-009" in out and "5 天" in out
        assert "物料未到" in out and "critical" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = SimpleNamespace(
            list_delivery_delay_exceptions=AsyncMock(
                side_effect=RuntimeError("x")
            )
        )
        with patch(
            "apps.kuaizhizao.services.exception_service.ExceptionService",
            return_value=svc,
        ):
            out = await ke.query_delivery_delays(ctx=_ctx())
        assert out == "查询延期异常失败，请稍后重试"


class TestQueryQualityExceptions:
    @pytest.mark.asyncio
    async def test_invalid_enums(self):
        out = await ke.query_quality_exceptions(
            exception_type="bad", ctx=_ctx()
        )
        assert "exception_type" in out
        out = await ke.query_quality_exceptions(statuses="bad", ctx=_ctx())
        assert "statuses" in out
        out = await ke.query_quality_exceptions(severity="bad", ctx=_ctx())
        assert "severity" in out

    @pytest.mark.asyncio
    async def test_null_work_order_row_kept(self):
        svc = SimpleNamespace(
            list_quality_exceptions=AsyncMock(
                return_value=(
                    [
                        _quality_row(id=3, work_order_id=9),
                        _quality_row(
                            id=4, work_order_id=None, work_order_code=None,
                            material_code="M-009",
                        ),
                    ],
                    2,
                )
            )
        )
        with patch(
            "apps.kuaizhizao.services.exception_service.ExceptionService",
            return_value=svc,
        ), _scope_patch({9}) as m_scope:
            out = await ke.query_quality_exceptions(ctx=_ctx())
        # 只对有工单行求交；无工单行过自身资源范围后保留
        assert m_scope.await_args.args[3] == {9}
        assert "共 2 条" in out
        assert "M-001" in out and "M-009" in out
        assert "major" in out

    @pytest.mark.asyncio
    async def test_null_work_order_row_dropped_by_own_scope(self):
        """质量异常无工单行仍须过自身资源范围：越界即剔除。"""
        svc = SimpleNamespace(
            list_quality_exceptions=AsyncMock(
                return_value=(
                    [
                        _quality_row(id=3, work_order_id=9),
                        _quality_row(
                            id=4, work_order_id=None, work_order_code=None,
                            material_code="M-009",
                        ),
                    ],
                    2,
                )
            )
        )
        with patch(
            "apps.kuaizhizao.services.exception_service.ExceptionService",
            return_value=svc,
        ), _scope_patch({9}, own_visible={3}):
            out = await ke.query_quality_exceptions(ctx=_ctx())
        assert "共 1 条" in out
        assert "M-009" not in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = SimpleNamespace(
            list_quality_exceptions=AsyncMock(side_effect=RuntimeError("x"))
        )
        with patch(
            "apps.kuaizhizao.services.exception_service.ExceptionService",
            return_value=svc,
        ):
            out = await ke.query_quality_exceptions(ctx=_ctx())
        assert out == "查询质量异常失败，请稍后重试"


class TestKittingServiceSplit:
    """K1-b：get_work_order_kitting_analysis 包装 = compute + persist。"""

    @pytest.mark.asyncio
    async def test_wrapper_persists_non_no_bom(self):
        from apps.kuaizhizao.services.work_order_service import WorkOrderService

        svc = WorkOrderService()
        resp = _kitting_resp([], rate="100", status="fully_kitted")
        with patch.object(
            svc,
            "compute_work_order_kitting_analysis",
            new=AsyncMock(return_value=resp),
        ) as m_compute, patch(
            "apps.kuaizhizao.services.work_order_readiness_service"
            ".persist_kitting_analysis_result",
            new=AsyncMock(),
        ) as m_persist:
            out = await svc.get_work_order_kitting_analysis(7, 9)
        m_compute.assert_awaited_once_with(7, 9)
        m_persist.assert_awaited_once_with(7, 9, resp)
        assert out is resp

    @pytest.mark.asyncio
    async def test_wrapper_skips_persist_on_no_bom(self):
        """原方法 no_bom 提前返回不持久化，包装层保持同一可达性。"""
        from apps.kuaizhizao.services.work_order_service import WorkOrderService

        svc = WorkOrderService()
        resp = _kitting_resp([], rate="0", status="no_bom")
        with patch.object(
            svc,
            "compute_work_order_kitting_analysis",
            new=AsyncMock(return_value=resp),
        ), patch(
            "apps.kuaizhizao.services.work_order_readiness_service"
            ".persist_kitting_analysis_result",
            new=AsyncMock(),
        ) as m_persist:
            out = await svc.get_work_order_kitting_analysis(7, 9)
        m_persist.assert_not_awaited()
        assert out is resp
