"""销售订单直推采购占用统计辅助逻辑单测。"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaizhizao.services.sales_order_purchase_push import (
    _add_po_item_qty,
    _is_purchase_order_doc_type,
    _is_sales_order_source,
    list_purchase_order_sales_order_pull_lines,
    list_purchase_requisition_sales_order_pull_lines,
)
from apps.kuaizhizao.utils.pull_open_line_quantity import build_partial_push_qty_triplet


def test_is_sales_order_source_normalizes():
    assert _is_sales_order_source("sales_order")
    assert _is_sales_order_source("SalesOrder")
    assert _is_sales_order_source("sales-order")
    assert not _is_sales_order_source("demand")


def test_is_purchase_order_doc_type_normalizes():
    assert _is_purchase_order_doc_type("purchase_order")
    assert _is_purchase_order_doc_type("PurchaseOrder")
    assert not _is_purchase_order_doc_type("sales_order")


def test_add_po_item_qty_accumulates_per_material():
    result: dict = {42: {}}
    _add_po_item_qty(result, 42, 7, "6")
    _add_po_item_qty(result, 42, 7, Decimal("2"))
    assert result[42][7] == Decimal("8")


def test_partial_push_line_triplet_keeps_second_pull_visible():
  """分批下推后：已占用 3、订单 6 → 仍可开票 3（开口取单三元组）。"""
  sug, pushed, rem = build_partial_push_qty_triplet(Decimal("6"), Decimal("3"))
  assert sug == 6.0
  assert pushed == 3.0
  assert rem == 3.0


@pytest.mark.asyncio
async def test_po_pull_passes_purchase_order_track():
    with patch(
        "apps.kuaizhizao.services.sales_order_purchase_push.require_purchase_requisition_for_tenant",
        new_callable=AsyncMock,
        return_value=False,
    ):
        with patch(
            "apps.kuaizhizao.services.sales_order_purchase_push._list_sales_order_buy_pull_lines",
            new_callable=AsyncMock,
            return_value={"data": [], "total": 0},
        ) as inner:
            await list_purchase_order_sales_order_pull_lines(1)
            inner.assert_awaited_once()
            assert inner.await_args.kwargs["purchase_pull_track"] == "purchase_order"


@pytest.mark.asyncio
async def test_pr_pull_passes_requisition_track():
    with patch(
        "apps.kuaizhizao.services.sales_order_purchase_push._list_sales_order_buy_pull_lines",
        new_callable=AsyncMock,
        return_value={"data": [], "total": 0},
    ) as inner:
        await list_purchase_requisition_sales_order_pull_lines(1)
        inner.assert_awaited_once()
        assert inner.await_args.kwargs["purchase_pull_track"] == "purchase_requisition"


@pytest.mark.asyncio
async def test_po_pull_lines_empty_when_require_pr_gate():
    with patch(
        "apps.kuaizhizao.services.sales_order_purchase_push.require_purchase_requisition_for_tenant",
        new_callable=AsyncMock,
        return_value=True,
    ):
        res = await list_purchase_order_sales_order_pull_lines(1)
    assert res == {"data": [], "total": 0}


@pytest.mark.asyncio
async def test_pr_pull_lines_skips_require_pr_gate():
    with patch(
        "apps.kuaizhizao.services.sales_order_purchase_push.require_purchase_requisition_for_tenant",
        new_callable=AsyncMock,
        return_value=True,
    ):
        with patch(
            "apps.kuaizhizao.services.sales_order_purchase_push._list_sales_order_buy_pull_lines",
            new_callable=AsyncMock,
            return_value={"data": [{"id": 1}], "total": 1},
        ) as inner:
            res = await list_purchase_requisition_sales_order_pull_lines(1)
            inner.assert_awaited_once()
    assert res["total"] == 1