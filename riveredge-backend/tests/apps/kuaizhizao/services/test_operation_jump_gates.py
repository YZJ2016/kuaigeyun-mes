"""工序跳转关闸：唯一认工单头 allow_operation_jump。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaizhizao.services.operation_jump_rules import (
    find_nearest_jump_gate,
    resolve_material_incoming_qty,
    validate_reporting_respects_jump_gates,
    validate_start_respects_jump_gates,
)
from infra.exceptions.exceptions import BusinessLogicError


def _op(
    seq: int,
    *,
    name: str = "",
    transfer: str = "0",
    status: str = "pending",
    is_node_operation: bool = False,
    allow_jump: bool = False,
):
    return SimpleNamespace(
        id=seq,
        sequence=seq,
        allow_jump=allow_jump,
        is_node_operation=is_node_operation,
        operation_name=name or f"OP{seq}",
        deleted_at=None,
        status=status,
        completed_quantity=Decimal("0"),
        qualified_quantity=Decimal(transfer),
        work_order_id=1,
    )


def _wo(*, allow_operation_jump: bool):
    return SimpleNamespace(id=1, allow_operation_jump=allow_operation_jump, quantity=Decimal("100"))


def test_jump_open_no_gate():
    preds = [_op(i, allow_jump=False) for i in range(1, 9)]
    assert find_nearest_jump_gate(preds, allow_operation_jump=True) is None


def test_jump_open_gate_is_nearest_node_not_row_allow_jump():
    preds = [
        _op(1, allow_jump=False),
        _op(2, name="节点2", is_node_operation=True, allow_jump=True),
        _op(3, allow_jump=False),
        _op(4, name="节点4", is_node_operation=True, allow_jump=True),
    ]
    gate = find_nearest_jump_gate(preds, allow_operation_jump=True)
    assert gate is not None
    assert gate.sequence == 4


def test_jump_closed_uses_adjacent():
    preds = [_op(i) for i in range(1, 5)]
    gate = find_nearest_jump_gate(preds, allow_operation_jump=False)
    assert gate is not None
    assert gate.sequence == 4


@pytest.mark.asyncio
async def test_start_blocked_when_sequential_and_no_transfer():
    current = _op(5)
    gate = _op(4, name="关闸4", transfer="0")
    ordered = [_op(1), _op(2), _op(3), gate, current]
    wo = _wo(allow_operation_jump=False)

    with patch(
        "apps.kuaizhizao.services.operation_jump_rules.qualified_transfer_quantity_async",
        new=AsyncMock(return_value=Decimal("0")),
    ):
        with pytest.raises(BusinessLogicError, match="关闸4"):
            await validate_start_respects_jump_gates(
                1, 1, current, work_order=wo, ordered_operations=ordered
            )


@pytest.mark.asyncio
async def test_start_ok_when_wo_allows_jump():
    current = _op(9)
    ordered = [_op(i, allow_jump=False) for i in range(1, 9)] + [current]
    wo = _wo(allow_operation_jump=True)
    await validate_start_respects_jump_gates(
        1, 1, current, work_order=wo, ordered_operations=ordered
    )


@pytest.mark.asyncio
async def test_start_blocked_when_jump_open_and_previous_node_has_no_output():
    node = _op(2, name="节点2", is_node_operation=True, allow_jump=True)
    current = _op(4)
    ordered = [_op(1), node, _op(3, allow_jump=False), current]
    wo = _wo(allow_operation_jump=True)
    with patch(
        "apps.kuaizhizao.services.operation_jump_rules.qualified_transfer_quantity_async",
        new=AsyncMock(return_value=Decimal("0")),
    ):
        with pytest.raises(BusinessLogicError, match="允许跳转时前序节点仍不可跳过"):
            await validate_start_respects_jump_gates(
                1, 1, current, work_order=wo, ordered_operations=ordered
            )


@pytest.mark.asyncio
async def test_start_ok_when_jump_open_and_previous_node_has_output():
    node = _op(2, name="节点2", is_node_operation=True, transfer="1")
    current = _op(4)
    ordered = [_op(1), node, current]
    wo = _wo(allow_operation_jump=True)
    with patch(
        "apps.kuaizhizao.services.operation_jump_rules.qualified_transfer_quantity_async",
        new=AsyncMock(return_value=Decimal("1")),
    ):
        await validate_start_respects_jump_gates(
            1, 1, current, work_order=wo, ordered_operations=ordered
        )


@pytest.mark.asyncio
async def test_report_capped_when_sequential():
    current = _op(5)
    gate = _op(4, name="关闸4", transfer="30")
    ordered = [_op(1), _op(2), _op(3), gate, current]
    wo = _wo(allow_operation_jump=False)

    with patch(
        "apps.kuaizhizao.services.operation_jump_rules.qualified_transfer_quantity_async",
        new=AsyncMock(return_value=Decimal("30")),
    ):
        with pytest.raises(BusinessLogicError, match="不能超过"):
            await validate_reporting_respects_jump_gates(
                1,
                1,
                current,
                reporting_type="quantity",
                reported_quantity=Decimal("40"),
                work_order=wo,
                ordered_operations=ordered,
            )


@pytest.mark.asyncio
async def test_report_blocked_when_jump_open_and_previous_node_has_no_output():
    node = _op(2, name="节点2", is_node_operation=True)
    later = _op(3, name="节点3", is_node_operation=True, transfer="10")
    current = _op(5)
    ordered = [node, later, current]
    wo = _wo(allow_operation_jump=True)

    async def _transfer(_tenant, _wo, operation, **_kwargs):
        return Decimal(str(operation.qualified_quantity or 0))

    with patch(
        "apps.kuaizhizao.services.operation_jump_rules.qualified_transfer_quantity_async",
        new=AsyncMock(side_effect=_transfer),
    ):
        with pytest.raises(BusinessLogicError, match="节点2"):
            await validate_reporting_respects_jump_gates(
                1,
                1,
                current,
                reporting_type="quantity",
                reported_quantity=Decimal("1"),
                work_order=wo,
                ordered_operations=ordered,
            )


@pytest.mark.asyncio
async def test_report_not_capped_by_node_output_when_jump_open():
    node = _op(2, name="节点2", is_node_operation=True, transfer="1")
    current = _op(4)
    ordered = [_op(1), node, current]
    wo = _wo(allow_operation_jump=True)
    with patch(
        "apps.kuaizhizao.services.operation_jump_rules.qualified_transfer_quantity_async",
        new=AsyncMock(return_value=Decimal("1")),
    ):
        await validate_reporting_respects_jump_gates(
            1,
            1,
            current,
            reporting_type="quantity",
            reported_quantity=Decimal("100"),
            work_order=wo,
            ordered_operations=ordered,
        )


@pytest.mark.asyncio
async def test_report_free_when_wo_allows_jump():
    current = _op(9)
    ordered = [_op(i) for i in range(1, 9)] + [current]
    wo = _wo(allow_operation_jump=True)
    await validate_reporting_respects_jump_gates(
        1,
        1,
        current,
        reporting_type="quantity",
        reported_quantity=Decimal("100"),
        work_order=wo,
        ordered_operations=ordered,
    )


@pytest.mark.asyncio
async def test_incoming_plan_when_wo_allows_jump():
    current = _op(9)
    ordered = [_op(i) for i in range(1, 9)] + [current]
    wo = _wo(allow_operation_jump=True)

    with patch(
        "apps.kuaizhizao.services.over_report_rules.first_operation_material_incoming",
        return_value=Decimal("100"),
    ):
        incoming = await resolve_material_incoming_qty(
            1,
            wo,
            current,
            plan_qty=Decimal("100"),
            adjacent_prev_transfer=Decimal("50"),
            ordered_operations=ordered,
        )
    assert incoming == Decimal("100")


@pytest.mark.asyncio
async def test_incoming_zero_when_jump_open_and_node_has_no_output():
    node = _op(2, name="节点2", is_node_operation=True)
    current = _op(4)
    ordered = [_op(1), node, current]
    wo = _wo(allow_operation_jump=True)
    with patch(
        "apps.kuaizhizao.services.operation_jump_rules.qualified_transfer_quantity_async",
        new=AsyncMock(return_value=Decimal("0")),
    ):
        incoming = await resolve_material_incoming_qty(
            1,
            wo,
            current,
            plan_qty=Decimal("100"),
            adjacent_prev_transfer=Decimal("0"),
            ordered_operations=ordered,
        )
    assert incoming == Decimal("0")


@pytest.mark.asyncio
async def test_incoming_stays_plan_when_jump_open_and_node_has_output():
    node = _op(2, name="节点2", is_node_operation=True, transfer="5")
    current = _op(4)
    ordered = [_op(1), node, current]
    wo = _wo(allow_operation_jump=True)
    with patch(
        "apps.kuaizhizao.services.operation_jump_rules.qualified_transfer_quantity_async",
        new=AsyncMock(return_value=Decimal("5")),
    ), patch(
        "apps.kuaizhizao.services.over_report_rules.first_operation_material_incoming",
        return_value=Decimal("100"),
    ):
        incoming = await resolve_material_incoming_qty(
            1,
            wo,
            current,
            plan_qty=Decimal("100"),
            adjacent_prev_transfer=Decimal("5"),
            ordered_operations=ordered,
        )
    assert incoming == Decimal("100")


@pytest.mark.asyncio
async def test_incoming_adjacent_when_sequential():
    current = _op(6)
    ordered = [_op(i) for i in range(1, 6)] + [current]
    wo = _wo(allow_operation_jump=False)
    incoming = await resolve_material_incoming_qty(
        1,
        wo,
        current,
        plan_qty=Decimal("100"),
        adjacent_prev_transfer=Decimal("25"),
        ordered_operations=ordered,
    )
    assert incoming == Decimal("25")
