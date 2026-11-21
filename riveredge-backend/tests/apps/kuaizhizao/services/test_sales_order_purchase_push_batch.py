"""销售订单直推采购占用统计辅助逻辑单测。"""

from decimal import Decimal

from apps.kuaizhizao.services.sales_order_purchase_push import (
    _add_po_item_qty,
    _is_purchase_order_doc_type,
    _is_sales_order_source,
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