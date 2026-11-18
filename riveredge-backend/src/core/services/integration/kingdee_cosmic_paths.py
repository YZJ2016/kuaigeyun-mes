"""金蝶AI苍穹 OpenAPI 路径约定（无重依赖，供 connector_request 等直接引用）。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


_BASEDATA_BATCH_OBJECTS = {
    "bd_material",
    "bd_measureunits",
    "bd_multimeasureunit",
    "bd_materialgroup",
    "bd_supplier",
    "bd_customer",
    "bd_warehouse",
}


_INCOMPLETE_SUPPLIER_PATH_MARKERS = frozenset(
    {
        "kapi/v2/basedata/b",
        "kapi/v2/basedata/bd",
        "v2/basedata/b",
    }
)
SUPPLIER_QUERY_ENDPOINT = "kapi/v2/basedata/bd_supplier/query"


def repair_incomplete_supplier_endpoint(endpoint: str) -> str:
    """
    接口库常见误存路径 …/basedata/b（缺 bd_supplier/query）。
    补全为制造链路探活地址，不是另猜路由。
    """
    ep = str(endpoint or "").strip().lstrip("/")
    lower = ep.lower().replace("\\", "/").rstrip("/")
    if lower in _INCOMPLETE_SUPPLIER_PATH_MARKERS or lower.endswith("/basedata/b"):
        return SUPPLIER_QUERY_ENDPOINT
    return ep


def normalize_cosmic_openapi_endpoint(endpoint: str) -> str:
    """相对路径：开放平台 /v2/… 补 kapi 前缀，旧 sys/query 按物料/客户规则改写。"""
    ep = str(endpoint or "").strip().lstrip("/")
    if ep.lower().startswith("v2/"):
        ep = f"kapi/{ep.lstrip('/')}"
    ep = rewrite_basedata_sys_query_path(ep)
    return repair_incomplete_supplier_endpoint(ep)


def strip_invalid_kingdee_cosmic_base_url_suffix(base_url: str) -> str:
    """
    连接器 base_url 误粘贴了接口路径（含截断的 …/basedata/b）时，剥回到门户根。
    """
    url = str(base_url or "").strip().rstrip("/")
    lower = url.lower()
    cut_markers = (
        "/kapi/v2/basedata/b",
        "/kapi/v2/basedata/bd_supplier/query",
        "/kapi/v2/basedata/bd_supplier/batchquery",
        "/kapi/v2/basedata/bd_material/batchquery",
    )
    for marker in cut_markers:
        idx = lower.find(marker)
        if idx > 0:
            return url[:idx].rstrip("/")
    return url


def rewrite_basedata_sys_query_path(endpoint: str) -> str:
    """
    旧 sys/query → v2。物料/客户/仓库等 batchQuery；供应商与 mfg 探活一致为 …/query。
    """
    ep = str(endpoint or "").strip().lstrip("/")
    if ep.lower().startswith("ierp/"):
        ep = ep[5:]
    lower = ep.lower()
    prefix = "kapi/sys/"
    suffix = "/query"
    if not lower.startswith(prefix) or not lower.endswith(suffix):
        return ep
    biz = lower[len(prefix) : -len(suffix)]
    if biz == "bd_supplier":
        return f"kapi/v2/basedata/{biz}/query"
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


def _is_flat_v2_query_path(path: str) -> bool:
    """请求体顶层筛选项 + pageNo/pageSize，勿包进 data（库存、商品分类 getMalGoodsClass 等）。"""
    lower = str(path or "").split("?", 1)[0].lower()
    return (
        "getinventory" in lower
        or "getinvacc" in lower
        or "/imrealbal" in lower
        or "getmalgoodsclass" in lower
        or "mdr_goodsclass" in lower
        or "/gmc/" in lower
    )


def ensure_kingdee_v2_request_body(url: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    v2 批量查询的请求体为 data，以及必填的 pageNo、pageSize。
    筛选字段在 data 内；pageSize 为空时金蝶返回 400。

    即时库存、商品分类 getMalGoodsClass 等使用顶层字段（不是 data），不可强行包进 data。
    """
    path = str(url or "").split("?", 1)[0].lower().replace("\\", "/")
    # 相对路径常为 kapi/v2/...（无前导 /），须同样规范化
    if "kapi/v2/" not in path:
        return body
    payload: Dict[str, Any] = dict(body) if isinstance(body, dict) else {}
    is_inventory = "getinventory" in path or "getinvacc" in path or "/imrealbal" in path
    is_flat = _is_flat_v2_query_path(path)

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

    if is_flat:
        # 商品分类等：筛选字段与 pageNo/pageSize 同级；去掉误包的空 data
        if payload.get("data") in (None, {}, []):
            payload.pop("data", None)
        if payload.get("pageNo") in (None, ""):
            payload["pageNo"] = 1
        if payload.get("pageSize") in (None, ""):
            payload["pageSize"] = 100
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


