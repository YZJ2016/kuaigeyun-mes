"""sync_source_rows.normalize_api_body_to_rows — 含苍穹 data.rows 嵌套。"""

from core.services.data.sync_source_rows import normalize_api_body_to_rows


def test_normalize_top_level_object_list():
    rows = normalize_api_body_to_rows([{"code": "A"}, {"code": "B"}])
    assert [r["code"] for r in rows] == ["A", "B"]


def test_normalize_cosmic_data_rows_nested():
    body = {
        "data": {
            "pageNo": 1,
            "rows": [
                {"number": "M1", "name": "物料1"},
                {"number": "M2", "name": "物料2"},
            ],
        }
    }
    rows = normalize_api_body_to_rows(body)
    assert len(rows) == 2
    assert rows[0]["number"] == "M1"
    assert rows[1]["name"] == "物料2"


def test_normalize_empty_data_rows():
    rows = normalize_api_body_to_rows({"data": {"rows": []}})
    assert rows == []


def test_normalize_cosmic_status_false_raises():
    import pytest

    with pytest.raises(ValueError, match="token expired"):
        normalize_api_body_to_rows(
            {
                "status": False,
                "errorCode": "401",
                "message": "token expired",
                "data": {},
            }
        )


def test_normalize_items_array():
    rows = normalize_api_body_to_rows({"items": [{"id": 1}]})
    assert rows == [{"id": 1}]


def test_normalize_kingdee_matrix_with_columns():
    body = [["c1", "n1"], ["c2", "n2"]]
    rows = normalize_api_body_to_rows(body, column_names=["code", "name"])
    assert rows == [{"code": "c1", "name": "n1"}, {"code": "c2", "name": "n2"}]
