from decimal import Decimal
from types import SimpleNamespace

from apps.kuaizhizao.services.inventory_service import InventoryService


def test_apply_material_batch_aux_deduct_single_unit_symmetric():
    batch = SimpleNamespace(
        quantity=Decimal("100"),
        base_quantity=Decimal("100"),
        aux_quantity=Decimal("300"),
    )
    material = SimpleNamespace(base_unit="张", units=None)
    InventoryService._apply_material_batch_aux_deduct(batch, material, Decimal("200"))
    assert batch.quantity == Decimal("100")
    assert batch.base_quantity == Decimal("100")
    assert batch.aux_quantity == Decimal("100")


def test_apply_material_batch_aux_deduct_no_material_uses_base():
    batch = SimpleNamespace(
        quantity=Decimal("30"),
        base_quantity=Decimal("30"),
        aux_quantity=Decimal("50"),
    )
    InventoryService._apply_material_batch_aux_deduct(batch, None, Decimal("20"))
    assert batch.quantity == Decimal("30")
    assert batch.base_quantity == Decimal("30")
    assert batch.aux_quantity == Decimal("30")
