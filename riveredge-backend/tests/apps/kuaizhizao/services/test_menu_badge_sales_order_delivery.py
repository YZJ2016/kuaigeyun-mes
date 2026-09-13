"""销售订单菜单徽章：按明细交货状态统计。"""

from apps.kuaizhizao.services.menu_badge_counts_service import (
    _SALES_ORDER_DELIVERY_EXCLUDED_REVIEW,
    _SALES_ORDER_DELIVERY_EXCLUDED_STATUS,
    _SALES_ORDER_UNDELIVERED_ITEM_STATUSES,
)


def test_sales_order_badge_uses_undelivered_item_statuses_only():
    assert _SALES_ORDER_UNDELIVERED_ITEM_STATUSES == ["待交货", "部分交货"]
    assert "已交货" not in _SALES_ORDER_UNDELIVERED_ITEM_STATUSES


def test_sales_order_badge_excludes_draft_terminal_and_pending_review():
    assert "DRAFT" in _SALES_ORDER_DELIVERY_EXCLUDED_STATUS
    assert "草稿" in _SALES_ORDER_DELIVERY_EXCLUDED_STATUS
    assert "COMPLETED" in _SALES_ORDER_DELIVERY_EXCLUDED_STATUS
    assert "待审核" in _SALES_ORDER_DELIVERY_EXCLUDED_REVIEW
    assert "PENDING" in _SALES_ORDER_DELIVERY_EXCLUDED_REVIEW
