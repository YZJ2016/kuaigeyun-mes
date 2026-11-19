from core.services.integration.kingdee_cosmic_supplier_org_scope import (
    filter_cosmic_supplier_rows_by_management_org_number,
    filter_cosmic_supplier_rows_by_org_numbers,
    is_cosmic_supplier_getsupplier_api,
    is_cosmic_supplier_getsupplier_path,
)


def test_is_cosmic_supplier_getsupplier_path():
    assert is_cosmic_supplier_getsupplier_path(
        "kapi/v2/fd81/basedata/bd_supplier/getsupplier"
    )
    assert not is_cosmic_supplier_getsupplier_path("kapi/v2/basedata/bd_supplier/query")


def test_is_cosmic_supplier_getsupplier_api_by_code_when_path_is_legacy_query():
    assert is_cosmic_supplier_getsupplier_api(
        path="kapi/v2/basedata/bd_supplier/query",
        code="kingdee_getsupplier_bd_supplier",
    )


def test_filter_cosmic_supplier_rows_by_management_org_number():
    rows = [
        {"number": "S1", "org_number": "BU-00001"},
        {"number": "S2", "org_number": "BU-00000"},
    ]
    kept = filter_cosmic_supplier_rows_by_management_org_number(rows, "BU-00001")
    assert len(kept) == 1
    assert kept[0]["number"] == "S1"


def test_filter_cosmic_supplier_rows_by_org_numbers():
    rows = [
        {"number": "S1", "name": "1"},
        {"number": "S2", "name": "2"},
    ]
    kept = filter_cosmic_supplier_rows_by_org_numbers(rows, frozenset({"S2"}))
    assert len(kept) == 1
    assert kept[0]["number"] == "S2"
