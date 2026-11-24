from decimal import Decimal

from apps.kuaizhizao.schemas.purchase import PurchaseOrderItemCreate, PurchaseOrderItemUpdate


def _base_item_kwargs() -> dict:
    return {
        "material_id": 1,
        "material_code": "M001",
        "material_name": "物料",
        "ordered_quantity": Decimal("1"),
        "unit": "件",
        "unit_price": Decimal("1"),
        "total_price": Decimal("1"),
        "tax_rate": Decimal("13"),
        "required_date": "2026-11-22",
    }


def test_purchase_order_item_create_accepts_zero_unit_price():
    row = PurchaseOrderItemCreate(**{**_base_item_kwargs(), "unit_price": Decimal("0"), "total_price": Decimal("0")})
    assert row.unit_price == Decimal("0")


def test_purchase_order_item_update_accepts_zero_unit_price():
    row = PurchaseOrderItemUpdate(**{**_base_item_kwargs(), "unit_price": Decimal("0"), "total_price": Decimal("0")})
    assert row.unit_price == Decimal("0")