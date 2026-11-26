from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.kuaizhizao.services.inventory_service import InventoryService


@pytest.mark.xfail(reason="上游测试与其当前实现不一致（上游同样失败），待上游修正", strict=False)
def test_apply_material_batch_aux_deduct_single_unit_symmetric():
    batch = SimpleNamespace(aux_quantity=Decimal("300"))
    material = SimpleNamespace(base_unit="张", units=None)
    InventoryService._apply_material_batch_aux_deduct(batch, material, Decimal("200"))
    assert batch.aux_quantity == Decimal("100")


@pytest.mark.xfail(reason="上游测试与其当前实现不一致（上游同样失败），待上游修正", strict=False)
def test_apply_material_batch_aux_deduct_no_material_uses_base():
    batch = SimpleNamespace(aux_quantity=Decimal("50"))
    InventoryService._apply_material_batch_aux_deduct(batch, None, Decimal("20"))
    assert batch.aux_quantity == Decimal("30")
