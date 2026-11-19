from core.services.integration.kingdee_cosmic_customer_org_scope import (
    filter_cosmic_customer_rows_by_management_org_number,
    is_cosmic_customer_getcustomer_api,
    is_cosmic_customer_getcustomer_path,
)


def test_is_cosmic_customer_getcustomer_path():
    assert is_cosmic_customer_getcustomer_path(
        "kapi/v2/fd81/basedata/bd_customer/getcustomer"
    )
    assert not is_cosmic_customer_getcustomer_path(
        "kapi/v2/basedata/bd_customer/batchQuery"
    )


def test_is_cosmic_customer_getcustomer_api_by_code_when_path_is_legacy():
    assert is_cosmic_customer_getcustomer_api(
        path="kapi/v2/basedata/bd_customer/batchQuery",
        code="kingdee_getcustomer_bd_customer",
    )


def test_filter_cosmic_customer_rows_by_management_org_number():
    rows = [
        {"number": "C1", "org_number": "BU-00001"},
        {"number": "C2", "org_number": "BU-00002"},
        {"number": "C3"},
    ]
    kept = filter_cosmic_customer_rows_by_management_org_number(rows, "BU-00001")
    assert [r["number"] for r in kept] == ["C1"]
