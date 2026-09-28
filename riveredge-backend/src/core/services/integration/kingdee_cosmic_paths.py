"""金蝶AI苍穹 OpenAPI 路径约定（无重依赖，供 connector_request 等直接引用）。"""

from __future__ import annotations

from typing import Any, Dict


_BASEDATA_BATCH_OBJECTS = {
    "bd_material",
    "bd_measureunits",
    "bd_materialgroup",
    "bd_supplier",
    "bd_customer",
    "bd_warehouse",
}


def rewrite_basedata_sys_query_path(endpoint: str) -> str:
    """供应商查询是 /query；物料批量查询是 /batchQuery。"""
    ep = str(endpoint or "").strip().lstrip("/")
    if ep.lower().startswith("ierp/"):
        ep = ep[5:]
    lower = ep.lower()
    if lower == "kapi/v2/basedata/bd_supplier/batchquery":
        return "kapi/v2/basedata/bd_supplier/query"
    prefix = "kapi/sys/"
    suffix = "/query"
    if not lower.startswith(prefix) or not lower.endswith(suffix):
        return ep
    biz = lower[len(prefix) : -len(suffix)]
    if biz == "bd_supplier":
        return "kapi/v2/basedata/bd_supplier/query"
    if biz not in _BASEDATA_BATCH_OBJECTS:
        return ep
    return f"kapi/v2/basedata/{biz}/batchQuery"


def strip_kingdee_cosmic_ierp_suffix_from_base(base_url: str) -> str:
    """
    门户根地址有时误填为 …/ierp；业务与鉴权路径均相对门户根拼接，须先去掉尾部的 /ierp。
    """
    url = str(base_url or "").strip().rstrip("/")
    if url.lower().endswith("/ierp"):
        return url[: -len("/ierp")]
    return url


def _kingdee_v2_needs_paging(path: str) -> bool:
    """v2 查询类接口普遍要求 pageNo/pageSize（含 query / batchQuery / batcheQuery）。"""
    lower = str(path or "").lower()
    if "/kapi/v2/" not in lower:
        return False
    # 写操作（save/submit/audit/delete 等）不要强塞分页
    write_markers = (
        "/save",
        "/batchsave",
        "/submit",
        "/audit",
        "/unaudit",
        "/delete",
        "/update",
        "/batchadd",
        "/batchupdate",
        "/batchdelete",
        "/batchsubmit",
        "/batchaudit",
        "/batchunaudit",
        "/batchunsubmit",
        "/transmit",
        "/beginwork",
        "/endwork",
        "/shut",
    )
    if any(marker in lower for marker in write_markers):
        return False
    return any(
        marker in lower
        for marker in (
            "batchquery",
            "batchequery",
            "batchquerynew",
            "/query",
            "/getlist",
        )
    )


def ensure_kingdee_v2_request_body(url: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    v2 批量查询的请求体为 data，以及必填的 pageNo、pageSize。
    筛选字段在 data 内；pageSize 为空时金蝶返回 400。

    即时库存等接口使用顶层 params（不是 data），不可强行包进 data。
    """
    path = str(url or "").split("?", 1)[0].lower()
    if "/kapi/v2/" not in path:
        return body
    payload: Dict[str, Any] = dict(body) if isinstance(body, dict) else {}
    is_inventory = "getinventory" in path or "getinvacc" in path or "/imrealbal" in path

    # 误把 params 包进 data 时还原（旧逻辑 / 手工编辑常见），否则金蝶 NPE
    data_obj = payload.get("data")
    if is_inventory and isinstance(data_obj, dict) and "params" in data_obj and "params" not in payload:
        nested_params = data_obj.pop("params")
        payload["params"] = nested_params
        if not data_obj:
            payload.pop("data", None)

    # 库存查询：{ params, pageNo, pageSize } —— 保留 params，勿包 data
    if is_inventory or ("params" in payload and "data" not in payload):
        if "params" in payload:
            if payload.get("pageNo") in (None, ""):
                payload["pageNo"] = 1
            if payload.get("pageSize") in (None, ""):
                payload["pageSize"] = 100
            # 库存接口禁止残留空 data，避免网关 NPE
            if payload.get("data") in (None, {}, []):
                payload.pop("data", None)
            return payload

    if "data" not in payload:
        # 库存路径即使没有 params 也不要瞎包一层 data
        if is_inventory:
            if payload.get("pageNo") in (None, ""):
                payload["pageNo"] = 1
            if payload.get("pageSize") in (None, ""):
                payload["pageSize"] = 100
            return payload
        paging = {
            key: payload.pop(key)
            for key in ("pageNo", "pageSize", "page_no", "page_size")
            if key in payload
        }
        payload = {"data": payload, **paging}
    if _kingdee_v2_needs_paging(path):
        if payload.get("pageNo") in (None, ""):
            payload["pageNo"] = 1
        if payload.get("pageSize") in (None, ""):
            # 兼容金蝶偶发只认 page_size 的旧路径：主字段仍用 pageSize
            payload["pageSize"] = 100
        # 若误把 pageSize 写进 data，提到外层
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("pageNo", "pageSize", "page_no", "page_size"):
                if key in data and payload.get(key) in (None, ""):
                    payload[key] = data.pop(key)
            if payload.get("pageSize") in (None, "") and data.get("pageSize") not in (None, ""):
                payload["pageSize"] = data.pop("pageSize")
            if payload.get("pageNo") in (None, "") and data.get("pageNo") not in (None, ""):
                payload["pageNo"] = data.pop("pageNo")
    return payload

def normalize_kingdee_cosmic_api_path(endpoint: str) -> str:
    """
    业务对象 sys/query 等在网关侧挂在 /ierp/kapi/sys/...；
    OAuth getToken 等仍为 /kapi/oauth2/...（不加 ierp 前缀）。
    """
    ep = str(endpoint or "").strip().lstrip("/")
    if not ep:
        return ep
    if ep.startswith("ierp/"):
        return ep
    if ep.startswith("kapi/sys/"):
        return f"ierp/{ep}"
    return ep
