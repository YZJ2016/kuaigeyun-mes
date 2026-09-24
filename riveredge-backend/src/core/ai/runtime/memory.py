"""消息表回放 → LangChain 消息（KR-D6/D7，设计 §8 回放规则）。

消息表 ``tool_calls`` 列存 OpenAI 线格式
``[{id, type, function:{name, arguments}}]``；进 ``AIMessage(tool_calls=)``
前必须经 ``normalize_tool_calls`` 转 LangChain 形态 ``{name, args, id}``
（LangChain 1.x pydantic 校验，直接喂列原值会校验失败）。

``to_lc_messages`` 对 rows 鸭子类型（role/content/tool_calls/tool_call_id/
tool_name），不 import apps 层模型；也容忍 dict 行。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)


def normalize_tool_calls(raw: Any) -> List[Dict[str, Any]]:
    """tool_calls 归一为 LangChain 形态 [{name, args, id, type}]。

    OpenAI 线格式条目转 {name, args, id}；已是 LangChain 形态（含 name 键）
    的条目原样透传以兼容脏数据；arguments JSON 解析失败按空 args 处理
    （回放不应因单条脏数据整体失败）。
    """
    out: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for call in raw:
        if not isinstance(call, dict):
            continue
        fn = call.get("function")
        if isinstance(fn, dict):
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (ValueError, TypeError):
                    args = {}
            out.append(
                {
                    "name": fn.get("name") or "",
                    "args": args if isinstance(args, dict) else {},
                    "id": call.get("id"),
                    "type": "tool_call",
                }
            )
        elif call.get("name"):
            out.append(dict(call))
    return out


def _row_get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def to_lc_messages(
    rows: List[Any], *, limit: Optional[int] = None
) -> List[BaseMessage]:
    """消息表回放（唯一历史来源）。

    规则（§8）：
    - role=="user"      → HumanMessage(content)
    - role=="assistant" → AIMessage(content or "", tool_calls=normalize(...))
    - role=="tool"      → ToolMessage(content, tool_call_id=..., name=...)

    ``limit``：只取尾部最近 N 条（窗口截断）。
    """
    if limit is not None and limit > 0:
        rows = rows[-limit:]
    out: List[BaseMessage] = []
    for row in rows:
        role = _row_get(row, "role")
        content = _row_get(row, "content") or ""
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(
                AIMessage(
                    content=content,
                    tool_calls=normalize_tool_calls(_row_get(row, "tool_calls")),
                )
            )
        elif role == "tool":
            out.append(
                ToolMessage(
                    content=content,
                    tool_call_id=str(_row_get(row, "tool_call_id") or ""),
                    name=_row_get(row, "tool_name") or None,
                )
            )
    return out


def dicts_to_lc_messages(messages: List[Dict[str, Any]]) -> List[BaseMessage]:
    """请求消息 dict（OpenAI 线格式）→ LangChain 消息（无会话纯转发路径）。"""
    out: List[BaseMessage] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = str(item.get("content") or "")
        if role == "system":
            out.append(SystemMessage(content=content))
        elif role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(
                AIMessage(
                    content=content,
                    tool_calls=normalize_tool_calls(item.get("tool_calls")),
                )
            )
        elif role == "tool":
            out.append(
                ToolMessage(
                    content=content,
                    tool_call_id=str(item.get("tool_call_id") or ""),
                    name=item.get("name"),
                )
            )
    return out


def lc_tool_calls_to_openai(calls: Any) -> List[Dict[str, Any]]:
    """``normalize_tool_calls`` 的反向转换：LangChain 形态 → OpenAI 线格式。

    ``{name, args, id, type}`` → ``{id, type:"function", function:{name,
    arguments}}``，``arguments`` 序列化为 JSON 字符串（消息表 ``tool_calls``
    列与请求体均存该线格式）。已是线格式（含 ``function`` 键）的条目原样
    透传以兼容脏数据；``args`` 为字符串时视为已序列化原文透传。
    """
    out: List[Dict[str, Any]] = []
    if not isinstance(calls, list):
        return out
    for call in calls:
        if not isinstance(call, dict):
            continue
        fn = call.get("function")
        if isinstance(fn, dict):
            out.append(dict(call))
            continue
        name = call.get("name")
        if not name:
            continue
        args = call.get("args")
        if not isinstance(args, str):
            args = json.dumps(args if isinstance(args, (dict, list)) else {}, ensure_ascii=False)
        out.append(
            {
                "id": call.get("id"),
                "type": "function",
                "function": {"name": name, "arguments": args},
            }
        )
    return out


def message_text(message: Any) -> str:
    """LangChain 消息/Chunk content 兼容 str 与 content-block 列表。"""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return str(content or "")
