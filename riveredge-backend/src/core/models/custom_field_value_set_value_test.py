"""CustomFieldValue.set_value 契约（无 DB）。"""

from decimal import Decimal

import pytest

from core.models.custom_field_value import CustomFieldValue


def _value() -> CustomFieldValue:
    return CustomFieldValue()


def test_associated_object_display_text_stores_value_text():
    row = _value()
    row.set_value(
        "2.8kg/个",
        "associated_object",
        {"displayMode": "display", "returnField": "base_unit"},
    )
    assert row.value_text == "2.8kg/个"
    assert row.value_number is None
    assert row.get_stored_value("associated_object") == "2.8kg/个"


def test_associated_object_numeric_id_stores_value_number():
    row = _value()
    row.set_value(42, "associated_object", {"displayMode": "select"})
    assert row.value_number == Decimal("42")
    assert row.value_text is None


def test_associated_object_display_mode_number_rejects_unit_text():
    row = _value()
    with pytest.raises(ValueError, match="自定义数值字段值无效"):
        row.set_value(
            "2.8kg/个",
            "associated_object",
            {"displayMode": "number"},
        )


def test_associated_object_display_mode_number_accepts_decimal():
    row = _value()
    row.set_value("2.8", "associated_object", {"displayMode": "number"})
    assert row.value_number == Decimal("2.8")
