from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
    build_slices_from_pull_receipt_line_selections,
)
from infra.exceptions.exceptions import ValidationError


@pytest.mark.asyncio
async def test_build_slices_rejects_sum_mismatch():
    with patch(
        "apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines.build_purchase_receipt_finance_detail_lines",
        new=AsyncMock(
            return_value=[
                {
                    "purchase_receipt_item_id": 10,
                    "max_push_amount": 100.0,
                }
            ]
        ),
    ), patch(
        "apps.kuaizhizao.models.purchase_receipt_item.PurchaseReceiptItem.filter",
    ) as mock_filter, patch(
        "apps.kuaizhizao.models.purchase_receipt_item.PurchaseReceiptItem.get_or_none",
        new=AsyncMock(
            return_value=type(
                "Item",
                (),
                {"unit_price": Decimal("1"), "receipt_quantity": Decimal("100")},
            )()
        ),
    ):
        mock_filter.return_value.values_list = AsyncMock(return_value=[10])
        with pytest.raises(ValidationError, match="不一致"):
            await build_slices_from_pull_receipt_line_selections(
                1,
                2,
                "payable",
                [{"purchase_receipt_item_id": 10, "amount": Decimal("50")}],
                header_amount=Decimal("100"),
            )
