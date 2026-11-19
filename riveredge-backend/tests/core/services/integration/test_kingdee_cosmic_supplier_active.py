"""苍穹供应商「仅有效」：pbdfl 无 status 时不得滤空。"""

from core.services.integration.kingdee_cosmic_supplier_org_scope import (
    filter_cosmic_supplier_rows_active,
    is_cosmic_supplier_pbdfl_path,
    is_cosmic_supplier_row_active,
)


def test_pbdfl_path_detect():
    assert is_cosmic_supplier_pbdfl_path(
        "kapi/v2/k6s3/basedata/bd_supplier/pbdfl/query"
    )
    assert not is_cosmic_supplier_pbdfl_path(
        "kapi/v2/basedata/bd_supplier/query"
    )


def test_pbdfl_row_active_by_enable_only():
    path = "kapi/v2/k6s3/basedata/bd_supplier/pbdfl/query"
    row = {
        "number": "1.003",
        "name": "测",
        "enable": "1",
        "group_name": "1原材料供应商",
        "group_number": "1RMS",
    }
    assert is_cosmic_supplier_row_active(row, path=path) is True
    assert is_cosmic_supplier_row_active({**row, "enable": "0"}, path=path) is False


def test_standard_query_still_requires_status_c():
    path = "kapi/v2/basedata/bd_supplier/query"
    assert (
        is_cosmic_supplier_row_active(
            {"number": "1", "enable": "1", "status": "C"}, path=path
        )
        is True
    )
    assert (
        is_cosmic_supplier_row_active(
            {"number": "1", "enable": "1", "status": "A"}, path=path
        )
        is False
    )
    # 标品缺 status / 空串不得按「仅 enable」放行（与 pbdfl 分流）
    assert (
        is_cosmic_supplier_row_active({"number": "1", "enable": "1"}, path=path)
        is False
    )
    assert (
        is_cosmic_supplier_row_active(
            {"number": "1", "enable": "1", "status": ""}, path=path
        )
        is False
    )


def test_filter_pbdfl_keeps_enabled_rows():
    path = "/v2/k6s3/basedata/bd_supplier/pbdfl/query"
    rows = [
        {"number": "1", "enable": "1"},
        {"number": "2", "enable": "0"},
        {"number": "3", "enable": "1"},
    ]
    kept = filter_cosmic_supplier_rows_active(rows, path=path)
    assert [r["number"] for r in kept] == ["1", "3"]
