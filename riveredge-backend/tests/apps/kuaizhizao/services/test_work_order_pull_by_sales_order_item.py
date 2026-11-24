"""销售订单明细行工单占用 FIFO 分摊单测。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaizhizao.services.sales_order_purchase_push import (
    batch_pushed_work_order_qty_by_sales_order_item,
)


@pytest.mark.asyncio
async def test_wo_qty_fifo_across_same_material_lines():
    """同料两行、一笔合并工单 6：按行 id 顺序 4+2 分摊，已转单不整单堆到首行。"""
    order_id = 1
    line_a = SimpleNamespace(id=10, material_id=100, order_quantity=Decimal("4"))
    line_b = SimpleNamespace(id=20, material_id=100, order_quantity=Decimal("6"))
    items_by_order = {order_id: [line_b, line_a]}

    async def fake_values_list(*args, **kwargs):
        return [(order_id, None, 100, Decimal("6"))]

    chain = SimpleNamespace(values_list=AsyncMock(side_effect=fake_values_list))
    with patch(
        "apps.kuaizhizao.models.work_order.WorkOrder.filter",
        return_value=SimpleNamespace(exclude=lambda *a, **k: chain),
    ):
        out = await batch_pushed_work_order_qty_by_sales_order_item(9, items_by_order)

    assert out[10] == Decimal("4")
    assert out[20] == Decimal("2")