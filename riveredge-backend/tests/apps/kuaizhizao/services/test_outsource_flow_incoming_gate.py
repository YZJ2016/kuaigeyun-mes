"""工序委外：可执行量受上道转入约束。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


def _noop_transaction():
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=None)
    return tx

import pytest

from apps.kuaizhizao.services.outsource_service import OutsourceService
from infra.exceptions.exceptions import BusinessLogicError


@pytest.mark.asyncio
async def test_outsourceable_capped_by_incoming_when_gate_on():
    svc = OutsourceService()
    work_order = SimpleNamespace(id=1, quantity=Decimal("100"))
    op = SimpleNamespace(id=2, completed_quantity=Decimal("0"), qualified_quantity=Decimal("0"))

    with patch.object(
        svc,
        "_resolve_operation_flow_caps",
        new=AsyncMock(
            return_value={
                "max_quantity": Decimal("100"),
                "completed_quantity": Decimal("0"),
                "incoming_quantity": Decimal("40"),
                "material_remaining": Decimal("40"),
                "plan_remaining": Decimal("100"),
            }
        ),
    ):
        with patch(
            "apps.kuaizhizao.services.outsource_service.OutsourceOrder.filter",
        ) as filter_mock:
            filter_mock.return_value.exclude.return_value.all = AsyncMock(return_value=[])
            gated = await svc._compute_outsourceable_breakdown(
                1, work_order, op, apply_incoming_gate=True
            )
            ungated = await svc._compute_outsourceable_breakdown(
                1, work_order, op, apply_incoming_gate=False
            )
    assert gated["outsourceable_quantity"] == Decimal("40")
    assert ungated["outsourceable_quantity"] == Decimal("100")


@pytest.mark.asyncio
async def test_release_blocked_when_exceeds_incoming():
    svc = OutsourceService()
    row = SimpleNamespace(
        id=9,
        status="draft",
        work_order_id=1,
        work_order_operation_id=2,
        outsource_quantity=Decimal("80"),
        updated_by=None,
        updated_by_name=None,
    )
    work_order = SimpleNamespace(id=1, quantity=Decimal("100"))
    op = SimpleNamespace(id=2)

    with patch(
        "apps.kuaizhizao.services.outsource_service.in_transaction",
        return_value=_noop_transaction(),
    ), patch.object(svc, "_get_outsource_order_row", new=AsyncMock(return_value=row)):
        with patch(
            "apps.kuaizhizao.services.outsource_service.WorkOrder.filter"
        ) as wo_filter:
            wo_filter.return_value.first = AsyncMock(return_value=work_order)
            with patch(
                "apps.kuaizhizao.services.outsource_service.WorkOrderOperation.filter"
            ) as op_filter:
                op_filter.return_value.first = AsyncMock(return_value=op)
                with patch.object(
                    svc,
                    "_compute_outsourceable_breakdown",
                    new=AsyncMock(
                        return_value={
                            "outsourceable_quantity": Decimal("40"),
                            "incoming_quantity": Decimal("40"),
                        }
                    ),
                ):
                    with pytest.raises(BusinessLogicError, match="工序流转门禁"):
                        await svc.release_outsource_order(
                            tenant_id=1, outsource_order_id=9, updated_by=1
                        )


def test_open_outsource_reserved_qty_nets_received():
    svc = OutsourceService()
    orders = [
        SimpleNamespace(outsource_quantity=Decimal("50"), received_quantity=Decimal("20")),
        SimpleNamespace(outsource_quantity=Decimal("10"), received_quantity=Decimal("10")),
    ]
    assert svc._open_outsource_reserved_qty(orders) == Decimal("30")
