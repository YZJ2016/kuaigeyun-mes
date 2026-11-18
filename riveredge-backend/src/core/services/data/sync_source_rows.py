"""将数据接口响应体规范化为同步可用的行字典列表。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.services.data.sync_nested_expand import expand_nested_detail_rows


def _collect_kingdee_error_messages(payload: Any) -> List[str]:
    messages: List[str] = []
    if isinstance(payload, dict):
        result = payload.get("Result") if isinstance(payload.get("Result"), dict) else payload
        if not isinstance(result, dict):
            return messages
        status = result.get("ResponseStatus") or result.get("responseStatus")
        if not isinstance(status, dict):
            return messages
        is_success = status.get("IsSuccess")
        if is_success is None:
            is_success = status.get("isSuccess")
        errors = status.get("Errors") or status.get("errors") or []
        if is_success is False or (isinstance(errors, list) and errors):
            if isinstance(errors, list):
                for item in errors:
                    if isinstance(item, dict):
                        msg = item.get("Message") or item.get("message") or item.get("FieldName")
                        if msg:
                            messages.append(str(msg))
                    elif item:
                        messages.append(str(item))
            if not messages:
                messages.append(str(status.get("MsgCode") or status.get("ErrorCode") or "金蝶查询失败"))
    return messages


def _raise_if_cosmic_error_payload(body: Any) -> None:
    """苍穹网关失败：status=false 且带 errorCode/data 外壳，禁止当成业务行。"""
    if not isinstance(body, dict):
        return
    if body.get("status") is not False:
        return
    if "errorCode" not in body and "data" not in body:
        return
    msg = body.get("message") or body.get("errorCode") or "苍穹接口返回失败"
    raise ValueError(str(msg))


def _unwrap_kingdee_execute_bill_layers(body: Any) -> Any:
    """ExecuteBillQuery 失败体常包成 [[{Result:...}]]，剥到内层对象再判错。"""
    current = body
    for _ in range(4):
        if isinstance(current, list) and len(current) == 1:
            current = current[0]
            continue
        break
    return current


def _raise_if_kingdee_error_payload(body: Any) -> None:
    """金蝶失败时常见为单条 Result/ResponseStatus 对象；禁止当成业务行跳过。

    物料分组等 ExecuteBillQuery 失败常返回 ``[[{Result:{ResponseStatus:{IsSuccess:false}}}]]``；
    若只认顶层 list[dict]，会把内层 Result 字典 zip 进 FieldKeys，摊成空 FNumber 行，
    物料管理同步表现为「缺少分组编码」，而接口调试仍能看见真实错误文案。
    """
    unwrapped = _unwrap_kingdee_execute_bill_layers(body)
    if isinstance(unwrapped, dict):
        messages = _collect_kingdee_error_messages(unwrapped)
        if messages:
            raise ValueError("；".join(messages))
    if isinstance(body, list) and body:
        first = body[0]
        if isinstance(first, dict):
            messages = _collect_kingdee_error_messages(first)
            if messages:
                raise ValueError("；".join(messages))
        if isinstance(first, list) and first:
            cell = first[0]
            if isinstance(cell, dict):
                messages = _collect_kingdee_error_messages(cell)
                if messages:
                    raise ValueError("；".join(messages))
            if isinstance(cell, str) and (
                "无效" in cell or "失败" in cell or "错误" in cell or "Error" in cell
            ):
                raise ValueError(cell)
    if isinstance(body, dict):
        messages = _collect_kingdee_error_messages(body)
        if messages:
            raise ValueError("；".join(messages))


def _extract_array_from_object(payload: Dict[str, Any], *, depth: int = 0) -> Optional[List[Any]]:
    """从苍穹 batchQuery / 星空 QueryGroupInfo 等嵌套响应中取出行数组。"""
    candidates = (
        "data",
        "items",
        "rows",
        "records",
        "Results",
        "result",
        "Result",
        "list",
        "NeedReturnData",
        "needReturnData",
    )
    for key in candidates:
        value = payload.get(key)
        if isinstance(value, list):
            return value
        # QueryGroupInfo 文档样例里 NeedReturnData 可能是 JSON 字符串
        if isinstance(value, str) and value.strip().startswith(("[", "{")):
            try:
                parsed = json.loads(value)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict) and depth < 2:
                nested = _extract_array_from_object(parsed, depth=depth + 1)
                if nested is not None:
                    return nested
    if depth >= 2:
        return None
    for key in candidates:
        value = payload.get(key)
        if isinstance(value, dict):
            nested = _extract_array_from_object(value, depth=depth + 1)
            if nested is not None:
                return nested
    return None


def _raise_if_flattened_kingdee_error_rows(rows: List[Dict[str, Any]]) -> None:
    """FieldKeys zip 后若仍出现 ResponseStatus/IsSuccess=false，禁止当业务行。"""
    if not rows or len(rows) > 3:
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        success_val = None
        for key, value in row.items():
            compact = str(key or "").lower().replace("_", "")
            if "responsestatus" in compact and "issuccess" in compact:
                success_val = value
                break
            if compact.endswith("issuccess") or compact == "issuccess":
                success_val = value
                break
        if success_val is False or str(success_val).lower() in {"false", "0"}:
            messages = _collect_kingdee_error_messages(row)
            if not messages:
                for key, value in row.items():
                    if value and ("message" in str(key).lower() or "msg" in str(key).lower()):
                        text = str(value).strip()
                        if text and text not in {"-", "--", "None"}:
                            messages.append(text)
            raise ValueError("；".join(messages) if messages else "金蝶查询失败")


def normalize_api_body_to_rows(
    body: Any,
    *,
    column_names: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    rows = _normalize_api_body_to_rows_raw(body, column_names=column_names)
    # 苍穹 BOM 等「表头 + entry[]」在解包外壳后仍须摊成扁平行，供字段映射
    rows = expand_nested_detail_rows(rows)
    _raise_if_flattened_kingdee_error_rows(rows)
    return rows


def _normalize_api_body_to_rows_raw(
    body: Any,
    *,
    column_names: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    if body is None:
        return []
    if isinstance(body, str):
        text = body.strip()
        if not text:
            return []
        try:
            import json

            body = json.loads(text)
        except Exception:
            return [{"value": body}]
    if isinstance(body, dict) and body.get("error"):
        raise ValueError(str(body["error"]))
    _raise_if_kingdee_error_payload(body)
    _raise_if_cosmic_error_payload(body)
    if isinstance(body, list):
        if not body:
            return []
        first = body[0]
        if isinstance(first, list):
            cols = column_names or [f"col_{index}" for index in range(len(first))]
            rows: List[Dict[str, Any]] = []
            for row in body:
                if not isinstance(row, list):
                    continue
                padded = list(row) + [None] * max(0, len(cols) - len(row))
                rows.append(dict(zip(cols, padded[: len(cols)])))
            return rows
        if isinstance(first, dict):
            return [item for item in body if isinstance(item, dict)]
        return [{"value": item} for item in body]
    if isinstance(body, dict):
        nested = _extract_array_from_object(body)
        if nested is not None:
            return _normalize_api_body_to_rows_raw(nested, column_names=column_names)
        return [body]
    return [{"value": body}]