"""KU-AI spec 206 单测：query_scheduling_board。

全部 mock / 假数据，不需要真实数据库。覆盖：
- ctx 缺失 / plan_date / work_center_id 非法回固定文案；
- 事实组装复用 scheduling_ai_service 拆出的纯事实函数
  （_load_board_work_orders / scan_scheduling_board_facts）；
- 数据范围 kuaizhizao:plan-management-scheduling 收敛，scan 仅跑可见工单；
- 输出为确定性事实（工单/计划时段/冲突/未排产/缺配置/物料/超载/约束），
  不含模型生成文字；
- 不调用任何大模型：SchedulingAiService 的模型出口
  StructuredDraftService.complete_json 断言未被调用；
- 空结果、底层异常与既有 Tool 口径一致；limit ≤20 截断。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.services.tools import scheduling_board as sb
from core.ai.runtime.context import AiRuntimeContext
from core.utils.timezone_utils import to_api_isoformat

TENANT = 7
USER_ID = 5

_MOD = "apps.kuaizhizao.services.scheduling_ai_service"
_SCENE = "apps.kuaiai.services.scene_tools"


def _ctx():
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
    )


def _wo(**kw):
    base = dict(
        id=301,
        code="WO-206-001",
        name="工单甲",
        status="released",
        product_code="P-1",
        planned_start_date=datetime(2026, 10, 24, 8, 0),
        planned_end_date=datetime(2026, 10, 24, 18, 0),
        is_frozen=False,
        readiness_rate=Decimal("80"),
        work_center_id=9,
        work_center_name="机加中心",
        quantity=Decimal("100"),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _scan(**kw):
    base = {
        "conflicts": [
            {
                "type": "station_overlap",
                "message": "工位 S1：工单 WO-206-001 与工单 WO-206-002 时间重叠",
                "work_order_id": 301,
                "work_order_code": "WO-206-001",
                "operation_id": 88,
                "station_id": 5,
                "resource_id": 5,
            }
        ],
        "unscheduled_orders": [
            {
                "work_order_id": 302,
                "work_order_code": "WO-206-002",
                "reason": "未设置计划起止时间",
            }
        ],
        "material_issues": [
            {
                "work_order_id": 301,
                "work_order_code": "WO-206-001",
                "readiness_rate": 80.0,
                "message": "齐套率 80% 不足，排产前请确认物料",
            }
        ],
        "missing_settings": [
            {
                "work_order_id": 301,
                "work_order_code": "WO-206-001",
                "operation_id": 88,
                "operation_name": "钻孔",
                "field": "standard_time",
                "label": "标准工时(小时/件)",
                "current": None,
                "suggested": 1.0,
                "work_center_id": 9,
            }
        ],
        "load_by_work_center": [
            {
                "work_center_id": 9,
                "work_center_name": "机加中心",
                "day": "2026-10-24",
                "hours": 12.0,
                "rate": 100,
                "overloaded": False,
            }
        ],
        "load_by_station": [
            {
                "station_id": 5,
                "station_name": "S1",
                "day": "2026-10-24",
                "hours": 12.0,
                "rate": 100,
                "overloaded": True,
            }
        ],
        "conflict_count": 1,
        "unscheduled_count": 1,
        "material_issue_count": 1,
        "missing_settings_count": 1,
        "overloaded_station_count": 1,
    }
    base.update(kw)
    return base


def _constraints():
    return {"freeze_horizon_days": 2, "rolling_horizon_days": 14}


def _patch_facts(work_orders, scan=None, visible=None):
    """一次给齐三个事实/范围 mock，返回各 mock 供断言。"""
    loader = AsyncMock(return_value=work_orders)
    scanner = AsyncMock(
        return_value=(scan if scan is not None else _scan(), _constraints())
    )
    scope = AsyncMock(
        return_value=(
            visible
            if visible is not None
            else {int(wo.id) for wo in work_orders}
        )
    )
    return loader, scanner, scope


class TestParams:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await sb.query_scheduling_board(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_plan_date(self):
        out = await sb.query_scheduling_board(
            ctx=_ctx(), plan_date="2026/10/24"
        )
        assert "plan_date" in out and "YYYY-MM-DD" in out

    @pytest.mark.asyncio
    async def test_invalid_work_center_id(self):
        out = await sb.query_scheduling_board(ctx=_ctx(), work_center_id="abc")
        assert "work_center_id" in out


class TestQuerySchedulingBoard:
    @pytest.mark.asyncio
    async def test_happy_path_facts_and_no_model_call(self):
        wos = [_wo(), _wo(id=302, code="WO-206-002", name="工单乙")]
        loader, scanner, scope = _patch_facts(wos)
        draft = MagicMock()
        with (
            patch(f"{_MOD}._load_board_work_orders", loader),
            patch(f"{_MOD}.scan_scheduling_board_facts", scanner),
            patch(f"{_SCENE}._scoped_row_ids", scope),
            patch(f"{_MOD}.StructuredDraftService", draft),
        ):
            out = await sb.query_scheduling_board(
                ctx=_ctx(), plan_date="2026-10-24", work_center_id=9, limit=10
            )
        # 事实组装参数透传
        l_args = loader.await_args
        assert l_args.args[0] == TENANT
        assert l_args.args[2] == date(2026, 10, 24)
        assert l_args.kwargs["work_center_id"] == 9
        s_kwargs = scanner.await_args.kwargs
        assert s_kwargs["work_order_ids"] == [301, 302]
        assert s_kwargs["work_center_id"] == 9
        assert s_kwargs["plan_date"] == date(2026, 10, 24)
        # 数据范围资源键
        scope_args = scope.await_args.args
        assert scope_args[2] == "kuaizhizao:plan-management-scheduling"
        # 无模型调用（X1=a 纯事实 Tool）
        draft.complete_json.assert_not_called()
        # 确定性事实输出
        assert "WO-206-001" in out and "工单甲" in out
        assert "2026-10-24" in out
        assert "机加中心" in out
        assert "已下达" in out
        assert "齐套率 80%" in out
        assert "station_overlap" in out and "时间重叠" in out
        assert "WO-206-002" in out and "未设置计划起止时间" in out
        assert "缺 标准工时" in out or "标准工时(小时/件)" in out
        assert "齐套率 80% 不足" in out
        assert "S1" in out and "负荷率 100%" in out
        assert "冻结窗 2 天" in out and "滚动窗 14 天" in out
        # 不含任何模型生成文字字段
        assert "answer" not in out and "rationale" not in out

    @pytest.mark.asyncio
    async def test_planned_dates_use_api_isoformat(self):
        """计划起止（DatetimeField）走 to_api_isoformat 站点时区口径。"""
        wos = [_wo()]
        loader, scanner, scope = _patch_facts(wos)
        with (
            patch(f"{_MOD}._load_board_work_orders", loader),
            patch(f"{_MOD}.scan_scheduling_board_facts", scanner),
            patch(f"{_SCENE}._scoped_row_ids", scope),
        ):
            out = await sb.query_scheduling_board(ctx=_ctx(), limit=10)
        expected_start = to_api_isoformat(datetime(2026, 10, 24, 8, 0))
        expected_end = to_api_isoformat(datetime(2026, 10, 24, 18, 0))
        assert f"计划 {expected_start} → {expected_end}" in out

    @pytest.mark.asyncio
    async def test_scope_filters_and_scan_restricted_to_visible(self):
        wos = [_wo(), _wo(id=302, code="WO-206-002")]
        loader, scanner, scope = _patch_facts(wos, visible={301})
        with (
            patch(f"{_MOD}._load_board_work_orders", loader),
            patch(f"{_MOD}.scan_scheduling_board_facts", scanner),
            patch(f"{_SCENE}._scoped_row_ids", scope),
        ):
            out = await sb.query_scheduling_board(ctx=_ctx())
        # scan 只跑可见工单集合
        assert scanner.await_args.kwargs["work_order_ids"] == [301]
        assert "看板工单 1 张" in out
        assert "WO-206-001" in out

    @pytest.mark.asyncio
    async def test_empty_candidates(self):
        loader, scanner, scope = _patch_facts([])
        with (
            patch(f"{_MOD}._load_board_work_orders", loader),
            patch(f"{_MOD}.scan_scheduling_board_facts", scanner),
            patch(f"{_SCENE}._scoped_row_ids", scope),
        ):
            out = await sb.query_scheduling_board(ctx=_ctx())
        assert "未查询到" in out
        scanner.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_visible(self):
        loader, scanner, scope = _patch_facts([_wo()], visible=set())
        with (
            patch(f"{_MOD}._load_board_work_orders", loader),
            patch(f"{_MOD}.scan_scheduling_board_facts", scanner),
            patch(f"{_SCENE}._scoped_row_ids", scope),
        ):
            out = await sb.query_scheduling_board(ctx=_ctx())
        assert "未查询到" in out
        scanner.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_loader_error_fixed_text(self):
        loader = AsyncMock(side_effect=RuntimeError("db down"))
        with patch(f"{_MOD}._load_board_work_orders", loader):
            out = await sb.query_scheduling_board(ctx=_ctx())
        assert out == "查询排程看板失败，请稍后重试"
        assert "db down" not in out

    @pytest.mark.asyncio
    async def test_scope_error_fixed_text(self):
        loader, scanner, _ = _patch_facts([_wo()])
        scope = AsyncMock(side_effect=RuntimeError("scope down"))
        with (
            patch(f"{_MOD}._load_board_work_orders", loader),
            patch(f"{_MOD}.scan_scheduling_board_facts", scanner),
            patch(f"{_SCENE}._scoped_row_ids", scope),
        ):
            out = await sb.query_scheduling_board(ctx=_ctx())
        assert out == "查询排程看板失败，请稍后重试"

    @pytest.mark.asyncio
    async def test_scan_error_fixed_text(self):
        wos = [_wo()]
        loader, scanner, scope = _patch_facts(wos)
        scanner.side_effect = RuntimeError("scan down")
        with (
            patch(f"{_MOD}._load_board_work_orders", loader),
            patch(f"{_MOD}.scan_scheduling_board_facts", scanner),
            patch(f"{_SCENE}._scoped_row_ids", scope),
        ):
            out = await sb.query_scheduling_board(ctx=_ctx())
        assert out == "查询排程看板失败，请稍后重试"

    @pytest.mark.asyncio
    async def test_limit_clamped_to_20(self):
        wos = [_wo(id=1000 + i, code=f"WO-{i:03d}") for i in range(25)]
        loader, scanner, scope = _patch_facts(wos, scan=_scan(conflicts=[]))
        with (
            patch(f"{_MOD}._load_board_work_orders", loader),
            patch(f"{_MOD}.scan_scheduling_board_facts", scanner),
            patch(f"{_SCENE}._scoped_row_ids", scope),
        ):
            out = await sb.query_scheduling_board(ctx=_ctx(), limit=99)
        assert "看板工单 25 张，返回前 20 张" in out
        assert "另有 5 张未展开" in out
        assert "WO-019" in out and "WO-020" not in out