def resolve_kingdee_cosmic_createorg_number(cfg: Optional[Dict[str, Any]]) -> str:
    """连接器组织编码：仓库/供应商 basedata 查询的 createorg_number。"""
    data = cfg if isinstance(cfg, dict) else {}
    for key in ("createorg_number", "create_org_number", "org_number", "orgNumber"):
        val = str(data.get(key) or "").strip()
        if val:
            return val
    return ""


def _path_without_query(url: str) -> str:
    return str(url or "").split("?", 1)[0]


def _is_basedata_single_query(path: str) -> bool:
    lower = _path_without_query(path).lower()
    return "/basedata/" in lower and lower.endswith("/query") and "batchquery" not in lower


def _is_warehouse_path(path: str) -> bool:
    return "bd_warehouse" in _path_without_query(path).lower()


def _is_location_path(path: str) -> bool:
    return "bd_location" in _path_without_query(path).lower()


def _is_material_batchquery_path(path: str) -> bool:
    """集团创建、子公司管理：batchQuery 仅剥离 createorg 筛选，管理组织 org_number 可选手工填写。

    含物料与物料分类（bd_material / bd_materialgroup）；二者均勿用 createorg_number 当子公司范围。
    """
    lower = _path_without_query(path).lower().replace("\\", "/")
    return (
        "/bd_material/batchquery" in lower
        or "/bd_materialgroup/batchquery" in lower
    )


def _is_group_created_master_query_path(path: str) -> bool:
    """集团创建、子公司管理：query 主档不得用 createorg_number 收窄（须 bd_*common 交集）。"""
    lower = _path_without_query(path).lower().replace("\\", "/")
    return (
        lower.endswith("/bd_supplier/query")
        or lower.endswith("/bd_customer/query")
        or lower.endswith("/bd_customer/batchquery")
        or lower.endswith("/bd_supplier/getsupplier")
        or lower.endswith("/bd_customer/getcustomer")
    )


def _is_supplier_getsupplier_path(path: str) -> bool:
    lower = _path_without_query(path).lower().replace("\\", "/")
    return lower.endswith("/bd_supplier/getsupplier")


def _is_customer_getcustomer_path(path: str) -> bool:
    lower = _path_without_query(path).lower().replace("\\", "/")
    return lower.endswith("/bd_customer/getcustomer")

def _is_blank_material_batchquery_filter_value(value: Any) -> bool:
    """勾选未填的空串/空数组不当作有效筛选，否则苍穹常直接返回 0 行。"""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return len(value) == 0 or all(_is_blank_material_batchquery_filter_value(x) for x in value)
    return False


def _strip_org_filters_from_material_batchquery_body(body: Dict[str, Any]) -> Dict[str, Any]:
    """物料 batchQuery：移除 createorg 与空筛选项；管理组织 org_number 非空时保留。"""
    if not isinstance(body, dict):
        return body
    out = dict(body)
    changed = False
    for key in list(out.keys()):
        if _is_createorg_filter_key(key):
            out.pop(key, None)
            changed = True
    data = out.get("data")
    if isinstance(data, dict) and data:
        cleaned = {
            k: v
            for k, v in data.items()
            if not _is_createorg_filter_key(k) and not _is_blank_material_batchquery_filter_value(v)
        }
        if cleaned != data:
            out["data"] = cleaned
            changed = True
    return out if changed else body


