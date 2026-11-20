"""采购类型与金蝶 variant 路由单测。"""

import pytest

from apps.kuaizhizao.constants.purchase_order_type import (
    PURCHASE_ORDER_TYPE_ASSET,
    PURCHASE_ORDER_TYPE_SERVICE,
    PURCHASE_ORDER_TYPE_STANDARD,
    assert_purchase_order_type_matches_material_categories,
    assert_purchase_order_type_matches_material_rows,
    is_service_purchase_order_type,
    normalize_purchase_order_type,
)
from apps.master_data.constants.material_inventory_category import (
    INVENTORY_CATEGORY_ASSET,
    INVENTORY_CATEGORY_SERVICE,
)
from apps.master_data.constants.material_source_type import SOURCE_TYPE_SERVICE
from infra.exceptions.exceptions import BusinessLogicError, ValidationError


def test_normalize_purchase_order_type_maps_framework_to_standard():
    assert normalize_purchase_order_type("框架协议") == PURCHASE_ORDER_TYPE_STANDARD


def test_normalize_rejects_unknown():
    with pytest.raises(ValidationError):
        normalize_purchase_order_type("寄售采购")


def test_asset_type_requires_asset_materials():
    assert_purchase_order_type_matches_material_categories(
        PURCHASE_ORDER_TYPE_ASSET,
        {INVENTORY_CATEGORY_ASSET},
    )


def test_standard_type_rejects_asset_line():
    with pytest.raises(BusinessLogicError):
        assert_purchase_order_type_matches_material_categories(
            PURCHASE_ORDER_TYPE_STANDARD,
            {INVENTORY_CATEGORY_ASSET},
        )


def test_standard_type_rejects_asset_line_lists_material():
    with pytest.raises(BusinessLogicError, match="FA-001") as exc:
        assert_purchase_order_type_matches_material_rows(
            PURCHASE_ORDER_TYPE_STANDARD,
            [
                {
                    "main_code": "FA-001",
                    "name": "数控机床",
                    "inventory_category": INVENTORY_CATEGORY_ASSET,
                    "source_type": None,
                }
            ],
            document_label="采购申请",
        )
    assert "资产采购" in str(exc.value)
    assert "存货类别：资产" in str(exc.value)


def test_service_type_requires_service_materials():
    assert_purchase_order_type_matches_material_categories(
        PURCHASE_ORDER_TYPE_SERVICE,
        {INVENTORY_CATEGORY_SERVICE},
    )


def test_service_type_rejects_stock_line():
    with pytest.raises(BusinessLogicError):
        assert_purchase_order_type_matches_material_categories(
            PURCHASE_ORDER_TYPE_SERVICE,
            {INVENTORY_CATEGORY_ASSET},
        )


def test_service_type_accepts_service_source_without_inventory_category():
    assert_purchase_order_type_matches_material_categories(
        PURCHASE_ORDER_TYPE_SERVICE,
        {(None, SOURCE_TYPE_SERVICE)},
    )


def test_service_type_rejects_uncategorized_buy_material():
    with pytest.raises(BusinessLogicError):
        assert_purchase_order_type_matches_material_categories(
            PURCHASE_ORDER_TYPE_SERVICE,
            {(None, "Buy")},
        )


def test_standard_type_allows_empty_inventory_category():
    assert_purchase_order_type_matches_material_categories(
        PURCHASE_ORDER_TYPE_STANDARD,
        {None},
    )


def test_is_service_purchase_order_type():
    assert is_service_purchase_order_type(PURCHASE_ORDER_TYPE_SERVICE)
    assert not is_service_purchase_order_type(PURCHASE_ORDER_TYPE_STANDARD)


