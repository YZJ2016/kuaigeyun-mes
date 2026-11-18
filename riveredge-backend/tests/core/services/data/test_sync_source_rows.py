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


def test_normalize_cosmic_612_without_status_raises():
    """开放平台常见：仅 errorCode+message，无 status=false，不得当业务行。"""
    import pytest

    with pytest.raises(ValueError, match="bd_warehouse"):
        normalize_api_body_to_rows(
            {
                "data": None,
                "errorCode": "612",
                "message": "当前用户，无应用 sbd 下业务对象 bd_warehouse 的查询功能权限",
            }
        )


def test_normalize_items_array():
    rows = normalize_api_body_to_rows({"items": [{"id": 1}]})
    assert rows == [{"id": 1}]


def test_normalize_kingdee_matrix_with_columns():
    body = [["c1", "n1"], ["c2", "n2"]]
    rows = normalize_api_body_to_rows(body, column_names=["code", "name"])
    assert rows == [{"code": "c1", "name": "n1"}, {"code": "c2", "name": "n2"}]


def test_normalize_kingdee_nested_result_error_raises():
    """ExecuteBillQuery 失败体 [[{Result...}]] 不得摊成空 FNumber 业务行。"""
    import pytest

    body = [
        [
            {
                "Result": {
                    "ResponseStatus": {
                        "ErrorCode": 500,
                        "IsSuccess": False,
                        "Errors": [
                            {
                                "FieldName": None,
                                "Message": "标识为“BD_MATERIALGROUP”的业务对象不存在，或者被删除。",
                                "DIndex": 0,
                            }
                        ],
                        "MsgCode": 4,
                    }
                }
            }
        ]
    ]
    with pytest.raises(ValueError, match="BD_MATERIALGROUP"):
        normalize_api_body_to_rows(body, column_names=["FID", "FNumber", "FName"])


def test_normalize_query_group_info_need_return_data():
    """QueryGroupInfo 成功体 Result.NeedReturnData 行数组。"""
    body = {
        "Result": {
            "ResponseStatus": {"IsSuccess": True, "Errors": []},
            "NeedReturnData": [
                {"FNUMBER": "CHLB01", "FNAME": "原材料", "FPARENTID": "0"},
                {"FNUMBER": "CHLB02", "FNAME": "半成品", "FPARENTID": "0"},
            ],
        }
    }
    rows = normalize_api_body_to_rows(body)
    assert len(rows) == 2
    assert rows[0]["FNUMBER"] == "CHLB01"
    assert rows[1]["FNAME"] == "半成品"


def test_normalize_query_group_info_need_return_data_json_string():
    """部分环境 NeedReturnData 为 JSON 字符串。"""
    import json

    rows_payload = [{"FNUMBER": "G1", "FNAME": "分组1"}]
    body = {
        "Result": {
            "ResponseStatus": {"IsSuccess": True},
            "NeedReturnData": json.dumps(rows_payload, ensure_ascii=False),
        }
    }
    rows = normalize_api_body_to_rows(body)
    assert rows == rows_payload


def test_normalize_flattened_kingdee_error_row_raises():
    """兜底：已摊平的 IsSuccess=false 行也不得当业务数据。"""
    import pytest

    rows_body = [
        {
            "FID_Result_ResponseStatus_IsSuccess": False,
            "FID_Result_ResponseStatus_Errors_Message": "元数据中标识为FNumber的字段不存在",
            "FNumber": None,
            "FName": None,
        }
    ]
    with pytest.raises(ValueError, match="FNumber"):
        normalize_api_body_to_rows(rows_body)
