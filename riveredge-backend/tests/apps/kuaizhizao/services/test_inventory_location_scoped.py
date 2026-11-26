"""整仓库位不应启用 location_scoped（与仓级可用量 / FIFO 扣减一致）。"""

from __future__ import annotations

from types import SimpleNamespace

from apps.kuaizhizao.services.inventory_service import InventoryService


def test_whole_warehouse_location_code_patterns() -> None:
    assert InventoryService.is_whole_warehouse_location_code("CK0009-整仓")
    assert InventoryService.is_whole_warehouse_location_code("整仓")
    assert not InventoryService.is_whole_warehouse_location_code("CK0009-A01")
    assert not InventoryService.is_whole_warehouse_location_code("")


def test_line_item_location_scoped_whole_warehouse_is_false() -> None:
    item = SimpleNamespace(location_code="CK0009-整仓", location_id=99)
    assert InventoryService.line_item_location_scoped(item) is False


def test_line_item_location_scoped_real_location_is_true() -> None:
    item = SimpleNamespace(location_code="CK0009-A01", location_id=12)
    assert InventoryService.line_item_location_scoped(item) is True