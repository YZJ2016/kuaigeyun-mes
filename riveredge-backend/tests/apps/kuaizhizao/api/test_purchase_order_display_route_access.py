"""采购订单 :display 回显与取单 GET 鉴权路径判定。"""

from unittest.mock import MagicMock

from apps.kuaizhizao.api._kuaizhizao_route_access import _purchase_order_get_accepts_display


def _mock_request(method: str, path: str) -> MagicMock:
    req = MagicMock()
    req.method = method
    req.url.path = path
    return req


def test_purchase_order_detail_get_accepts_display():
    req = _mock_request(
        "GET",
        "/api/v1/apps/kuaizhizao/purchase-orders/42",
    )
    assert _purchase_order_get_accepts_display(req) is True


def test_purchase_order_list_get_does_not_accept_display_only_path():
    req = _mock_request("GET", "/api/v1/apps/kuaizhizao/purchase-orders")
    assert _purchase_order_get_accepts_display(req) is False


def test_purchase_order_receipt_pull_candidates_accepts_display():
    req = _mock_request(
        "GET",
        "/api/v1/apps/kuaizhizao/purchase-orders/receipt-pull-candidates",
    )
    assert _purchase_order_get_accepts_display(req) is True


def test_purchase_order_tracking_get_not_display_pull_path():
    req = _mock_request(
        "GET",
        "/api/v1/apps/kuaizhizao/purchase-orders/42/tracking",
    )
    assert _purchase_order_get_accepts_display(req) is False
