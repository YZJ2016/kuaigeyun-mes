"""客户订单号：规范化与行快照回落（契约抽检，不连库）。"""

from apps.kuaizhizao.services.sales_order_service import _normalize_customer_order_no
from apps.kuaizhizao.services.warehouse_service import (
    _customer_order_no_from_so_item,
    _normalize_customer_order_no_text,
)


def test_normalize_customer_order_no_strips_and_empty_to_none():
    assert _normalize_customer_order_no("  PO-1001  ") == "PO-1001"
    assert _normalize_customer_order_no("") is None
    assert _normalize_customer_order_no(None) is None
    assert _normalize_customer_order_no_text("  x ") == "x"


def test_customer_order_no_from_so_item_prefers_line_snapshot():
    item = type("Item", (), {"customer_order_no": "LINE-PO"})()
    assert _customer_order_no_from_so_item(item, "HDR-PO") == "LINE-PO"
    assert _customer_order_no_from_so_item(type("Item", (), {"customer_order_no": None})(), "HDR-PO") == "HDR-PO"