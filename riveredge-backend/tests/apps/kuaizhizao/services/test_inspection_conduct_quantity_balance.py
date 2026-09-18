"""检验开展：合格+不合格数量与检验数量平衡（含小数）。"""

from decimal import Decimal

import pytest

from apps.kuaizhizao.services.inspection_quantity_utils import (
    assert_inspection_quantities_balanced,
    to_inspection_quantity,
)
from infra.exceptions import ValidationError


def test_decimal_inspection_quantity_balanced_with_float_payload():
    qualified, unqualified = assert_inspection_quantities_balanced(
        48.36,
        0.0,
        Decimal("48.36"),
    )
    assert qualified == Decimal("48.36")
    assert unqualified == Decimal("0.00")


def test_inspection_quantity_rejects_sum_mismatch():
    with pytest.raises(ValidationError, match="合格数量和不合格数量之和必须等于检验数量"):
        assert_inspection_quantities_balanced(48.35, 0, Decimal("48.36"))


def test_to_inspection_quantity_quantizes():
    assert to_inspection_quantity("48.36") == Decimal("48.36")
    assert to_inspection_quantity("2.1") == Decimal("2.10")


def test_four_decimal_places_balanced():
    qualified, unqualified = assert_inspection_quantities_balanced(
        Decimal("0.125"),
        Decimal("0"),
        Decimal("0.125"),
        decimal_places=4,
    )
    assert qualified == Decimal("0.1250")
    assert unqualified == Decimal("0.0000")


def test_four_decimal_places_rejects_two_decimal_rounded_payload():
    with pytest.raises(ValidationError, match="合格数量和不合格数量之和必须等于检验数量"):
        assert_inspection_quantities_balanced(
            Decimal("0.13"),
            Decimal("0"),
            Decimal("0.125"),
            decimal_places=4,
        )