def _strip_createorg_from_group_master_query_payload(
    params: Dict[str, Any],
    body: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """供应商/客户 query：移除 createorg 筛选，避免误当管理组织范围。"""
    params_out = dict(params)
    params_out.pop("createorg_number", None)
    params_out.pop("createorgnumber", None)
    if not isinstance(body, dict):
        return params_out, body
    data = body.get("data")
    if not isinstance(data, dict) or not data:
        return params_out, body
    if not any(_is_createorg_filter_key(k) for k in data):
        return params_out, body
    cleaned = {k: v for k, v in data.items() if not _is_createorg_filter_key(k)}
    body_out = dict(body)
    body_out["data"] = cleaned
    return params_out, body_out


_ORG_FIELD_KEYS = frozenset(
    {
        "org",
        "createorg_number",
        "createorgnumber",
        "create_org_number",
        "org_number",
        "orgnumber",
        "bizorg_number",
        "bizorgnumber",
        "entrysettleorg_number",
        "entrysettleorgnumber",
    }
)


def _is_org_field_key(key: Any) -> bool:
    text = str(key or "").strip().lower().replace("-", "_")
    if text in _ORG_FIELD_KEYS:
        return True
    return text.endswith("org_number") or text.endswith("orgnumber")


def _is_createorg_filter_key(key: Any) -> bool:
    """batchQuery data 内「创建组织」筛选项（与 org/管理组织 不同）。"""
    text = str(key or "").strip().lower().replace("-", "_")
    if text in {"createorg_number", "createorgnumber", "create_org_number", "createorg"}:
        return True
    return text.startswith("createorg_")


def _is_org_placeholder(value: Any) -> bool:
    """空值、尖括号占位、历史示例 BU-00000、出站 REPLACE_ORG 均视为待连接器填充。"""
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    if text.startswith("<") and text.endswith(">"):
        return True
    upper = text.upper()
    if upper in {"BU-00000", "REPLACE_ORG"}:
        return True
    if upper.startswith("REPLACE_"):
        return True
    return False


def apply_connector_org_to_payload(payload: Any, org: str) -> Any:
    """把连接器组织写入请求体/参数中所有组织字段；无连接器组织则原样返回。"""
    org_text = str(org or "").strip()
    if not org_text:
        return payload

    def _walk(node: Any, *, parent_is_org_field: bool = False) -> Any:
        if isinstance(node, dict):
            out: Dict[str, Any] = {}
            for key, value in node.items():
                is_org = _is_org_field_key(key)
                if is_org:
                    if isinstance(value, list):
                        out[key] = [org_text]
                    else:
                        out[key] = org_text
                else:
                    out[key] = _walk(value, parent_is_org_field=False)
            return out
        if isinstance(node, list):
            if parent_is_org_field:
                return [org_text]
            return [_walk(item, parent_is_org_field=False) for item in node]
        if parent_is_org_field or _is_org_placeholder(node):
            # 仅在组织字段路径上替换占位；普通字符串里的 BU-00000 不当组织
            if parent_is_org_field:
                return org_text
        return node

    return _walk(payload, parent_is_org_field=False)


def _rewrite_warehouse_list_url(url: str) -> str:
    """仓库列表统一走 sbd/bd_warehouse/getList。basedata 路径网关 2530。"""
    raw = _path_without_query(url)
    lower = raw.lower().replace("\\", "/")
    if not _is_warehouse_path(raw):
        return url
    if "/sbd/bd_warehouse/getlist" in lower:
        return url
    is_list = "batchquery" in lower or lower.rstrip("/").endswith("/query")
    if not is_list:
        return url
    m = re.match(r"(?i)^(https?://[^/]+)", raw)
    if m:
        return f"{m.group(1).rstrip('/')}/{WAREHOUSE_LIST_ENDPOINT}"
    return WAREHOUSE_LIST_ENDPOINT


def _is_inventory_balance_query_path(url: str) -> bool:
    """库存余额/即时库存：getInventoryAvbQty、getInventoryDetail、getInventorySum 等。"""
    lower = _path_without_query(url).lower()
    return (
        "getinventory" in lower
        or "getinvacc" in lower
        or "/imrealbal" in lower
    )


def prepare_kingdee_cosmic_outbound(
    cfg: Optional[Dict[str, Any]],
    url: str,
    method: str,
    params: Optional[Dict[str, Any]],
    body: Optional[Dict[str, Any]],
) -> Tuple[str, str, Dict[str, Any], Dict[str, Any]]:
    """
    仓库列表走 batchQuery，并把连接器组织编码写入 createorg_number。
    GET /bd_warehouse/query 且未指定 number 时改为 POST batchQuery。
    """
    params_out: Dict[str, Any] = dict(params or {})
    body_out: Dict[str, Any] = dict(body) if isinstance(body, dict) else {}
    method_out = str(method or "POST").upper() or "POST"
    url_out = str(url or "")
    lower_path = _path_without_query(url_out).lower()
    if "oauth2/gettoken" in lower_path:
        return method_out, url_out, params_out, body_out

    number = str(params_out.get("number") or "").strip()
    if _is_warehouse_path(url_out) and _is_basedata_single_query(url_out) and not number:
        url_out = re.sub(r"(?i)/query/?$", "/batchQuery", _path_without_query(url_out))
        method_out = "POST"
        params_out.pop("number", None)
    body_out = ensure_kingdee_v2_request_body(url_out, body_out)
    org = resolve_kingdee_cosmic_createorg_number(cfg)
    lower = _path_without_query(url_out).lower()
    data_obj = body_out.get("data") if isinstance(body_out.get("data"), dict) else {}
    already = str(params_out.get("createorg_number") or "").strip() or str(
        data_obj.get("createorg_number") or data_obj.get("createOrgNumber") or ""
    ).strip()
    createorg = already or org or ("WANG" if _is_warehouse_path(url_out) else "")

    if _is_warehouse_path(url_out) and "batchquery" in lower:
        data = dict(data_obj)
        data["createorg_number"] = createorg
        body_out["data"] = data

    # 仓位 getList 契约必含 data（可为空对象）。生产库接口体常只有 pageNo/pageSize；
    # 仓库因注入 createorg 会顺带补上 data，仓位无组织字段时须在此保证，且不依赖连接器组织。
    if _is_location_path(url_out) and "getlist" in lower:
        data = body_out.get("data") if isinstance(body_out.get("data"), dict) else {}
        body_out["data"] = dict(data)
        method_out = "POST"

    if org:
        params_out = apply_connector_org_to_payload(params_out, org)
        body_out = apply_connector_org_to_payload(body_out, org)
        # 仓库列表 / 库存查询即使 body 未写组织字段，也必须带上连接器组织
        if _is_warehouse_path(url_out) and "getlist" in lower:
            data = body_out.get("data") if isinstance(body_out.get("data"), dict) else {}
            data = dict(data)
            data["createorg_number"] = org
            body_out["data"] = data
            method_out = "POST"
        elif _is_inventory_balance_query_path(url_out):
            inv_params = body_out.get("params") if isinstance(body_out.get("params"), dict) else {}
            inv_params = dict(inv_params)
            inv_params["org"] = org
            body_out["params"] = inv_params
            method_out = "POST"
        elif _is_supplier_getsupplier_path(url_out) and org.upper() != "BU-00000":
            data = body_out.get("data") if isinstance(body_out.get("data"), dict) else {}
            data = dict(data)
            data["org_number"] = [org]
            body_out["data"] = data
            method_out = "POST"
        elif _is_customer_getcustomer_path(url_out) and org.upper() != "BU-00000":
            data = body_out.get("data") if isinstance(body_out.get("data"), dict) else {}
            data = dict(data)
            data["org_number"] = [org]
            body_out["data"] = data
            method_out = "POST"
        elif _is_basedata_single_query(url_out) and not _is_group_created_master_query_path(
            url_out
        ):
            params_out["createorg_number"] = org

    if "batchquery" in lower:
        method_out = "POST"
        # sys/query 改写为 batchQuery 时，把 select 落到请求体，避免仍拉全量返回列
        select_raw = params_out.get("select")
        if select_raw in (None, ""):
            select_raw = body_out.get("select")
        select_text = str(select_raw or "").strip()
        if select_text:
            body_out["select"] = select_text
            params_out["select"] = select_text

    if _is_material_batchquery_path(url_out):
        body_out = _strip_org_filters_from_material_batchquery_body(body_out)
        # 查询参数里若残留 createorg，同样剥离（历史接口模板 / 连接器误写）
        for key in list(params_out.keys()):
            if _is_createorg_filter_key(key):
                params_out.pop(key, None)

    return method_out, url_out, params_out, body_out


def _select_output_column(key: str) -> str:
    """点号 select 输出为下划线列名，便于前端映射（group.number → group_number）。"""
    raw = str(key or "").strip()
    return raw.replace(".", "_") if raw else raw


def _dig_nested_path(row: Dict[str, Any], dotted: str) -> tuple[bool, Any]:
    """按 a.b.c 深入嵌套对象；返回 (是否命中路径, 值)。"""
    cursor: Any = row
    for part in str(dotted or "").split("."):
        token = part.strip()
        if not token or not isinstance(cursor, dict):
            return False, None
        lower_map = {str(k).lower(): k for k in cursor.keys()}
        actual = lower_map.get(token.lower())
        if actual is None:
            return False, None
        cursor = cursor.get(actual)
    return True, cursor


def project_row_by_select(row: Any, select_keys: List[str]) -> Any:
    """
    按 select 保留行字段。

    - 平铺名：number、baseunit_number
    - 点号路径：baseunit.number / group.number 从嵌套对象取值，输出为 baseunit_number / group_number
    - 禁止用末段裸名（如 number）冒充 baseunit.number，否则会丢掉分组/单位嵌套列
    """
    if not isinstance(row, dict) or not select_keys:
        return row
    lower_map = {str(k).lower(): k for k in row.keys()}
    projected: Dict[str, Any] = {}
    for key in select_keys:
        raw = str(key or "").strip()
        if not raw:
            continue
        out_col = _select_output_column(raw)
        value: Any = None
        found = False

        for variant in (raw, raw.replace(".", "_")):
            actual = lower_map.get(variant.lower())
            if actual is not None:
                value = row.get(actual)
                found = True
                break

        if not found and "." in raw:
            hit, nested = _dig_nested_path(row, raw)
            if hit:
                value = nested
                found = True

        if found and out_col not in projected:
            projected[out_col] = value
    return projected if projected else row


def collapse_material_rows_to_unique_units(rows: List[Any]) -> List[Dict[str, Any]]:
    """
    物料行 → 按基础单位编码去重。
    单位同步源常是物料 batchQuery；同一 kg 会在每条物料上重复出现。
    """
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = (
            row.get("baseunit_number")
            or row.get("baseunit.number")
            or row.get("measureunitid_number")
            or row.get("measureunitid.number")
        )
        name = (
            row.get("baseunit_name")
            or row.get("baseunit.name")
            or row.get("measureunitid_name")
            or row.get("measureunitid.name")
            or code
        )
        code_s = str(code or "").strip()
        name_s = str(name or "").strip() or code_s
        if not code_s:
            continue
        key = code_s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "baseunit_number": code_s,
                "baseunit_name": name_s,
                "number": code_s,
                "name": name_s,
                "code": code_s,
            }
        )
    return out


