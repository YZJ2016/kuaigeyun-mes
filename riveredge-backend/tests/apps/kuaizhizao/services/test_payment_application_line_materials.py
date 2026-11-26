"""付款申请行：采购订单预付款按行金额权重分摊到各明细行。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaizhizao.services.payment_application_line_materials import (
    lines_from_purchase_order_items,
)


@pytest.mark.asyncio
async def test_prepayment_from_po_allocates_to_item_lines():
    order = SimpleNamespace(id=99, order_code="CG202611050005")
    with patch(
        "apps.kuaizhizao.models.purchase_order.PurchaseOrderItem.filter",
    ) as mock_filter:
        mock_filter.return_value.order_by.return_value.all = AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=1,
                    material_name="物料A",
                    material_spec="S1",
                    ordered_quantity=100,
                    unit="件",
                    total_price=Decimal("5000"),
                ),
                SimpleNamespace(
                    id=2,
                    material_name="物料B",
                    material_spec="S2",
                    ordered_quantity=100,
                    unit="件",
                    total_price=Decimal("5000"),
                ),
            ]
        )
        lines = await lines_from_purchase_order_items(
            tenant_id=1,
            order=order,
            request_amount=Decimal("10000"),
            line_kind="prepayment",
        )

    assert len(lines) == 2
    for line, item_id in zip(lines, (1, 2)):
        assert line.source_id == 99
        assert line.source_code == "CG202611050005"
        assert line.request_amount == Decimal("5000")
        assert line.source_line_id == item_id
