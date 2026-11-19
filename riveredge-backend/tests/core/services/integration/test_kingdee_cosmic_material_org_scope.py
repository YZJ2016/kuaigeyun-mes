from core.services.integration.kingdee_cosmic_material_org_scope import (
    filter_cosmic_material_rows_by_org_numbers,
)


def test_filter_cosmic_material_rows_by_org_numbers():
    rows = [
        {"number": "A", "name": "1"},
        {"number": "B", "name": "2"},
    ]
    kept = filter_cosmic_material_rows_by_org_numbers(rows, frozenset({"A"}))
    assert len(kept) == 1
    assert kept[0]["number"] == "A"


def test_filter_cosmic_material_rows_by_org_numbers_empty_means_none():
    rows = [{"number": "A"}, {"number": "B"}]
    assert filter_cosmic_material_rows_by_org_numbers(rows, frozenset()) == []
