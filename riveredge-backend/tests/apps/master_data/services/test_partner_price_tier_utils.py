from decimal import Decimal

import pytest

from apps.master_data.services.partner_price_tier_utils import (
    match_tier_unit_price,
    normalize_tier_prices_for_storage,
    validate_tier_intervals,
)


def test_match_tier_picks_highest_min_quantity():
    tiers = normalize_tier_prices_for_storage(
        [
            {"minQuantity": 1, "maxQuantity": 99, "unitPrice": "10"},
            {"minQuantity": 100, "maxQuantity": None, "unitPrice": "9"},
        ]
    )
    assert match_tier_unit_price(tiers, Decimal("50")) == Decimal("10")
    assert match_tier_unit_price(tiers, Decimal("100")) == Decimal("9")
    assert match_tier_unit_price(tiers, Decimal("1")) == Decimal("10")


def test_match_tier_none_without_quantity():
    tiers = normalize_tier_prices_for_storage([{"minQuantity": 1, "unitPrice": "10"}])
    assert match_tier_unit_price(tiers, None) is None


def test_validate_tier_overlap_raises():
    with pytest.raises(ValueError, match="重叠"):
        validate_tier_intervals(
            [
                {"minQuantity": 1, "maxQuantity": 100, "unitPrice": "1"},
                {"minQuantity": 50, "maxQuantity": None, "unitPrice": "2"},
            ]
        )
