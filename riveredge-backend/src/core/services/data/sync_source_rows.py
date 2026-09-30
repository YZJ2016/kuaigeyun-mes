"""将数据接口响应体规范化为同步可用的行字典列表。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


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


def _raise_if_kingdee_error_payload(body: Any) -> None:
    """金蝶失败时常见为单条 Result/ResponseStatus 对象；禁止当成业务行跳过。"""
    if isinstance(body, list) and body:
        first = body[0]
        if isinstance(first, dict):
            messages = _collect_kingdee_error_messages(first)
            if messages:
                raise ValueError("；".join(messages))
        if isinstance(first, list) and first:
            cell = first[0]
            if isinstance(cell, str) and (
                "无效" in cell or "失败" in cell or "错误" in cell or "Error" in cell
            ):
                raise ValueError(cell)
    if isinstance(body, dict):
        messages = _collect_kingdee_error_messages(body)
        if messages:
            raise ValueError("；".join(messages))


def _extract_array_from_object(payload: Dict[str, Any], *, depth: int = 0) -> Optional[List[Any]]:
    """从苍穹 batchQuery 等嵌套响应中取出行数组（对齐接口测试预览 extractArrayFromObject）。"""
    candidates = ("data", "items", "rows", "records", "Results", "result", "list")
    for key in candidates:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    if depth >= 2:
        return None
    for key in candidates:
        value = payload.get(key)
        if isinstance(value, dict):
            nested = _extract_array_from_object(value, depth=depth + 1)
            if nested is not None:
                return nested
    return None


def normalize_api_body_to_rows(
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
            return normalize_api_body_to_rows(nested, column_names=column_names)
        return [body]
    return [{"value": body}]
