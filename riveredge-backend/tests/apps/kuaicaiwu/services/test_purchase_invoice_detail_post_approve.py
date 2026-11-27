"""明细采购发票审核后：收票结束与价差计算。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaicaiwu.services.purchase_invoice_detail_post_approve import (
    _actual_incl_for_invoice_item,
    _expected_incl_for_invoice_item,
    compute_purchase_invoice_price_diff_incl,
    refresh_outsource_order_receipt_invoice_receipt_complete,
    refresh_purchase_receipt_items_invoice_receipt_complete,
    sum_outsource_batch_invoice_occupied_incl,
)


def test_actual_incl_for_invoice_item():
    row = SimpleNamespace(amount=Decimal("100"), tax_amount=Decimal("13"))
    assert _actual_incl_for_invoice_item(row) == Decimal("113.00")


@pytest.mark.asyncio
async def test_expected_incl_proportional_qty():
    item = SimpleNamespace(receipt_quantity=Decimal("10"))
    with patch(
        "apps.kuaicaiwu.services.purchase_invoice_detail_post_approve._line_settlement_gross_by_item_id",
        new=AsyncMock(return_value={5: Decimal("1000.00")}),
    ), patch(
        "apps.kuaicaiwu.services.purchase_invoice_detail_post_approve.PurchaseReceiptItem.get_or_none",
        new=AsyncMock(return_value=item),
    ):
        got = await _expected_incl_for_invoice_item(1, 9, 5, Decimal("5"))
    assert got == Decimal("500.00")


@pytest.mark.asyncio
async def test_compute_price_diff_sums_receipt_lines():
    items = [
        SimpleNamespace(
            source_doc_type="purchase_receipt",
            source_doc_id=1,
            source_line_id=10,
            quantity=Decimal("1"),
            amount=Decimal("110"),
            tax_amount=Decimal("14.30"),
        ),
    ]
    qs = AsyncMock()
    qs.all = AsyncMock(return_value=items)
    order_qs = AsyncMock()
    order_qs.all = AsyncMock(return_value=items)
    with patch(
        "apps.kuaicaiwu.services.purchase_invoice_detail_post_approve.PurchaseInvoiceItem.filter",
        return_value=order_qs,
    ):
        order_qs.order_by = lambda *_a, **_k: order_qs
        with patch(
            "apps.kuaicaiwu.services.purchase_invoice_detail_post_approve._expected_incl_for_invoice_item",
            new=AsyncMock(return_value=Decimal("100.00")),
        ):
            diff = await compute_purchase_invoice_price_diff_incl(1, 99)
    assert diff == Decimal("24.30")


@pytest.mark.asyncio
async def test_refresh_marks_complete_when_occupied_ge_gross():
    items = [SimpleNamespace(id=10, invoice_receipt_complete=False)]
    list_qs = AsyncMock()
    list_qs.all = AsyncMock(return_value=items)
    update_qs = AsyncMock()
    update_qs.update = AsyncMock()

    def filter_side_effect(**kwargs):
        if "id__in" in kwargs:
            return list_qs
        if "id" in kwargs:
            return update_qs
        return list_qs

    with patch(
        "apps.kuaicaiwu.services.purchase_invoice_detail_post_approve.PurchaseReceiptItem.filter",
        side_effect=filter_side_effect,
    ), patch(
        "apps.kuaicaiwu.services.purchase_invoice_detail_post_approve._line_settlement_gross_by_item_id",
        new=AsyncMock(return_value={10: Decimal("1000.00")}),
    ), patch(
        "apps.kuaicaiwu.services.purchase_invoice_detail_post_approve._sum_invoice_occupied_incl_by_receipt_item",
        new=AsyncMock(return_value={10: Decimal("1000.00")}),
    ):
        marked = await refresh_purchase_receipt_items_invoice_receipt_complete(1, 2, item_ids=[10])
    assert marked == [10]


@pytest.mark.asyncio
async def test_refresh_outsource_batch_complete_when_occupied_ge_gross():
    batch = SimpleNamespace(invoice_receipt_complete=False)
    update_qs = AsyncMock()
    update_qs.update = AsyncMock()

    with patch(
        "apps.kuaizhizao.models.outsource_order_receipt.OutsourceOrderReceipt.get_or_none",
        new=AsyncMock(return_value=batch),
    ), patch(
        "apps.kuaizhizao.models.outsource_order_receipt.OutsourceOrderReceipt.filter",
        return_value=update_qs,
    ), patch(
        "apps.kuaicaiwu.services.purchase_invoice_pull_service.PurchaseInvoicePullService"
    ) as pull_cls, patch(
        "apps.kuaicaiwu.services.purchase_invoice_detail_post_approve.sum_outsource_batch_invoice_occupied_incl",
        new=AsyncMock(return_value=Decimal("1000.00")),
    ):
        pull_cls.return_value.outsource_order_receipt_settlement_gross = AsyncMock(
            return_value=Decimal("1000.00")
        )
        ok = await refresh_outsource_order_receipt_invoice_receipt_complete(1, 88)
    assert ok is True
    update_qs.update.assert_awaited_once_with(invoice_receipt_complete=True)


@pytest.mark.asyncio
async def test_sum_outsource_batch_invoice_occupied_incl():
    rows = [SimpleNamespace(amount=Decimal("50")), SimpleNamespace(amount=Decimal("63"))]
    qs = AsyncMock()
    qs.all = AsyncMock(return_value=rows)
    with patch(
        "apps.kuaicaiwu.services.purchase_invoice_detail_post_approve.PurchaseReceiptLineFinanceOccupancy.filter",
        return_value=qs,
    ):
        total = await sum_outsource_batch_invoice_occupied_incl(1, 88)
    assert total == Decimal("113.00")