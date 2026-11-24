"""采购变更 diff_purchase_item 副数量"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.kuaizhizao.constants.order_change import OrderChangeLineType
from apps.kuaizhizao.services.order_change.helpers import diff_purchase_item
from infra.exceptions.exceptions import BusinessLogicError


def _source_item(**kwargs):
    base = dict(
        ordered_quantity=Decimal("10"),
        unit_price=Decimal("5"),
        tax_inclusive_unit_price=None,
        required_date="2026-11-01",
        received_quantity=Decimal("0"),
        material_code="M001",
        aux_quantity=Decimal("2"),
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_diff_purchase_item_aux_only_change():
    src = _source_item()
    change_type, diff = diff_purchase_item(
        src,
        after_quantity=Decimal("10"),
        after_unit_price=Decimal("5"),
        after_delivery_date="2026-11-01",
        after_aux_quantity=Decimal("3"),
    )
    assert change_type == OrderChangeLineType.AUX_QUANTITY.value
    assert diff["before_aux_quantity"] == Decimal("2")
    assert diff["after_aux_quantity"] == Decimal("3")


def test_diff_purchase_item_no_change_raises():
    src = _source_item()
    with pytest.raises(BusinessLogicError, match="无有效变更"):
        diff_purchase_item(
            src,
            after_quantity=Decimal("10"),
            after_unit_price=Decimal("5"),
            after_delivery_date="2026-11-01",
            after_aux_quantity=Decimal("2"),
        )