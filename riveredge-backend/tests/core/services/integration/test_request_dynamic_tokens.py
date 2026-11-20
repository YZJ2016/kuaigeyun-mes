from core.services.integration.request_dynamic_tokens import (
    JSON_FIELD_NOW_TOKEN,
    resolve_request_dynamic_tokens,
)


def test_resolve_now_token_in_nested_body():
    body = {
        "pageNo": 1,
        "data": {
            "start_createtime": "2026-01-01 00:00:00",
            "end_createtime": JSON_FIELD_NOW_TOKEN,
            "nested": {"ts": f"  {JSON_FIELD_NOW_TOKEN}  "},
        },
    }
    out = resolve_request_dynamic_tokens(body, now_text="2026-10-23 15:30:00")
    assert out["pageNo"] == 1
    assert out["data"]["start_createtime"] == "2026-01-01 00:00:00"
    assert out["data"]["end_createtime"] == "2026-10-23 15:30:00"
    assert out["data"]["nested"]["ts"] == "2026-10-23 15:30:00"


def test_resolve_now_token_in_list_and_params():
    params = {"t": JSON_FIELD_NOW_TOKEN, "ids": [1, JSON_FIELD_NOW_TOKEN]}
    out = resolve_request_dynamic_tokens(params, now_text="2026-10-23 01:02:03")
    assert out["t"] == "2026-10-23 01:02:03"
    assert out["ids"] == [1, "2026-10-23 01:02:03"]


def test_omit_empty_datetime_strings():
    body = {
        "pageNo": 1,
        "data": {
            "start_createtime": "",
            "end_createtime": "  ",
            "billstatus": "C",
        },
    }
    out = resolve_request_dynamic_tokens(body, now_text="2026-10-23 15:30:00")
    assert out["pageNo"] == 1
    assert "start_createtime" not in out["data"]
    assert "end_createtime" not in out["data"]
    assert out["data"]["billstatus"] == "C"


def test_resolve_display_now_label():
    out = resolve_request_dynamic_tokens(
        {"data": {"start_createtime": "此刻（每次调用）"}},
        now_text="2026-10-24 08:00:00",
    )
    assert out["data"]["start_createtime"] == "2026-10-24 08:00:00"


def test_leave_unrelated_values():
    assert resolve_request_dynamic_tokens("__NOW_AT__", now_text="x") == "__NOW_AT__"
    assert resolve_request_dynamic_tokens(None) is None
    assert resolve_request_dynamic_tokens(12) == 12


def test_keep_empty_data_object_for_cosmic_getlist():
    """仓位 getList 体形：空 data 不得被 omit 掉。"""
    body = {"data": {}, "pageNo": 1, "pageSize": 1000}
    out = resolve_request_dynamic_tokens(body, now_text="2026-10-29 09:00:00")
    assert out == {"data": {}, "pageNo": 1, "pageSize": 1000}
