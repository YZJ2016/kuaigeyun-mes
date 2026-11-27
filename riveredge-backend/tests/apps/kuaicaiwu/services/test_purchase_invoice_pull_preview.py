"""采购发票统一取单预览分发。"""

from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaicaiwu.services.purchase_invoice_pull_service import PurchaseInvoicePullService


@pytest.mark.asyncio
async def test_preview_pull_dispatches_purchase_order_single():
    svc = PurchaseInvoicePullService()
    preview = {"items": [{"max_push_quantity": 100}], "source_type": "purchase_order"}
    with patch.object(
        svc,
        "preview_pull_from_purchase_order",
        new=AsyncMock(return_value=preview),
    ) as single:
        out = await svc.preview_pull(
            1, source_type="purchase_order", source_ids=[9]
        )
    assert out is preview
    single.assert_awaited_once_with(1, 9)


@pytest.mark.asyncio
async def test_preview_pull_dispatches_purchase_order_multi():
    svc = PurchaseInvoicePullService()
    preview = {"items": [{}]}
    with patch.object(
        svc,
        "preview_pull_from_purchase_orders",
        new=AsyncMock(return_value=preview),
    ) as multi:
        out = await svc.preview_pull(
            1, source_type="purchase_order", source_ids=[9, 10]
        )
    assert out is preview
    multi.assert_awaited_once_with(1, [9, 10])


@pytest.mark.asyncio
async def test_preview_pull_rejects_empty_ids():
    svc = PurchaseInvoicePullService()
    with pytest.raises(Exception):
        await svc.preview_pull(1, source_type="payable", source_ids=[])