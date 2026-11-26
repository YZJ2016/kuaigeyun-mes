"""按采购入库行汇总退货占用量。"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaizhizao.utils.purchase_return_qty import returned_qty_by_purchase_receipt_item_ids


@pytest.mark.asyncio
async def test_empty_ids_returns_empty():
    assert await returned_qty_by_purchase_receipt_item_ids(1, []) == {}


@pytest.mark.asyncio
async def test_sums_active_returns_excludes_void():
    ri_active = MagicMock()
    ri_active.return_id = 10
    ri_active.purchase_receipt_item_id = 100
    ri_active.return_quantity = Decimal("3")

    ri_void = MagicMock()
    ri_void.return_id = 11
    ri_void.purchase_receipt_item_id = 100
    ri_void.return_quantity = Decimal("5")

    header_active = MagicMock()
    header_active.id = 10
    header_active.status = "待退货"

    header_void = MagicMock()
    header_void.id = 11
    header_void.status = "已取消"

    item_filter = MagicMock()
    item_filter.all = AsyncMock(return_value=[ri_active, ri_void])

    return_filter = MagicMock()
    return_filter.all = AsyncMock(return_value=[header_active, header_void])

    with patch(
        "apps.kuaizhizao.models.purchase_return_item.PurchaseReturnItem.filter",
        return_value=item_filter,
    ), patch(
        "apps.kuaizhizao.models.purchase_return.PurchaseReturn.filter",
        return_value=return_filter,
    ):
        result = await returned_qty_by_purchase_receipt_item_ids(1, [100])

    assert result[100] == 3.0
