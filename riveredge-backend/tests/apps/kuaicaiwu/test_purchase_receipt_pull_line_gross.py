"""采购入库取单明细：可开票/本次开票须为价税合计，与表头一致。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
    build_purchase_receipt_finance_detail_lines,
)


class _AwaitableList:
    def __init__(self, rows):
        self._rows = rows

    def __await__(self):
        async def _get():
            return self._rows

        return _get().__await__()


@pytest.mark.asyncio
async def test_receipt_detail_lines_max_push_is_line_gross():
    receipt = SimpleNamespace(id=1, tax_rate=Decimal("13"))
    item = SimpleNamespace(
        id=10,
        material_code="M1",
        material_name="刀",
        material_spec=None,
        material_unit="EA",
        receipt_quantity=Decimal("10"),
        unit_price=Decimal("176.99"),
        total_amount=Decimal("1769.91"),
        purchase_order_item_id=99,
    )
    poi = SimpleNamespace(id=99, ordered_quantity=Decimal("10"), total_price=Decimal("1769.91"))

    with patch(
        "apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines._purchase_receipt_line_gross_by_item_id",
        new=AsyncMock(
            return_value=(
                receipt,
                [item],
                {10: Decimal("1769.91")},
                {10: Decimal("2000.00")},
            )
        ),
    ), patch(
        "apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines.PurchaseReceiptLineFinanceOccupancyService"
    ) as mock_svc_cls, patch(
        "apps.kuaizhizao.models.purchase_order.PurchaseOrderItem.filter",
        return_value=_AwaitableList([poi]),
    ):
        mock_svc_cls.return_value._sum_occupied_by_item = AsyncMock(return_value={})

        lines = await build_purchase_receipt_finance_detail_lines(1, 1, "invoice")

    assert len(lines) == 1
    row = lines[0]
    assert row["amount"] == pytest.approx(1769.91)
    assert row["tax_amount"] == pytest.approx(230.09, abs=0.02)
    assert row["max_push_amount"] == pytest.approx(2000.0)
    assert row["max_push_quantity"] == pytest.approx(10.0)
