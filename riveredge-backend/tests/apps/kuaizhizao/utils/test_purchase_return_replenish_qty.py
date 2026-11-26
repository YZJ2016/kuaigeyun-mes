"""补货退货不参与扣减采购订单已到货，但计入可再次入库量。"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaizhizao.utils.purchase_return_qty import (
    confirmed_returned_qty_by_purchase_order_item_ids,
    replenish_return_qty_by_purchase_order_item_ids,
)


@pytest.mark.asyncio
async def test_confirmed_qty_excludes_replenish_header():
    header = MagicMock()
    header.id = 1
    header.status = "已退货"
    header.purchase_order_id = 99
    header.replenish = True

    with patch(
        "apps.kuaizhizao.utils.purchase_return_qty._purchase_return_qty_by_po_item_ids",
        new=AsyncMock(return_value={10: Decimal("0")}),
    ) as mocked:
        await confirmed_returned_qty_by_purchase_order_item_ids(1, [10])
        mocked.assert_awaited_once()
        assert mocked.await_args.kwargs["replenish_filter"] == "exclude_replenish"
        assert mocked.await_args.kwargs["confirmed_only"] is True


@pytest.mark.asyncio
async def test_replenish_qty_includes_pending():
    with patch(
        "apps.kuaizhizao.utils.purchase_return_qty._purchase_return_qty_by_po_item_ids",
        new=AsyncMock(return_value={10: Decimal("5")}),
    ) as mocked:
        result = await replenish_return_qty_by_purchase_order_item_ids(1, [10])
        assert result[10] == Decimal("5")
        assert mocked.await_args.kwargs["replenish_filter"] == "replenish_only"
        assert mocked.await_args.kwargs["confirmed_only"] is False
