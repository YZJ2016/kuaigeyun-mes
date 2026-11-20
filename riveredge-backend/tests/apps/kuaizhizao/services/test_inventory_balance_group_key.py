from apps.kuaizhizao.services.report_enhancements import (
    inventory_balance_group_location_code,
    inventory_material_balance_group_key,
)


def test_material_balance_group_key_ignores_warehouse_name():
    row_a = {
        "material_id": 1,
        "warehouse_id": 5,
        "warehouse_name": "原料仓",
        "location_code": "",
    }
    row_b = {
        "material_id": 1,
        "warehouse_id": 5,
        "warehouse_name": "原料仓 ",
        "location_code": None,
    }
    assert inventory_material_balance_group_key(row_a) == inventory_material_balance_group_key(row_b)


def test_material_balance_group_location_default_empty_equivalent():
    assert inventory_balance_group_location_code("") == ""
    assert inventory_balance_group_location_code("DEFAULT") == ""
    assert inventory_balance_group_location_code("A-01") == "A-01"
