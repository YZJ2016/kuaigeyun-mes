"""采购订单收货进度：已入库孤儿行按物料归集。"""

from decimal import Decimal

import pytest

from apps.kuaizhizao.services.warehouse_service import (
    _merge_orphan_confirmed_receipt_qty_for_order_items,
)


class _PoItem:
    def __init__(self, *, id: int, order_id: int, material_id: int):
        self.id = id
        self.order_id = order_id
        self.material_id = material_id


class _RItem:
    def __init__(self, *, receipt_id: int, material_id: int, qty: str):
        self.receipt_id = receipt_id
        self.purchase_order_item_id = None
        self.material_id = material_id
        self.receipt_quantity = Decimal(qty)


@pytest.mark.asyncio
async def test_merge_orphan_receipt_qty_by_material(monkeypatch):
    order_items = [_PoItem(id=11, order_id=7, material_id=900)]
    confirmed = {11: Decimal("0")}

    def fake_receipt_filter(**_kw):
        class _Q:
            async def values(self, *_a, **_k):
                return [{"id": 501, "status": "已入库", "purchase_order_id": 7}]

        return _Q()

    def fake_item_filter(**_kw):
        class _Q:
            async def all(self):
                return [_RItem(receipt_id=501, material_id=900, qty="50")]

        return _Q()

    monkeypatch.setattr(
        "apps.kuaizhizao.services.warehouse_service.PurchaseReceipt.filter",
        fake_receipt_filter,
    )
    monkeypatch.setattr(
        "apps.kuaizhizao.services.warehouse_service.PurchaseReceiptItem.filter",
        fake_item_filter,
    )

    await _merge_orphan_confirmed_receipt_qty_for_order_items(1, order_items, confirmed)
    assert confirmed[11] == Decimal("50")