"""出站请求合并顺序：覆盖先于预置升级（契约单测）。"""

from core.services.application.api_test_request_merge import (
    merge_api_test_request_overrides,
)


def test_merge_overrides_win_over_stored_body():
    params, body = merge_api_test_request_overrides(
        stored_params={"page": 1},
        stored_body={"data": {"createorg_number": "dirty", "filter": ""}},
        override_params={"pageSize": 200},
        override_body={"data": {"filter": "status eq 'A'"}},
    )
    assert params == {"page": 1, "pageSize": 200}
    # 顶层 key 覆盖：override 整段 data 替换，不深合并嵌套
    assert body == {"data": {"filter": "status eq 'A'"}}


def test_merge_empty_override_keeps_stored():
    params, body = merge_api_test_request_overrides(
        stored_params={"a": 1},
        stored_body={"x": True},
        override_params=None,
        override_body=None,
    )
    assert params == {"a": 1}
    assert body == {"x": True}


def test_merge_non_dict_stored_body_replaced_by_override():
    params, body = merge_api_test_request_overrides(
        stored_params=None,
        stored_body=["not", "a", "dict"],
        override_body={"ok": 1},
    )
    assert params == {}
    assert body == {"ok": 1}


def test_merge_does_not_mutate_stored_inputs():
    stored_params = {"page": 1}
    stored_body = {"data": {"createorg_number": "dirty"}}
    merge_api_test_request_overrides(
        stored_params=stored_params,
        stored_body=stored_body,
        override_params={"page": 2},
        override_body={"data": {"filter": "A"}},
    )
    assert stored_params == {"page": 1}
    assert stored_body == {"data": {"createorg_number": "dirty"}}
