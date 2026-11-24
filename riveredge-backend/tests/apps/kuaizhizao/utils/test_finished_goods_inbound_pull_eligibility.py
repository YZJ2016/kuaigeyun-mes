"""成品入库从工单取单门禁单测。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaizhizao.utils.finished_goods_inbound_pull_eligibility import (
    REASON_OPERATION_NOT_REPORTED,
    REASON_PICK_INCOMPLETE,
    evaluate_fg_pull_readiness,
)


def _wo(wo_id: int = 1):
    return SimpleNamespace(
        id=wo_id,
        product_id=100,
        quantity=10,
        variant_attributes=None,
        configurable_selections=None,
    )


def _op(op_id: int = 1, operation_id: int = 10, completed: float = 0):
    return SimpleNamespace(
        id=op_id,
        work_order_id=1,
        operation_id=operation_id,
        completed_quantity=completed,
        deleted_at=None,
    )


def _req(mid: int, gross: float, *, issue_method=None, component_type=None):
    return SimpleNamespace(
        component_id=mid,
        gross_requirement=gross,
        net_requirement=gross,
        issue_method=issue_method,
        component_type=component_type,
    )


@pytest.mark.asyncio
async def test_legacy_eligible_without_bom_and_operations():
    with patch(
        "apps.kuaizhizao.utils.finished_goods_inbound_pull_eligibility._load_material_requirements",
        new=AsyncMock(return_value=[]),
    ):
        result = await evaluate_fg_pull_readiness(1, _wo(), operations=[])
    assert result.eligible is True
    assert result.has_pick_bom is False
    assert result.has_operations is False


@pytest.mark.asyncio
async def test_pick_bom_incomplete_blocks():
    pick_req = _req(201, 5.0, issue_method="pick")
    with (
        patch(
            "apps.kuaizhizao.utils.finished_goods_inbound_pull_eligibility._load_material_requirements",
            new=AsyncMock(return_value=[pick_req]),
        ),
        patch(
            "apps.kuaizhizao.utils.finished_goods_inbound_pull_eligibility.sum_confirmed_picked_by_material",
            new=AsyncMock(return_value={201: Decimal("2")}),
        ),
    ):
        result = await evaluate_fg_pull_readiness(1, _wo(), operations=[])
    assert result.eligible is False
    assert result.reason_code == REASON_PICK_INCOMPLETE


@pytest.mark.asyncio
async def test_bom_and_operations_require_pick_and_all_ops_reported():
    pick_req = _req(201, 5.0, issue_method="pick")
    ops = [_op(1, 10, 0), _op(2, 20, 0)]
    with (
        patch(
            "apps.kuaizhizao.utils.finished_goods_inbound_pull_eligibility._load_material_requirements",
            new=AsyncMock(return_value=[pick_req]),
        ),
        patch(
            "apps.kuaizhizao.utils.finished_goods_inbound_pull_eligibility.sum_confirmed_picked_by_material",
            new=AsyncMock(return_value={201: Decimal("5")}),
        ),
        patch.object(
            __import__(
                "apps.kuaizhizao.services.work_order_service", fromlist=["WorkOrderService"]
            ).WorkOrderService,
            "_work_order_operation_has_reporting_qty",
            new=AsyncMock(side_effect=[True, False]),
        ),
    ):
        result = await evaluate_fg_pull_readiness(1, _wo(), operations=ops)
    assert result.eligible is False
    assert result.reason_code == REASON_OPERATION_NOT_REPORTED


@pytest.mark.asyncio
async def test_operations_only_all_reported_eligible():
    ops = [_op(1, 10, 1.0)]
    with (
        patch(
            "apps.kuaizhizao.utils.finished_goods_inbound_pull_eligibility._load_material_requirements",
            new=AsyncMock(return_value=[]),
        ),
        patch.object(
            __import__(
                "apps.kuaizhizao.services.work_order_service", fromlist=["WorkOrderService"]
            ).WorkOrderService,
            "_work_order_operation_has_reporting_qty",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await evaluate_fg_pull_readiness(1, _wo(), operations=ops)
    assert result.eligible is True
    assert result.has_operations is True
    assert result.has_pick_bom is False