def project_response_by_select(body: Any, select_text: str) -> Any:
    """
    对苍穹查询响应按 select 裁剪行对象字段。
    网关常忽略 select 仍回全量时，测试预览与下游映射只见需要的列。

    注意：此处**禁止**按单位去重。同步分页用「本页行数 < pageSize」判断是否结束；
    若在 test_api 内先把 100 条物料收成 1 个单位，分页会误停，单位只剩一两个。
    去重放在单位同步写入前 / 前端预览展示层。
    """
    keys = [part.strip() for part in str(select_text or "").split(",") if part.strip()]
    if not keys:
        return body

    def project_rows(rows: Any) -> Any:
        if not isinstance(rows, list):
            return rows
        return [
            project_row_by_select(item, keys) if isinstance(item, dict) else item
            for item in rows
        ]

    if isinstance(body, list):
        return project_rows(body)
    if not isinstance(body, dict):
        return body

    out = dict(body)
    for nest_key in ("data", "items", "rows", "records", "result", "list", "Results"):
        nested = out.get(nest_key)
        if isinstance(nested, list) and nested and isinstance(nested[0], dict):
            out[nest_key] = project_rows(nested)
            return out
        if isinstance(nested, dict):
            for inner_key in ("rows", "items", "records", "list", "data"):
                inner = nested.get(inner_key)
                if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                    nested_out = dict(nested)
                    nested_out[inner_key] = project_rows(inner)
                    out[nest_key] = nested_out
                    return out
    return out


def collapse_response_rows_to_unique_units(body: Any) -> Any:
    """仅用于接口测试展示：把物料行收成唯一单位（不参与同步分页）。"""
    def collapse_list(rows: Any) -> Any:
        if not isinstance(rows, list):
            return rows
        collapsed = collapse_material_rows_to_unique_units(rows)
        return collapsed if collapsed else rows

    if isinstance(body, list):
        return collapse_list(body)
    if not isinstance(body, dict):
        return body
    out = dict(body)
    for nest_key in ("data", "items", "rows", "records", "result", "list", "Results"):
        nested = out.get(nest_key)
        if isinstance(nested, list) and nested and isinstance(nested[0], dict):
            out[nest_key] = collapse_list(nested)
            return out
        if isinstance(nested, dict):
            for inner_key in ("rows", "items", "records", "list", "data"):
                inner = nested.get(inner_key)
                if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                    nested_out = dict(nested)
                    nested_out[inner_key] = collapse_list(inner)
                    out[nest_key] = nested_out
                    return out
    return out


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
