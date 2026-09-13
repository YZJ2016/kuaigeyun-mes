"""采购退货确认须保留业务结算单价。"""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from apps.kuaicaiwu.services.inventory_cost_service import InventoryCostService


def test_on_purchase_return_confirmed_does_not_overwrite_business_unit_price():
    item = SimpleNamespace(
        return_quantity=Decimal("20"),
        material_id=1,
        unit_price=Decimal("10"),
        total_amount=Decimal("200"),
        save=AsyncMock(),
    )

    async def run():
        with patch(
            "apps.kuaizhizao.models.purchase_return_item.PurchaseReturnItem.filter"
        ) as item_filter:
            q = AsyncMock()
            q.all = AsyncMock(return_value=[item])
            item_filter.return_value = q
            with patch.object(
                InventoryCostService,
                "get_material_unit_cost_or_zero",
                AsyncMock(return_value=Decimal("8.6957")),
            ):
                await InventoryCostService().on_purchase_return_confirmed(1, 99)

    asyncio.run(run())
    assert item.unit_price == Decimal("10")
    assert item.total_amount == Decimal("200")
    item.save.assert_not_called()
