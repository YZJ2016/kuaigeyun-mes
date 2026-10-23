"""KU-AI spec 195 单测：query_sales_orders / query_purchase_arrival_warnings。

全部 mock / 假数据，不需要真实数据库。覆盖：
- 闭集参数（view / status / warning_level / processing_status / 日期）非法回固定文案；
- list_sales_orders 走 view="options" 轻量路径 + current_user 透传（数据范围）；
- 交货进度用 service 同款 _merged_delivery_progress 计算；
- 敏感商务字段（电话/地址/单价/金额）不出现在输出；
- 空结果、底层异常、limit 截断与既有 Tool 口径一致。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaiai.services.tools import sales_purchase as sp
from apps.kuaizhizao.services.sales_order_service import SalesOrderService
from core.ai.runtime.context import AiRuntimeContext

TENANT = 7
USER_ID = 5


def _ctx():
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
    )


def _order_item(**kw):
    base = dict(
        material_code="M-001",
        material_name="物料一",
        required_quantity=Decimal("10"),
        delivered_quantity=Decimal("4"),
        delivery_date=date(2026, 2, 1),
        delivery_status="部分交货",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _order(**kw):
    base = dict(
        id=101,
        order_code="SO-2026-001",
        customer_name="客户甲",
        status="CONFIRMED",
        delivery_date=date(2026, 2, 10),
        total_quantity=Decimal("10"),
        items=[_order_item()],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _sales_service(data, total=None):
    service = SimpleNamespace()
    service.list_sales_orders = AsyncMock(
        return_value=SimpleNamespace(
            data=data, total=len(data) if total is None else total
        )
    )
    service._shipped_qty_by_sales_order = AsyncMock(return_value={})
    # 用真 service 静态方法，保证 Tool 输出与列表进度同口径
    service._merged_delivery_progress = (
        SalesOrderService._merged_delivery_progress
    )
    return service


def _warning_row(**kw):
    base = dict(
        id=501,
        purchase_order_item_id=501,
        order_code="PO-2026-001",
        supplier_name="供应商乙",
        material_code="M-002",
        material_name="物料二",
        unit="个",
        ordered_quantity=100.0,
        received_quantity=20.0,
        outstanding_quantity=80.0,
        required_date=date(2026, 1, 20),
        warning_level="overdue",
        day_offset=-5,
        remaining_days=0,
        overdue_days=5,
        processing_status="unprocessed",
    )
    base.update(kw)
    return base


def _warning_result(rows, total=None, summary=None):
    return {
        "data": rows,
        "total": len(rows) if total is None else total,
        "success": True,
        "summary": summary
        or {"normal": 0, "imminent": 0, "overdue": 1, "total_open_lines": 1},
    }


class TestQuerySalesOrdersParams:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await sp.query_sales_orders(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_view(self):
        out = await sp.query_sales_orders(view="evil", ctx=_ctx())
        assert "summary" in out and "lines" in out

    @pytest.mark.asyncio
    async def test_invalid_status(self):
        out = await sp.query_sales_orders(status="bogus", ctx=_ctx())
        assert "status" in out and "DRAFT" in out

    @pytest.mark.asyncio
    async def test_invalid_dates(self):
        out = await sp.query_sales_orders(start_date="2026/01/01", ctx=_ctx())
        assert "start_date" in out
        out = await sp.query_sales_orders(end_date="abc", ctx=_ctx())
        assert "end_date" in out


class TestQuerySalesOrders:
    @pytest.mark.asyncio
    async def test_summary_calls_options_light_path_and_user_scope(self):
        service = _sales_service([_order()], total=1)
        with patch(
            "apps.kuaizhizao.services.sales_order_service.SalesOrderService",
            return_value=service,
        ):
            out = await sp.query_sales_orders(ctx=_ctx())
        kw = service.list_sales_orders.await_args.kwargs
        assert service.list_sales_orders.await_args.args[0] == TENANT
        assert kw["view"] == "options"
        assert kw["include_items"] is True
        assert kw["current_user"].id == USER_ID
        assert "SO-2026-001" in out
        assert "客户甲" in out
        # 进度 = 明细已交 4 / 需求 10 = 40.0%
        assert "40.0%" in out
        # 敏感字段不输出
        assert "phone" not in out and "address" not in out
        assert "单价" not in out and "金额" not in out

    @pytest.mark.asyncio
    async def test_summary_progress_merges_shipped_qty(self):
        service = _sales_service([_order()])
        service._shipped_qty_by_sales_order = AsyncMock(
            return_value={101: Decimal("7")}
        )
        with patch(
            "apps.kuaizhizao.services.sales_order_service.SalesOrderService",
            return_value=service,
        ):
            out = await sp.query_sales_orders(ctx=_ctx())
        # 已出库 7/10=70% > 明细 4/10=40% → 取较大
        assert "70.0%" in out

    @pytest.mark.asyncio
    async def test_lines_view_lists_items(self):
        service = _sales_service([_order()])
        with patch(
            "apps.kuaizhizao.services.sales_order_service.SalesOrderService",
            return_value=service,
        ):
            out = await sp.query_sales_orders(view="lines", ctx=_ctx())
        assert "M-001" in out and "已交 4" in out
        assert "行交期" in out

    @pytest.mark.asyncio
    async def test_filters_passed_through(self):
        service = _sales_service([])
        with patch(
            "apps.kuaizhizao.services.sales_order_service.SalesOrderService",
            return_value=service,
        ):
            out = await sp.query_sales_orders(
                order_code="SO-1",
                customer_name="客户",
                status="AUDITED",
                start_date="2026-01-01",
                end_date="2026-01-31",
                ctx=_ctx(),
            )
        kw = service.list_sales_orders.await_args.kwargs
        assert kw["order_code"] == "SO-1"
        assert kw["customer_name"] == "客户"
        assert kw["status"] == "AUDITED"
        assert kw["start_date"] == date(2026, 1, 1)
        assert kw["end_date"] == date(2026, 1, 31)
        assert "未查询到" in out

    @pytest.mark.asyncio
    async def test_limit_clamped_to_20(self):
        service = _sales_service([])
        with patch(
            "apps.kuaizhizao.services.sales_order_service.SalesOrderService",
            return_value=service,
        ):
            await sp.query_sales_orders(limit=99, ctx=_ctx())
        assert service.list_sales_orders.await_args.kwargs["limit"] == 20

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        service = SimpleNamespace(
            list_sales_orders=AsyncMock(side_effect=RuntimeError("db down"))
        )
        with patch(
            "apps.kuaizhizao.services.sales_order_service.SalesOrderService",
            return_value=service,
        ):
            out = await sp.query_sales_orders(ctx=_ctx())
        assert out == "查询销售订单失败，请稍后重试"
        assert "db down" not in out


class TestQueryPurchaseArrivalWarnings:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await sp.query_purchase_arrival_warnings(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_enums(self):
        out = await sp.query_purchase_arrival_warnings(
            warning_level="bad", ctx=_ctx()
        )
        assert "warning_level" in out
        out = await sp.query_purchase_arrival_warnings(
            processing_status="bad", ctx=_ctx()
        )
        assert "processing_status" in out

    @pytest.mark.asyncio
    async def test_rows_and_summary_and_user_scope(self):
        service = SimpleNamespace(
            list_warnings=AsyncMock(
                return_value=_warning_result([_warning_row()])
            )
        )
        with patch(
            "apps.kuaizhizao.services.purchase_arrival_warning_service"
            ".PurchaseArrivalWarningService",
            return_value=service,
        ):
            out = await sp.query_purchase_arrival_warnings(ctx=_ctx())
        kw = service.list_warnings.await_args.kwargs
        assert service.list_warnings.await_args.args[0] == TENANT
        assert kw["current_user"].id == USER_ID
        assert "PO-2026-001" in out
        assert "供应商乙" in out
        assert "逾期 1" in out  # summary 计数
        assert "逾期 5 天" in out  # 行级天数
        assert "unprocessed" in out
        assert "单价" not in out and "金额" not in out

    @pytest.mark.asyncio
    async def test_empty_result(self):
        service = SimpleNamespace(
            list_warnings=AsyncMock(return_value=_warning_result([]))
        )
        with patch(
            "apps.kuaizhizao.services.purchase_arrival_warning_service"
            ".PurchaseArrivalWarningService",
            return_value=service,
        ):
            out = await sp.query_purchase_arrival_warnings(ctx=_ctx())
        assert "未查询到" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        service = SimpleNamespace(
            list_warnings=AsyncMock(side_effect=RuntimeError("x"))
        )
        with patch(
            "apps.kuaizhizao.services.purchase_arrival_warning_service"
            ".PurchaseArrivalWarningService",
            return_value=service,
        ):
            out = await sp.query_purchase_arrival_warnings(ctx=_ctx())
        assert out == "查询采购到货预警失败，请稍后重试"
