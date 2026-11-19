"""同步无变更比较与「映射字段有变更则更新」契约。"""

from decimal import Decimal
from types import SimpleNamespace

from apps.master_data.services.master_data_sync_common import (
    apply_proposed_fields_to_record,
    collect_mapped_scalar_proposed,
    list_changed_sync_fields,
    record_fields_unchanged,
    sync_record_needs_update,
    sync_values_equal,
)


def test_sync_values_equal_decimal_and_empty():
    assert sync_values_equal(Decimal("1.0"), Decimal("1"))
    assert sync_values_equal(None, "")
    assert sync_values_equal("A", "A")
    assert not sync_values_equal("A", "B")


def test_sync_values_equal_bool_none_not_false():
    assert not sync_values_equal(None, False)
    assert not sync_values_equal(False, None)
    assert sync_values_equal(True, True)
    assert sync_values_equal(False, "0")


def test_record_fields_unchanged():
    record = SimpleNamespace(quantity=Decimal("2"), unit="个", name="X")
    assert record_fields_unchanged(record, {"quantity": Decimal("2.0"), "unit": "个"})
    assert not record_fields_unchanged(record, {"quantity": Decimal("3"), "unit": "个"})


def test_collect_mapped_scalar_proposed_only_mapped_keys():
    proposed = collect_mapped_scalar_proposed(
        {"category": "原料供应商", "name_ignored": "x"},
        string_fields=frozenset({"short_name", "category", "phone"}),
        always={"name": "甲供应商"},
    )
    assert proposed == {"name": "甲供应商", "category": "原料供应商"}
    assert "short_name" not in proposed
    assert "phone" not in proposed


def test_sync_record_needs_update_on_mapped_field_change():
    record = SimpleNamespace(name="甲", category="ZCGYS", short_name="甲短")
    proposed = collect_mapped_scalar_proposed(
        {"category": "原料供应商"},
        string_fields=frozenset({"short_name", "category"}),
        always={"name": "甲"},
    )
    assert list_changed_sync_fields(record, proposed) == ["category"]
    assert sync_record_needs_update(record, proposed)
    assert not sync_record_needs_update(
        record,
        collect_mapped_scalar_proposed(
            {"category": "ZCGYS"},
            string_fields=frozenset({"category"}),
            always={"name": "甲"},
        ),
    )


def test_sync_record_needs_update_force():
    record = SimpleNamespace(name="甲", category="ZCGYS")
    proposed = {"name": "甲", "category": "ZCGYS"}
    assert not sync_record_needs_update(record, proposed)
    assert sync_record_needs_update(record, proposed, force=True)


def test_apply_proposed_does_not_clear_unmapped():
    record = SimpleNamespace(name="甲", category="旧分类", short_name="短名")
    proposed = collect_mapped_scalar_proposed(
        {"category": "新分类"},
        string_fields=frozenset({"short_name", "category"}),
        always={"name": "甲"},
    )
    touched = apply_proposed_fields_to_record(record, proposed)
    assert touched == ["category"]
    assert record.category == "新分类"
    assert record.short_name == "短名"
