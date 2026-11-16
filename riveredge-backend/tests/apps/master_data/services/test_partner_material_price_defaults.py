from decimal import Decimal

from apps.master_data.services.partner_material_price_defaults import (
    resolve_material_default_unit_price,
)


def test_material_defaults_purchase_tier():
    defaults = {
        "purchasePriceMethod": "tier",
        "defaultPurchasePriceType": "tax_exclusive",
        "purchase": {
            "tierPrices": [
                {"minQuantity": 1, "maxQuantity": 99, "unitPrice": "10"},
                {"minQuantity": 100, "unitPrice": "9"},
            ],
        },
    }
    assert resolve_material_default_unit_price(defaults, "purchase", Decimal("50")) == Decimal("10")
    assert resolve_material_default_unit_price(defaults, "purchase", Decimal("100")) == Decimal("9")


def test_material_defaults_sales_tier():
    defaults = {
        "salePriceMethod": "tier",
        "sales": {"tierPrices": [{"minQuantity": 1, "unitPrice": "12.5"}]},
    }
    assert resolve_material_default_unit_price(defaults, "sales", Decimal("3")) == Decimal("12.5")


def test_material_defaults_tier_skipped_without_quantity():
    defaults = {
        "purchasePriceMethod": "tier",
        "purchase": {"tierPrices": [{"minQuantity": 1, "unitPrice": "10"}]},
    }
    assert resolve_material_default_unit_price(defaults, "purchase", None) is None
