"""生产领料空白建单保存时库存校验。"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaizhizao.services.warehouse_service import _assert_production_picking_save_stock_lines
from infra.exceptions.exceptions import BusinessLogicError


@pytest.mark.asyncio
async def test_assert_production_picking_save_stock_rejects_insufficient():
    with patch(
        "apps.kuaizhizao.utils.inventory_helper.assert_outbound_warehouse_stock_available",
        new=AsyncMock(side_effect=BusinessLogicError("库存不足")),
    ):
        with pytest.raises(BusinessLogicError, match="库存不足"):
            await _assert_production_picking_save_stock_lines(
                1,
                [
                    {
                        "material_id": 10,
                        "warehouse_id": 2,
                        "required_quantity": 5,
                        "material_code": "RM001",
                    }
                ],
            )


@pytest.mark.asyncio
async def test_assert_production_picking_save_stock_skips_zero_qty():
    with patch(
        "apps.kuaizhizao.utils.inventory_helper.assert_outbound_warehouse_stock_available",
        new=AsyncMock(),
    ) as mocked:
        await _assert_production_picking_save_stock_lines(
            1,
            [{"material_id": 10, "warehouse_id": 2, "required_quantity": 0}],
        )
        mocked.assert_not_called()