"""入站同步：entry / FEntity 明细摊平。"""

from core.services.data.sync_nested_expand import expand_nested_detail_rows
from core.services.data.sync_source_rows import normalize_api_body_to_rows


def test_expand_cosmic_bom_entry():
    rows = expand_nested_detail_rows(
        [
            {
                "number": "BOM1",
                "material": {"number": "P001", "name": "父件"},
                "entry": [
                    {"material": {"number": "C001"}, "qty": 2},
                    {"material": {"number": "C002"}, "qty": 1},
                ],
            }
        ]
    )
    assert len(rows) == 2
    assert rows[0]["material_number"] == "P001"
    assert rows[0]["entrymaterial_number"] == "C001"
    assert rows[0]["entryqty"] == 2
    assert rows[1]["entrymaterial_number"] == "C002"
    assert "entry" not in rows[0]


def test_expand_cosmic_bom_entry_avoids_double_prefix():
    """明细字段已带 entry 前缀时，不要再叠成 entryentry*。"""
    rows = expand_nested_detail_rows(
        [
            {
                "material": {"number": "P001"},
                "entry": [
                    {
                        "entrymaterial": {"number": "C001", "name": "子件"},
                        "entrymaterialid": {"number": "C001"},
                        "entryqty": 3,
                        "childnumerator": 3,
                    }
                ],
            }
        ]
    )
    assert rows[0]["entrymaterial_number"] == "C001"
    assert rows[0]["entrymaterialid_number"] == "C001"
    assert rows[0]["entryqty"] == 3
    assert "entryentrymaterial_number" not in rows[0]
    assert "entryentryqty" not in rows[0]


def test_expand_empty_entry_keeps_header():
    rows = expand_nested_detail_rows([{"number": "BOM1", "entry": []}])
    assert rows == [{"number": "BOM1"}]


def test_normalize_api_body_expands_nested_entry():
    body = {
        "data": {
            "rows": [
                {
                    "material": {"number": "P1"},
                    "entry": [{"material": {"number": "C1"}, "qty": 3}],
                }
            ]
        }
    }
    rows = normalize_api_body_to_rows(body)
    assert len(rows) == 1
    assert rows[0]["material_number"] == "P1"
    assert rows[0]["entrymaterial_number"] == "C1"
    assert rows[0]["entryqty"] == 3


def test_expand_fentity():
    rows = expand_nested_detail_rows(
        [{"FBillNo": "X1", "FEntity": [{"FMaterialId": {"FNumber": "M1"}, "FQty": 5}]}]
    )
    assert rows[0]["FBillNo"] == "X1"
    assert rows[0]["FEntityFMaterialId_FNumber"] == "M1"
    assert rows[0]["FEntityFQty"] == 5
