"""KU-AI spec 196 单测：query_inventory_alerts / query_replenishment_suggestions
/ query_slow_moving_inventory。

全部 mock / 假数据，不需要真实数据库。覆盖：
- 闭集参数（alert_type/status/alert_level/priority/suggestion_type）非法回固定文案；
- 三个底层 service 均不接收 current_user：适配层用 _scoped_row_ids /
  _slow_moving_visible 套 ``kuaizhizao:inventory`` 资源收敛；
- 摘要字段口径（物料/仓库/类型/级别/量/阈值/状态、建议量/下单日期、库龄），
  不含金额类字段；
- 空结果、底层异常、limit 截断与既有 Tool 口径一致。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaiai.services.tools import inventory_alerts as ia
from core.ai.runtime.context import AiRuntimeContext

TENANT = 7
USER_ID = 5


def _ctx():
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
    )


def _alert_row(**kw):
    base = dict(
        id=11,
        alert_type="low_stock",
        alert_level="warning",
        status="pending",
        material_id=1,
        material_code="M-001",
        material_name="物料一",
        warehouse_id=2,
        warehouse_name="原料仓",
        current_quantity=Decimal("5"),
        threshold_value=Decimal("10"),
        alert_message="低于安全库存",
        triggered_at=datetime(2026, 1, 10, 8, 0),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _suggestion_row(**kw):
    base = dict(
        id=21,
        status="pending",
        priority="high",
        suggestion_type="low_stock",
        material_id=1,
        material_code="M-001",
        material_name="物料一",
        warehouse_id=2,
        warehouse_name="原料仓",
        current_quantity=Decimal("5"),
        suggested_quantity=Decimal("100"),
        suggested_order_date=date(2026, 1, 15),
        supplier_name="供应商乙",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _slow_row(**kw):
    base = dict(
        batch_no="B-2025-01",
        material_code="MAT-001",
        material_name="物料一",
        quantity=50.0,
        last_move_date="2025-10-01",
        age_days=120,
        warehouse_name="",
    )
    base.update(kw)
    return base


def _scope_patch(visible):
    return patch(
        "apps.kuaiai.services.scene_tools._scoped_row_ids",
        new=AsyncMock(return_value=set(visible)),
    )


class TestQueryInventoryAlerts:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await ia.query_inventory_alerts(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_enums(self):
        out = await ia.query_inventory_alerts(alert_type="bad", ctx=_ctx())
        assert "alert_type" in out and "low_stock" in out
        out = await ia.query_inventory_alerts(status="bad", ctx=_ctx())
        assert "status" in out and "pending" in out
        out = await ia.query_inventory_alerts(alert_level="bad", ctx=_ctx())
        assert "alert_level" in out and "critical" in out

    @pytest.mark.asyncio
    async def test_rows_scoped_and_summarized(self):
        svc = SimpleNamespace(
            get_alerts=AsyncMock(
                return_value=([_alert_row(id=11), _alert_row(id=12)], 2)
            )
        )
        with patch(
            "apps.kuaizhizao.services.inventory_alert_service"
            ".InventoryAlertService",
            return_value=svc,
        ), _scope_patch({11}) as m_scope:
            out = await ia.query_inventory_alerts(ctx=_ctx())
        kw = svc.get_alerts.await_args.kwargs
        assert svc.get_alerts.await_args.args[0] == TENANT
        assert kw["limit"] <= 100  # 过采样上限
        assert m_scope.await_args.args[2] == "kuaizhizao:inventory"
        assert m_scope.await_args.args[3] == {11, 12}
        assert "共 1 条" in out
        assert "M-001" in out and "原料仓" in out
        assert "low_stock" in out and "warning" in out
        assert "5" in out and "10" in out and "pending" in out
        # id=12 不可见，不出现第二条（两条行文本字段相同，用计数判断）
        assert out.count("id=11") == 1 and "id=12" not in out

    @pytest.mark.asyncio
    async def test_all_out_of_scope_truthful_copy(self):
        svc = SimpleNamespace(
            get_alerts=AsyncMock(return_value=([_alert_row(id=11)], 1))
        )
        with patch(
            "apps.kuaizhizao.services.inventory_alert_service"
            ".InventoryAlertService",
            return_value=svc,
        ), _scope_patch(set()):
            out = await ia.query_inventory_alerts(ctx=_ctx())
        assert "数据范围内" in out and "未查询到" in out

    @pytest.mark.asyncio
    async def test_empty_result(self):
        svc = SimpleNamespace(get_alerts=AsyncMock(return_value=([], 0)))
        with patch(
            "apps.kuaizhizao.services.inventory_alert_service"
            ".InventoryAlertService",
            return_value=svc,
        ):
            out = await ia.query_inventory_alerts(ctx=_ctx())
        assert "未查询到" in out

    @pytest.mark.asyncio
    async def test_filters_passed_through(self):
        svc = SimpleNamespace(get_alerts=AsyncMock(return_value=([], 0)))
        with patch(
            "apps.kuaizhizao.services.inventory_alert_service"
            ".InventoryAlertService",
            return_value=svc,
        ):
            await ia.query_inventory_alerts(
                alert_type="expired",
                status="processing",
                alert_level="critical",
                material_id=3,
                warehouse_id=4,
                keyword="过期",
                ctx=_ctx(),
            )
        kw = svc.get_alerts.await_args.kwargs
        assert kw["alert_type"] == "expired"
        assert kw["status"] == "processing"
        assert kw["alert_level"] == "critical"
        assert kw["material_id"] == 3
        assert kw["warehouse_id"] == 4
        assert kw["keyword"] == "过期"

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = SimpleNamespace(
            get_alerts=AsyncMock(side_effect=RuntimeError("db down"))
        )
        with patch(
            "apps.kuaizhizao.services.inventory_alert_service"
            ".InventoryAlertService",
            return_value=svc,
        ):
            out = await ia.query_inventory_alerts(ctx=_ctx())
        assert out == "查询库存预警失败，请稍后重试"
        assert "db down" not in out


class TestQueryReplenishmentSuggestions:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await ia.query_replenishment_suggestions(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_enums(self):
        out = await ia.query_replenishment_suggestions(status="bad", ctx=_ctx())
        assert "status" in out and "processed" in out
        out = await ia.query_replenishment_suggestions(
            priority="bad", ctx=_ctx()
        )
        assert "priority" in out and "high" in out
        out = await ia.query_replenishment_suggestions(
            suggestion_type="bad", ctx=_ctx()
        )
        assert "suggestion_type" in out and "seasonal" in out

    @pytest.mark.asyncio
    async def test_rows_scoped_and_summarized(self):
        svc = SimpleNamespace(
            get_suggestions=AsyncMock(
                return_value=([_suggestion_row(id=21), _suggestion_row(id=22)], 2)
            )
        )
        with patch(
            "apps.kuaizhizao.services.replenishment_suggestion_service"
            ".ReplenishmentSuggestionService",
            return_value=svc,
        ), _scope_patch({21}) as m_scope:
            out = await ia.query_replenishment_suggestions(ctx=_ctx())
        assert m_scope.await_args.args[2] == "kuaizhizao:inventory"
        assert "共 1 条" in out
        assert "M-001" in out and "原料仓" in out
        assert "100" in out and "2026-01-15" in out
        assert "high" in out and "low_stock" in out and "pending" in out
        # 供应商名允许出现；金额类字段不输出
        assert "金额" not in out and "单价" not in out
        assert "id=21" in out and "id=22" not in out

    @pytest.mark.asyncio
    async def test_empty_result(self):
        svc = SimpleNamespace(
            get_suggestions=AsyncMock(return_value=([], 0))
        )
        with patch(
            "apps.kuaizhizao.services.replenishment_suggestion_service"
            ".ReplenishmentSuggestionService",
            return_value=svc,
        ):
            out = await ia.query_replenishment_suggestions(ctx=_ctx())
        assert "未查询到" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = SimpleNamespace(
            get_suggestions=AsyncMock(side_effect=RuntimeError("x"))
        )
        with patch(
            "apps.kuaizhizao.services.replenishment_suggestion_service"
            ".ReplenishmentSuggestionService",
            return_value=svc,
        ):
            out = await ia.query_replenishment_suggestions(ctx=_ctx())
        assert out == "查询补货建议失败，请稍后重试"


class TestQuerySlowMovingInventory:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await ia.query_slow_moving_inventory(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_rows_scoped_by_batch_pair(self):
        svc = SimpleNamespace(
            get_inventory_report=AsyncMock(
                return_value={
                    "data": [
                        _slow_row(batch_no="B-1", material_code="MAT-001"),
                        _slow_row(batch_no="B-2", material_code="MAT-002"),
                    ],
                    "success": True,
                    "summary": {"stale_days": 90, "material_count": 2},
                }
            )
        )
        visible = ({(1, "B-1"): "原料仓"}, {"MAT-001": 1, "MAT-002": 2})
        with patch(
            "apps.kuaizhizao.services.report_service.ReportService",
            return_value=svc,
        ), patch.object(
            ia, "_slow_moving_visible", new=AsyncMock(return_value=visible)
        ) as m_vis:
            out = await ia.query_slow_moving_inventory(ctx=_ctx())
        assert svc.get_inventory_report.await_args.args[0] == TENANT
        assert svc.get_inventory_report.await_args.args[1] == "slow_moving"
        assert "共 1 条" in out
        assert "MAT-001" in out and "MAT-002" not in out
        assert "B-1" in out and "B-2" not in out
        assert "原料仓" in out and "120 天" in out
        # 无金额字段
        assert "金额" not in out and "单价" not in out

    @pytest.mark.asyncio
    async def test_warehouse_filter_forwarded_to_scope_query(self):
        svc = SimpleNamespace(
            get_inventory_report=AsyncMock(
                return_value={"data": [_slow_row()], "success": True}
            )
        )
        visible = ({(1, "B-2025-01"): "原料仓"}, {"MAT-001": 1})
        with patch(
            "apps.kuaizhizao.services.report_service.ReportService",
            return_value=svc,
        ), patch.object(
            ia, "_slow_moving_visible", new=AsyncMock(return_value=visible)
        ) as m_vis:
            out = await ia.query_slow_moving_inventory(
                warehouse_id=9, ctx=_ctx()
            )
        # build_slow_moving_inventory 的 warehouse_id 参数在服务内未生效；
        # Tool 仓库过滤经可见批次查询生效
        assert m_vis.await_args.args[2] == 9
        assert "原料仓" in out

    @pytest.mark.asyncio
    async def test_empty_result(self):
        svc = SimpleNamespace(
            get_inventory_report=AsyncMock(
                return_value={"data": [], "success": True}
            )
        )
        with patch(
            "apps.kuaizhizao.services.report_service.ReportService",
            return_value=svc,
        ):
            out = await ia.query_slow_moving_inventory(ctx=_ctx())
        assert "未查询到" in out

    @pytest.mark.asyncio
    async def test_all_out_of_scope_truthful_copy(self):
        svc = SimpleNamespace(
            get_inventory_report=AsyncMock(
                return_value={"data": [_slow_row()], "success": True}
            )
        )
        with patch(
            "apps.kuaizhizao.services.report_service.ReportService",
            return_value=svc,
        ), patch.object(
            ia,
            "_slow_moving_visible",
            new=AsyncMock(return_value=({}, {})),
        ):
            out = await ia.query_slow_moving_inventory(ctx=_ctx())
        assert "数据范围内" in out and "未查询到" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = SimpleNamespace(
            get_inventory_report=AsyncMock(side_effect=RuntimeError("x"))
        )
        with patch(
            "apps.kuaizhizao.services.report_service.ReportService",
            return_value=svc,
        ):
            out = await ia.query_slow_moving_inventory(ctx=_ctx())
        assert out == "查询呆滞料失败，请稍后重试"

    @pytest.mark.asyncio
    async def test_limit_clamped_to_20(self):
        rows = [_slow_row(batch_no=f"B-{i}") for i in range(25)]
        svc = SimpleNamespace(
            get_inventory_report=AsyncMock(
                return_value={"data": rows, "success": True}
            )
        )
        visible = ({(1, r["batch_no"]): "仓" for r in rows}, {"MAT-001": 1})
        with patch(
            "apps.kuaizhizao.services.report_service.ReportService",
            return_value=svc,
        ), patch.object(
            ia, "_slow_moving_visible", new=AsyncMock(return_value=visible)
        ):
            out = await ia.query_slow_moving_inventory(limit=99, ctx=_ctx())
        assert "返回前 20 条" in out
