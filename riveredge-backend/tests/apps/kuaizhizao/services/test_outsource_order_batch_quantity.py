"""工序委外：默认套数与已发料套数。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaizhizao.services.outsource_order_batch_quantity import (
    compute_issued_batch_quantity,
    resolve_outsource_default_basis_quantity,
    resolve_outsource_suggested_issue_batch_quantity,
    resolve_outsource_suggested_receipt_quantity,
)


@pytest.mark.asyncio
async def test_default_basis_when_jump_allowed():
    wo = SimpleNamespace(id=1, quantity=Decimal("100"), allow_operation_jump=True)
    op = SimpleNamespace(id=2)
    ops = [SimpleNamespace(id=1), op]
    basis = await resolve_outsource_default_basis_quantity(1, wo, op, ordered_operations=ops)
    assert basis == Decimal("100")


@pytest.mark.asyncio
async def test_default_basis_adjacent_prev_when_no_jump():
    wo = SimpleNamespace(id=1, quantity=Decimal("100"), allow_operation_jump=False)
    op = SimpleNamespace(id=2)
    ops = [SimpleNamespace(id=1), op]
    with patch(
        "apps.kuaizhizao.services.outsource_order_batch_quantity.resolve_operation_transfer_qualified",
        new=AsyncMock(return_value=Decimal("42")),
    ):
        basis = await resolve_outsource_default_basis_quantity(1, wo, op, ordered_operations=ops)
    assert basis == Decimal("42")


@pytest.mark.asyncio
async def test_suggested_receipt_min_remain_and_basis():
    oo = SimpleNamespace(
        id=9,
        work_order_id=1,
        work_order_operation_id=2,
        outsource_quantity=Decimal("80"),
        received_quantity=Decimal("10"),
    )
    wo = SimpleNamespace(id=1, quantity=Decimal("100"), allow_operation_jump=False)
    op = SimpleNamespace(id=2)
    with patch(
        "apps.kuaizhizao.services.outsource_order_batch_quantity.resolve_outsource_default_basis_quantity",
        new=AsyncMock(return_value=Decimal("50")),
    ):
        qty = await resolve_outsource_suggested_receipt_quantity(
            1, oo, work_order=wo, work_order_operation=op
        )
    assert qty == Decimal("50")


@pytest.mark.asyncio
async def test_issued_batch_bottleneck():
    oo = SimpleNamespace(
        id=1,
        work_order_id=1,
        outsource_quantity=Decimal("10"),
    )
    wo = SimpleNamespace(id=1, product_id=99)
    bom = [(1, Decimal("2")), (2, Decimal("4"))]
    issued = {1: Decimal("10"), 2: Decimal("8")}
    batch = await compute_issued_batch_quantity(
        1, oo, work_order=wo, issued_map=issued, bom_per_unit=bom
    )
    assert batch == Decimal("2")


@pytest.mark.asyncio
async def test_suggested_issue_batch_capped_by_pending():
    oo = SimpleNamespace(
        id=1,
        work_order_id=1,
        work_order_operation_id=2,
        outsource_quantity=Decimal("10"),
    )
    wo = SimpleNamespace(id=1, quantity=Decimal("100"), allow_operation_jump=True)
    op = SimpleNamespace(id=2)
    with patch(
        "apps.kuaizhizao.services.outsource_order_batch_quantity.resolve_outsource_default_basis_quantity",
        new=AsyncMock(return_value=Decimal("100")),
    ):
        qty = await resolve_outsource_suggested_issue_batch_quantity(
            1,
            oo,
            work_order=wo,
            work_order_operation=op,
            issued_batch=Decimal("6"),
        )
    assert qty == Decimal("4")