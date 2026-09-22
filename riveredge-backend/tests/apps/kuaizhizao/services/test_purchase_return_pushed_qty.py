"""采购退货下推已下推数量统计。"""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from apps.kuaizhizao.utils.purchase_return_qty import returned_qty_by_purchase_order_item_ids


def test_returned_qty_falls_back_to_order_and_material():
    po_item = SimpleNamespace(id=10, order_id=100, material_id=501)
    return_header = SimpleNamespace(
        id=900,
        purchase_order_id=100,
        status="待退货",
        deleted_at=None,
    )
    return_line = SimpleNamespace(
        return_id=900,
        purchase_order_item_id=None,
        purchase_receipt_item_id=None,
        material_id=501,
        return_quantity=Decimal("40"),
    )

    async def run():
        with patch(
            "apps.kuaizhizao.models.purchase_order.PurchaseOrderItem.filter"
        ) as po_filter, patch(
            "apps.kuaizhizao.models.purchase_return.PurchaseReturn.filter"
        ) as return_filter, patch(
            "apps.kuaizhizao.models.purchase_return_item.PurchaseReturnItem.filter"
        ) as item_filter:
            po_q = MagicMock()
            po_q.all = AsyncMock(return_value=[po_item])
            po_filter.return_value = po_q
            ret_q = MagicMock()
            ret_q.all = AsyncMock(return_value=[return_header])
            return_filter.return_value = ret_q
            item_q = MagicMock()
            item_q.all = AsyncMock(return_value=[return_line])
            item_filter.return_value = item_q
            return await returned_qty_by_purchase_order_item_ids(1, [10])

    assert asyncio.run(run()) == {10: 40.0}
