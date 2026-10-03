"""同步无变更比较。"""

from decimal import Decimal
from types import SimpleNamespace

from apps.master_data.services.master_data_sync_common import (
    record_fields_unchanged,
    sync_values_equal,
)


def test_sync_values_equal_decimal_and_empty():
    assert sync_values_equal(Decimal("1.0"), Decimal("1"))
    assert sync_values_equal(None, "")
    assert sync_values_equal("A", "A")
    assert not sync_values_equal("A", "B")


def test_record_fields_unchanged():
    record = SimpleNamespace(quantity=Decimal("2"), unit="个", name="X")
    assert record_fields_unchanged(record, {"quantity": Decimal("2.0"), "unit": "个"})
    assert not record_fields_unchanged(record, {"quantity": Decimal("3"), "unit": "个"})
