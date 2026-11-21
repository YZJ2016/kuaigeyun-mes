"""工序委外状态流转与登记收货。"""

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
async def test_complete_outsource_order_requires_full_receipt():
    svc = OutsourceService()
    row = SimpleNamespace(
        tenant_id=1,
        id=9,
        status="in_progress",
        outsource_quantity=Decimal("10"),
        received_quantity=Decimal("5"),
        actual_end_date=None,
    )

    with patch(
        "apps.kuaizhizao.services.outsource_service.in_transaction",
        return_value=_noop_transaction(),
    ), patch.object(svc, "_get_outsource_order_row", new=AsyncMock(return_value=row)):
        with pytest.raises(BusinessLogicError, match="未达到委外数量"):
            await svc.complete_outsource_order(tenant_id=1, outsource_order_id=9, updated_by=1)


def test_can_revoke_outsource_order_release():
    svc = OutsourceService()
    ok = SimpleNamespace(
        status="released",
        purchase_receipt_id=None,
        received_quantity=Decimal("0"),
        actual_start_date=None,
    )
    assert svc.can_revoke_outsource_order_release(ok) is True
    blocked = SimpleNamespace(
        status="released",
        purchase_receipt_id=1,
        received_quantity=Decimal("0"),
        actual_start_date=None,
    )
    assert svc.can_revoke_outsource_order_release(blocked) is False


@pytest.mark.asyncio
async def test_start_outsource_order_requires_process_issue():
    svc = OutsourceService()
    with pytest.raises(BusinessLogicError, match="工序发料"):
        await svc.start_outsource_order(tenant_id=1, outsource_order_id=1, updated_by=1)


def test_validate_outsource_receipt_quantities_sum():
    svc = OutsourceService()
    with pytest.raises(BusinessLogicError):
        svc._validate_outsource_receipt_quantities(
            outsource_quantity=Decimal("10"),
            received_quantity=Decimal("5"),
            qualified_quantity=Decimal("3"),
            unqualified_quantity=Decimal("1"),
        )
