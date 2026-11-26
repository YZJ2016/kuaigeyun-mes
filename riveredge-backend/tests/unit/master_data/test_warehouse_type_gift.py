"""赠品仓库类型：只计数量不计成本。"""

from apps.master_data.constants.warehouse_type import (
    QUANTITY_ONLY_WAREHOUSE_TYPES,
    WAREHOUSE_TYPE_CHOICES,
    WAREHOUSE_TYPE_GIFT,
    is_quantity_only_warehouse_type,
)


def test_gift_warehouse_type_in_choices():
    assert WAREHOUSE_TYPE_GIFT in WAREHOUSE_TYPE_CHOICES
    assert WAREHOUSE_TYPE_GIFT in QUANTITY_ONLY_WAREHOUSE_TYPES


def test_is_quantity_only_warehouse_type():
    assert is_quantity_only_warehouse_type("gift") is True
    assert is_quantity_only_warehouse_type("GIFT") is True
    assert is_quantity_only_warehouse_type("normal") is False
    assert is_quantity_only_warehouse_type(None) is False
    assert is_quantity_only_warehouse_type("") is False
