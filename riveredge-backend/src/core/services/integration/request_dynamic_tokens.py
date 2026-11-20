"""请求体/参数中的动态占位符解析（如日期快捷「此刻」→ __NOW__）。"""

from __future__ import annotations

from typing import Any

from core.utils.timezone_utils import now_utc, to_site_timezone

JSON_FIELD_NOW_TOKEN = "__NOW__"


def site_now_datetime_string() -> str:
    """当前站点墙钟 ``YYYY-MM-DD HH:mm:ss``。"""
    return to_site_timezone(now_utc()).strftime("%Y-%m-%d %H:%M:%S")


def _is_now_token(value: str) -> bool:
    text = value.strip()
    if text == JSON_FIELD_NOW_TOKEN:
        return True
    # 兼容误写入的展示文案
    return text in {"此刻（每次调用）", "此刻(每次调用)", "此刻"}


def omit_empty_request_values(value: Any) -> Any:
    """
    发送前去掉空字符串 / null（保留 0、False）。
    苍穹 DateTime 收到 ``\"\"`` 会 NumberFormatException。

    禁止删空对象：仓位/仓库 getList 契约要求顶层 ``data``（可为空 ``{}``），
    删掉会报「请求参数没有 data 数据」。与前端 ``omitEmptyJsonValues`` 一致。
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            next_item = omit_empty_request_values(item)
            if next_item is None:
                continue
            if isinstance(next_item, str) and next_item.strip() == "":
                continue
            out[key] = next_item
        return out
    if isinstance(value, list):
        return [
            item
            for item in (omit_empty_request_values(v) for v in value)
            if item is not None and not (isinstance(item, str) and item.strip() == "")
        ]
    return value


def resolve_request_dynamic_tokens(value: Any, *, now_text: str | None = None) -> Any:
    """
    递归替换请求 JSON 中的动态占位符，并去掉空字符串 / null。

    - ``__NOW__`` → 站点当前墙钟（每次调用重新解析）
    - 空对象 ``{}``（如 getList 的 data）必须保留
    """
    resolved_now = now_text if now_text is not None else site_now_datetime_string()
    if isinstance(value, dict):
        resolved = {
            key: resolve_request_dynamic_tokens(item, now_text=resolved_now)
            for key, item in value.items()
        }
        return omit_empty_request_values(resolved)
    if isinstance(value, list):
        resolved_list = [
            resolve_request_dynamic_tokens(item, now_text=resolved_now) for item in value
        ]
        return omit_empty_request_values(resolved_list)
    if isinstance(value, str) and _is_now_token(value):
        return resolved_now
    return value
