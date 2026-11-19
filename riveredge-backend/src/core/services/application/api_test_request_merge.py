"""
接口测试 / 同步拉数共用的出站请求合并契约。

顺序（硬约束）：
1. 深拷贝库内 request_params / request_body
2. 用本次调用覆盖（同步传入的 body、接口调试表单）merge 上去
3. 再跑 Cosmic/星空等预置升级（在 api_service.test_api 内）

禁止：先升级再无条件 update(test_request.body)——同步脏模板会盖回升级结果，
造成「接口调试正常、物料同步异常」。
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Mapping, Optional, Tuple


def merge_api_test_request_overrides(
    *,
    stored_params: Any,
    stored_body: Any,
    override_params: Optional[Mapping[str, Any]] = None,
    override_body: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], Any]:
    """
    合并测试/同步覆盖到库内定义的本地副本。

    Returns:
        (call_request_params, call_request_body)
    """
    call_request_params: Dict[str, Any] = (
        copy.deepcopy(stored_params) if isinstance(stored_params, dict) else {}
    )
    if not isinstance(call_request_params, dict):
        call_request_params = {}

    call_request_body: Any = copy.deepcopy(stored_body) if stored_body else {}

    if override_params:
        call_request_params.update(copy.deepcopy(dict(override_params)))
    if override_body:
        if not isinstance(call_request_body, dict):
            call_request_body = {}
        call_request_body.update(copy.deepcopy(dict(override_body)))

    return call_request_params, call_request_body


_PAGING_BODY_KEYS = ("pageNo", "pageSize", "page_no", "page_size")


def preserve_request_paging_fields(old_body: Any, new_body: Any) -> Any:
    """
    预置升级若整表替换 request_body，须保留本次调用的翻页字段。

    否则同步/接口测试第 2 页起会被打回 pageNo=1（单位同步走物料 batchQuery 时曾中招）。
    """
    if not isinstance(new_body, dict):
        return new_body
    out = copy.deepcopy(new_body)
    if not isinstance(old_body, dict):
        return out
    for key in _PAGING_BODY_KEYS:
        value = old_body.get(key)
        if value not in (None, ""):
            out[key] = value
    return out
