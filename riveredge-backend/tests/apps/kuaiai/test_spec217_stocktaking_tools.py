"""spec 217（S22 盘点差异解读）Tool 单元测试。

全部 mock / 假数据，不需要真实数据库。覆盖：
- ``query_stocktakings``：status 闭集、日期格式、参数透传
  ``list_stocktakings``、行级范围收敛、输出单号/仓库/范围/状态/时间；
- ``analyze_stocktaking_variance``：view 闭集、按单须 stocktaking_id、
  history 与 stocktaking_id 互斥、按视图拆判读权限（明细
  ``warehouse-management-stocktaking:read`` / 历史
  ``reports-stocktaking-history:read``）、源单行级范围外按不存在、
  差异聚合可复算（Σ账存/实盘/差异/金额、差异率、盘盈盘亏）、TopN 排序、
  物料类别汇总、无差异「账实一致」、未盘行提示、不输出操作员姓名；
- ``view=history``：各盘点单差异率趋势 + 库位差异汇总、范围内无单如实、
  范围内收敛（_apply_scope 套 reports-stocktaking-history 资源）。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.services.tools import stocktaking as st
from apps.kuaizhizao.models.stocktaking import Stocktaking, StocktakingItem
from apps.kuaizhizao.services.stocktaking_service import StocktakingService
from apps.master_data.models.material import Material, MaterialGroup
from core.ai.runtime.context import AiRuntimeContext
from infra.exceptions.exceptions import NotFoundError

TENANT = 7
USER_ID = 5

_SCOPE_IDS = "apps.kuaiai.services.scene_tools._scoped_row_ids"
_APPLY_SCOPE = "apps.kuaiai.services.scene_tools._apply_scope"
_PERM_VIEW = "apps.kuaiai.services.tools.document_chain._perm_view"

_PERM_ORDER = "kuaizhizao:warehouse-management-stocktaking:read"
_PERM_HISTORY = (
    "kuaizhizao:warehouse-management-reports-stocktaking-history:read"
)


def _ctx(admin: bool = True):
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
        is_tenant_admin=admin,
    )


def _qs(rows=(), first=None):
    q = MagicMock()
    for m in ("filter", "order_by", "offset", "limit"):
        setattr(q, m, MagicMock(return_value=q))
    q.all = AsyncMock(return_value=list(rows))
    q.first = AsyncMock(
        return_value=first if first is not None else (rows[0] if rows else None)
    )
    q.count = AsyncMock(return_value=len(rows))
    q.exists = AsyncMock(return_value=bool(rows))
    q.values = AsyncMock(return_value=list(rows))
    q.values_list = AsyncMock(return_value=list(rows))
    return q


def _scope_all():
    return AsyncMock(side_effect=lambda model, ctx, resource, ids: set(ids))


def _scope_visible(*allowed):
    allow = set(allowed)
    return AsyncMock(
        side_effect=lambda model, ctx, resource, ids: set(ids) & allow
    )


def _apply_scope_passthrough():
    return AsyncMock(side_effect=lambda qs, tenant_id, ctx, resource: qs)


def _perm(*codes):
    return AsyncMock(return_value=(False, frozenset(codes)))


def _stocktaking_row(**kw):
    base = dict(
        id=42,
        code="ST20260105001",
        warehouse_name="原料仓",
        stocktaking_date=datetime(2026, 1, 5, 10, 0),
        status="completed",
        stocktaking_type="full",
        line_granularity="batch",
        include_zero_stock=False,
        total_items=5,
        counted_items=4,
        total_differences=3,
        total_difference_amount=Decimal("5"),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _item(**kw):
    base = dict(
        id=1,
        stocktaking_id=42,
        material_id=1,
        material_code="M-1",
        material_name="外壳",
        material_unit="个",
        warehouse_id=1,
        location_code="A-01",
        batch_no="B-1",
        book_quantity=Decimal("100"),
        actual_quantity=Decimal("90"),
        difference_quantity=Decimal("-10"),
        unit_price=Decimal("5"),
        difference_amount=Decimal("-50"),
        status="counted",
        counted_by_name="张三",
        created_by_name="李四",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _detail(items, **kw):
    base = dict(
        id=42,
        code="ST20260105001",
        warehouse_name="原料仓",
        stocktaking_date=datetime(2026, 1, 5, 10, 0),
        status="completed",
        stocktaking_type="full",
        items=list(items),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _svc(method, return_value=None, side_effect=None):
    return patch.object(
        StocktakingService,
        method,
        AsyncMock(return_value=return_value, side_effect=side_effect),
    )


class TestQueryStocktakings:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await st.query_stocktakings(ctx=None)
        assert "缺少租户/用户上下文" in out

    @pytest.mark.asyncio
    async def test_status_closed_set(self):
        out = await st.query_stocktakings(status="bogus", ctx=_ctx())
        assert "status 仅支持 draft/in_progress/completed/cancelled" in out

    @pytest.mark.asyncio
    async def test_bad_date(self):
        out = await st.query_stocktakings(date_start="01/05", ctx=_ctx())
        assert "date_start 须为 YYYY-MM-DD" in out
        out = await st.query_stocktakings(date_end="x", ctx=_ctx())
        assert "date_end 须为 YYYY-MM-DD" in out

    @pytest.mark.asyncio
    async def test_list_passes_filters_and_formats(self):
        resp = SimpleNamespace(items=[_stocktaking_row()], total=1)
        with (
            _svc("list_stocktakings", return_value=resp) as m_list,
            patch(_SCOPE_IDS, _scope_all()),
        ):
            out = await st.query_stocktakings(
                keyword="ST2026",
                status="completed",
                warehouse_id=1,
                date_start="2026-01-01",
                date_end="2026-01-31",
                ctx=_ctx(),
            )
        m_list.assert_awaited_once_with(
            TENANT,
            skip=0,
            limit=50,
            keyword="ST2026",
            warehouse_id=1,
            status="completed",
            stocktaking_date_start="2026-01-01",
            stocktaking_date_end="2026-01-31",
        )
        assert "ST20260105001" in out
        assert "原料仓" in out
        assert "全盘/批次粒度" in out
        assert "已完成(completed)" in out
        assert "2026-01-05" in out
        assert "差异 3" in out and "id=42" in out

    @pytest.mark.asyncio
    async def test_scope_filter(self):
        resp = SimpleNamespace(
            items=[_stocktaking_row(id=42), _stocktaking_row(id=43, code="ST2")],
            total=2,
        )
        with (
            _svc("list_stocktakings", return_value=resp),
            patch(_SCOPE_IDS, _scope_visible(43)),
        ):
            out = await st.query_stocktakings(ctx=_ctx())
        assert "ST2" in out and "ST20260105001" not in out
        assert "当前用户数据范围内" in out

    @pytest.mark.asyncio
    async def test_scope_empty(self):
        resp = SimpleNamespace(items=[_stocktaking_row()], total=1)
        with (
            _svc("list_stocktakings", return_value=resp),
            patch(_SCOPE_IDS, _scope_visible()),
        ):
            out = await st.query_stocktakings(ctx=_ctx())
        assert "当前用户数据范围内未查询到符合条件的盘点单" in out

    @pytest.mark.asyncio
    async def test_empty(self):
        resp = SimpleNamespace(items=[], total=0)
        with _svc("list_stocktakings", return_value=resp):
            out = await st.query_stocktakings(ctx=_ctx())
        assert "未查询到符合条件的盘点单" in out

    @pytest.mark.asyncio
    async def test_error_fixed_text(self):
        with _svc("list_stocktakings", side_effect=RuntimeError("x")):
            out = await st.query_stocktakings(ctx=_ctx())
        assert "查询盘点单失败，请稍后重试" in out

    @pytest.mark.asyncio
    async def test_header_candidate_window_note(self):
        """头部注明计数口径：过采样上限内的候选计数（非全量总数）。"""
        resp = SimpleNamespace(items=[_stocktaking_row()], total=1)
        with (
            _svc("list_stocktakings", return_value=resp),
            patch(_SCOPE_IDS, _scope_all()),
        ):
            out = await st.query_stocktakings(ctx=_ctx())
        assert "前 100 条候选内计" in out

    @pytest.mark.asyncio
    async def test_limit_clamped(self):
        """limit 钳位：>20 钳到 20（返回前 N 条与 _clamp_limit 同口径）。"""
        resp = SimpleNamespace(
            items=[
                _stocktaking_row(id=i, code=f"ST{i:05d}")
                for i in range(1, 26)
            ],
            total=25,
        )
        with (
            _svc("list_stocktakings", return_value=resp),
            patch(_SCOPE_IDS, _scope_all()),
        ):
            out = await st.query_stocktakings(limit=999, ctx=_ctx())
        assert "共 25 张盘点单" in out and "返回前 20 条" in out


class TestAnalyzeParams:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await st.analyze_stocktaking_variance(ctx=None)
        assert "缺少租户/用户上下文" in out

    @pytest.mark.asyncio
    async def test_view_closed_set(self):
        out = await st.analyze_stocktaking_variance(view="bogus", ctx=_ctx())
        assert "view 仅支持" in out

    @pytest.mark.asyncio
    async def test_order_requires_stocktaking_id(self):
        out = await st.analyze_stocktaking_variance(ctx=_ctx())
        assert "须提供 stocktaking_id" in out

    @pytest.mark.asyncio
    async def test_history_mutex_stocktaking_id(self):
        out = await st.analyze_stocktaking_variance(
            stocktaking_id=1, view="history", ctx=_ctx()
        )
        assert "不能同时使用" in out


class TestAnalyzeByOrder:
    def _items(self):
        return [
            _item(),
            _item(
                id=2,
                material_id=2,
                material_code="M-2",
                material_name="内衬",
                book_quantity=Decimal("50"),
                actual_quantity=Decimal("60"),
                difference_quantity=Decimal("10"),
                difference_amount=Decimal("30"),
            ),
            _item(
                id=3,
                material_id=3,
                material_code="M-3",
                material_name="标签",
                book_quantity=Decimal("20"),
                actual_quantity=Decimal("20"),
                difference_quantity=Decimal("0"),
                difference_amount=Decimal("0"),
            ),
            _item(
                id=4,
                material_id=4,
                material_code="M-4",
                material_name="垫片",
                location_code="A-02",
                book_quantity=Decimal("0"),
                actual_quantity=Decimal("5"),
                difference_quantity=Decimal("5"),
                difference_amount=Decimal("25"),
            ),
            _item(
                id=5,
                material_id=5,
                material_code="M-5",
                material_name="螺钉",
                book_quantity=Decimal("10"),
                actual_quantity=None,
                difference_quantity=Decimal("0"),
                difference_amount=Decimal("0"),
                status="pending",
            ),
        ]

    @pytest.mark.asyncio
    async def test_order_permission_denied(self):
        # 只有历史报表权限、无盘点单读权限 → 按单视图拒绝（视图拆判）
        with patch(_PERM_VIEW, _perm(_PERM_HISTORY)):
            out = await st.analyze_stocktaking_variance(
                stocktaking_id=42, ctx=_ctx(admin=False)
            )
        assert "无权查看盘点单明细" in out

    @pytest.mark.asyncio
    async def test_order_out_of_scope_as_not_found(self):
        with (
            patch(_PERM_VIEW, _perm(_PERM_ORDER)),
            patch(_SCOPE_IDS, _scope_visible()),
        ):
            out = await st.analyze_stocktaking_variance(
                stocktaking_id=42, ctx=_ctx(admin=False)
            )
        assert "盘点单不存在或超出当前用户数据范围" in out

    @pytest.mark.asyncio
    async def test_order_non_integer_id_as_not_found(self):
        """非整型 stocktaking_id 按不存在固定文案（不抛异常、不查库）。"""
        with patch(_PERM_VIEW, _perm(_PERM_ORDER)):
            out = await st.analyze_stocktaking_variance(
                stocktaking_id="abc", ctx=_ctx(admin=False)
            )
        assert "盘点单不存在或超出当前用户数据范围" in out

    @pytest.mark.asyncio
    async def test_order_not_found(self):
        with (
            patch(_PERM_VIEW, _perm(_PERM_ORDER)),
            patch(_SCOPE_IDS, _scope_all()),
            _svc(
                "get_stocktaking_by_id",
                side_effect=NotFoundError("盘点单不存在"),
            ),
        ):
            out = await st.analyze_stocktaking_variance(
                stocktaking_id=42, ctx=_ctx(admin=False)
            )
        assert "盘点单不存在或超出当前用户数据范围" in out

    @pytest.mark.asyncio
    async def test_order_no_items(self):
        with (
            patch(_PERM_VIEW, _perm(_PERM_ORDER)),
            patch(_SCOPE_IDS, _scope_all()),
            _svc("get_stocktaking_by_id", return_value=_detail([])),
        ):
            out = await st.analyze_stocktaking_variance(
                stocktaking_id=42, ctx=_ctx(admin=False)
            )
        assert "暂无盘点明细" in out

    @pytest.mark.asyncio
    async def test_order_aggregation_recomputable(self):
        with (
            patch(_PERM_VIEW, _perm(_PERM_ORDER)),
            patch(_SCOPE_IDS, _scope_all()),
            _svc(
                "get_stocktaking_by_id",
                return_value=_detail(self._items()),
            ),
            patch.object(
                Material,
                "filter",
                MagicMock(
                    return_value=_qs(
                        [
                            {"id": 1, "group_id": 10},
                            {"id": 2, "group_id": 10},
                            {"id": 4, "group_id": 20},
                        ]
                    )
                ),
            ),
            patch.object(
                MaterialGroup,
                "filter",
                MagicMock(
                    return_value=_qs(
                        [
                            {"id": 10, "name": "结构件"},
                            {"id": 20, "name": "辅料"},
                        ]
                    )
                ),
            ),
        ):
            out = await st.analyze_stocktaking_variance(
                stocktaking_id=42, ctx=_ctx(admin=False)
            )
        # 头部合计可复算：Σ账存 180、Σ差异量 +5、Σ差异金额 +5、差异行 3、未盘 1
        assert "明细 5 行" in out
        assert "已盘 4 行" in out and "含 1 行未录入实盘" in out
        assert "差异 3 行" in out
        assert "账面合计 180" in out
        assert "差异量合计 5" in out and "差异金额合计 5" in out
        assert "数量差异率 2.8%" in out  # |5|/180
        # TopN 按|差异金额|降序：M-1(50) > M-2(30) > M-4(25)
        i1, i2, i4 = out.index("M-1"), out.index("M-2"), out.index("M-4")
        assert i1 < i2 < i4
        assert "账存 100/实盘 90/差异 -10（盘亏）/差异金额 -50/差异率 10.0%" in out
        assert "账存 50/实盘 60/差异 10（盘盈）/差异金额 30/差异率 20.0%" in out
        assert "差异率 —" in out  # M-4 账存为 0
        assert "M-3" not in out  # 无差异物料不进 TopN
        # 类别汇总：辅料(M-4)=+25 > 结构件(M-1+M-2)=-20
        assert "- 辅料：差异物料 1 种，差异量 5，差异金额 25" in out
        assert "- 结构件：差异物料 2 种，差异量 0，差异金额 -20" in out
        # 不输出操作员个人信息
        assert "张三" not in out and "李四" not in out

    @pytest.mark.asyncio
    async def test_order_no_variance(self):
        items = [
            _item(
                actual_quantity=Decimal("100"),
                difference_quantity=Decimal("0"),
                difference_amount=Decimal("0"),
            )
        ]
        with (
            patch(_PERM_VIEW, _perm(_PERM_ORDER)),
            patch(_SCOPE_IDS, _scope_all()),
            _svc("get_stocktaking_by_id", return_value=_detail(items)),
        ):
            out = await st.analyze_stocktaking_variance(
                stocktaking_id=42, ctx=_ctx(admin=False)
            )
        assert "账实一致" in out
        assert "Top" not in out


def _header(**kw):
    base = dict(
        id=1,
        code="ST20260105001",
        warehouse_name="原料仓",
        stocktaking_date=datetime(2026, 1, 5),
        status="completed",
    )
    base.update(kw)
    return base


def _hitem(**kw):
    base = dict(
        stocktaking_id=1,
        location_code="A-01",
        book_quantity=Decimal("100"),
        actual_quantity=Decimal("90"),
        difference_quantity=Decimal("-10"),
        difference_amount=Decimal("-50"),
    )
    base.update(kw)
    return base


class TestAnalyzeHistory:
    @pytest.mark.asyncio
    async def test_history_permission_denied(self):
        # 只有盘点单读权限、无历史报表权限 → history 视图拒绝
        with patch(_PERM_VIEW, _perm(_PERM_ORDER)):
            out = await st.analyze_stocktaking_variance(
                view="history", ctx=_ctx(admin=False)
            )
        assert "无权查看盘点历史报表" in out

    @pytest.mark.asyncio
    async def test_history_bad_date(self):
        with patch(_PERM_VIEW, _perm(_PERM_HISTORY)):
            out = await st.analyze_stocktaking_variance(
                view="history", date_start="01/05", ctx=_ctx(admin=False)
            )
        assert "date_start 须为 YYYY-MM-DD" in out

    @pytest.mark.asyncio
    async def test_history_empty(self):
        with (
            patch(_PERM_VIEW, _perm(_PERM_HISTORY)),
            patch(_APPLY_SCOPE, _apply_scope_passthrough()),
            patch.object(
                Stocktaking, "filter", MagicMock(return_value=_qs())
            ),
        ):
            out = await st.analyze_stocktaking_variance(
                view="history", ctx=_ctx(admin=False)
            )
        assert "无盘点单记录" in out

    @pytest.mark.asyncio
    async def test_history_trend_and_location(self):
        headers = [
            _header(),
            _header(
                id=2,
                code="ST20260201002",
                warehouse_name="成品仓",
                stocktaking_date=datetime(2026, 2, 1),
                status="in_progress",
            ),
        ]
        items = [
            _hitem(),
            _hitem(
                location_code="A-02",
                book_quantity=Decimal("20"),
                actual_quantity=Decimal("20"),
                difference_quantity=Decimal("0"),
                difference_amount=Decimal("0"),
            ),
            _hitem(
                stocktaking_id=2,
                location_code="A-01",
                book_quantity=Decimal("40"),
                actual_quantity=Decimal("46"),
                difference_quantity=Decimal("6"),
                difference_amount=Decimal("30"),
            ),
        ]
        with (
            patch(_PERM_VIEW, _perm(_PERM_HISTORY)),
            patch(_APPLY_SCOPE, _apply_scope_passthrough()) as m_scope,
            patch.object(
                Stocktaking,
                "filter",
                MagicMock(return_value=_qs(headers)),
            ),
            patch.object(
                StocktakingItem,
                "filter",
                MagicMock(return_value=_qs(items)),
            ),
        ):
            out = await st.analyze_stocktaking_variance(
                view="history",
                date_start="2026-01-01",
                date_end="2026-03-31",
                ctx=_ctx(admin=False),
            )
        # 行级范围套历史报表资源键
        assert m_scope.await_args.args[3] == (
            "kuaizhizao:warehouse-management-reports-stocktaking-history"
        )
        assert "范围内 2 张盘点单" in out
        # 单1：2 行明细 1 行差异 → 50.0%；|−10|/120=8.3%
        assert "ST20260105001" in out
        assert "明细 2 行/差异 1 行（差异行占比 50.0%）" in out
        assert "数量差异率 8.3%" in out
        assert "差异金额 -50" in out
        # 单2：1/1 → 100.0%；6/40=15.0%
        assert "ST20260201002" in out
        assert "明细 1 行/差异 1 行（差异行占比 100.0%）" in out
        assert "数量差异率 15.0%" in out
        # 库位：A-01 两行差异合计 -4/-20；A-02 无差异不列
        assert "- 库位 A-01：差异 2 行/明细 2 行，差异量 -4，差异金额 -20" in out
        assert "A-02" not in out
        # 日期升序：单1 在单2 前
        assert out.index("ST20260105001") < out.index("ST20260201002")

    @pytest.mark.asyncio
    async def test_history_all_consistent(self):
        headers = [_header()]
        items = [
            _hitem(
                actual_quantity=Decimal("100"),
                difference_quantity=Decimal("0"),
                difference_amount=Decimal("0"),
            )
        ]
        with (
            patch(_PERM_VIEW, _perm(_PERM_HISTORY)),
            patch(_APPLY_SCOPE, _apply_scope_passthrough()),
            patch.object(
                Stocktaking,
                "filter",
                MagicMock(return_value=_qs(headers)),
            ),
            patch.object(
                StocktakingItem,
                "filter",
                MagicMock(return_value=_qs(items)),
            ),
        ):
            out = await st.analyze_stocktaking_variance(
                view="history", ctx=_ctx(admin=False)
            )
        assert "账实一致" in out
