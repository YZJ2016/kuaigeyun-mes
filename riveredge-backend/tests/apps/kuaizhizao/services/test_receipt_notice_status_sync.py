"""收货通知单 status 与关联采购入库单同步。"""

from apps.kuaizhizao.services.receipt_notice_service import (
    _PURCHASE_RECEIPT_OPEN_STATUSES,
    _PURCHASE_RECEIPT_RECEIVED_STATUSES,
)


def test_purchase_receipt_received_statuses_cover_inbound_done():
    assert "已入库" in _PURCHASE_RECEIPT_RECEIVED_STATUSES
    assert "待入库" in _PURCHASE_RECEIPT_OPEN_STATUSES
