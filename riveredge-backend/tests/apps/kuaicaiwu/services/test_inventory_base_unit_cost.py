"""库存基础单位计价测试。"""

from decimal import Decimal
from types import SimpleNamespace

from apps.kuaicaiwu.services.inventory_cost_service import InventoryCostService


def _box_material():
    return SimpleNamespace(
        base_unit="个",
        units={
            "units": [{"unit": "箱", "numerator": 1000, "denominator": 1}],
            "scenarios": {"purchase": "箱"},
        },
        defaults={
            "purchase": {"purchase_price": 50},
        },
        source_config=None,
    )


def test_resolve_material_base_unit_cost_converts_purchase_price():
    material = _box_material()
    assert InventoryCostService.resolve_material_base_unit_cost(material) == Decimal("0.05")


def test_resolve_material_base_unit_cost_keeps_moving_average_as_base():
    material = _box_material()
    material.defaults["moving_average_cost"] = 0.05
    assert InventoryCostService.resolve_material_base_unit_cost(material) == Decimal("0.05")
