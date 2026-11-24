"""resolve_material_inventory_unit：无主数据换算时不得采纳残留库存单位。"""

from types import SimpleNamespace

from apps.kuaizhizao.utils.material_unit_utils import resolve_material_inventory_unit


def test_inventory_unit_falls_back_to_base_without_aux_units():
    mat = SimpleNamespace(
        base_unit="包",
        inventory_unit="个",
        units=None,
    )
    assert resolve_material_inventory_unit(mat) == "包"


def test_inventory_unit_keeps_fixed_aux_when_configured():
    mat = SimpleNamespace(
        base_unit="kg",
        inventory_unit="箱",
        units={
            "units": [
                {
                    "unit": "箱",
                    "conversion_type": "fixed",
                    "numerator": 1,
                    "denominator": 12,
                }
            ],
            "scenarios": {"inventory": "箱"},
        },
    )
    assert resolve_material_inventory_unit(mat) == "箱"