"""LangChain 流 → OpenAI chunk SSE 线格式（KR-D14，逐字节兼容 deepseekChat.ts）。

主路径：``astream_events(version="v2")`` 取 ``on_chat_model_stream`` →
``choices[].delta.content`` chunk → ``[DONE]``。``on_tool_start/end`` 另发
顶层 ``kuaiai_tool`` 扩展帧（不写入 ``delta.content``）；旧客户端只读
正文时忽略该帧。工具轨迹仍以落库历史为准，扩展帧只供抽屉实时反馈。

兼容分支（KR-D14，**不是**假流式兜底）：流式在产出任何内容且**未发生
任何工具执行**前失败（典型如端点不支持 tool_calls 流式）→ 该轮回退
**非流式补全**再适配成同一 OpenAI chunk 线格式；已产出文本或已出现
``on_tool_start``/``on_tool_end`` 后的失败只写通用错误帧收尾——
``ainvoke`` 整图重跑会让副作用工具（报工/改状态）重复执行。
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger

from core.ai.runtime.memory import message_text

_SSE_DONE = b"data: [DONE]\n\n"
_SUMMARY_LIMIT = 120


def _short_text(value: Any) -> str:
    """工具参数/结果压成单行短摘要，避免把整段 JSON 或密钥推进 SSE。"""
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = message_text(value) if hasattr(value, "content") else ""
        if not text:
            try:
                text = json.dumps(value, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                text = str(value)
    text = " ".join(text.split())
    if len(text) <= _SUMMARY_LIMIT:
        return text
    return text[:_SUMMARY_LIMIT] + "…"


def _tool_notice(event: Dict[str, Any]) -> Dict[str, str]:
    data = event.get("data") or {}
    name = str(event.get("name") or data.get("name") or "tool").strip() or "tool"
    if event.get("event") == "on_tool_start":
        notice = {"phase": "start", "name": name}
        summary = _short_text(data.get("input"))
        if summary:
            notice["args_summary"] = summary
        return notice
    notice = {"phase": "end", "name": name}
    summary = _short_text(data.get("output"))
    if summary:
        notice["result_summary"] = summary
    return notice


def _chunk_payload(model_name: str, delta: Dict[str, Any]) -> bytes:
    chunk = {
        "id": "chatcmpl-kuaiai",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_name,
        "choices": [{"index": 0, "delta": delta}],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8")


def _tool_payload(model_name: str, notice: Dict[str, str]) -> bytes:
    """扩展帧：空 delta，工具反馈放在顶层 kuaiai_tool，不进回答正文。"""
    chunk = {
        "id": "chatcmpl-kuaiai",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_name,
        "kuaiai_tool": notice,
        "choices": [{"index": 0, "delta": {}}],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8")


def _error_payload() -> bytes:
    err = {"error": {"message": "AI 对话调用失败，请稍后重试"}}
    return f"data: {json.dumps(err, ensure_ascii=False)}\n\n".encode("utf-8")


# 工具执行类事件：一旦发生即视为「副作用可能已落」，禁止 ainvoke 整图重跑。
_TOOL_EVENT_NAMES = frozenset({"on_tool_start", "on_tool_end"})


async def _iter_agent_texts(
    agent: Any,
    messages: List[Any],
    config: Optional[Dict[str, Any]],
    tool_events: List[str],
) -> AsyncIterator[tuple]:
    """产出 (\"text\", str) 或 (\"tool\", notice)。工具帧不计入已发出的正文。"""
    async for event in agent.astream_events(
        {"messages": messages}, config=config, version="v2"
    ):
        kind = event.get("event")
        if kind in _TOOL_EVENT_NAMES:
            tool_events.append(kind)
            yield ("tool", _tool_notice(event))
            continue
        if kind != "on_chat_model_stream":
            continue
        chunk = (event.get("data") or {}).get("chunk")
        if chunk is None:
            continue
        text = message_text(chunk)
        if text:
            yield ("text", text)


def _final_message_text(result: Any) -> str:
    """agent.ainvoke 终态 dict（{messages:[...]}）取最后一条文本。"""
    if isinstance(result, dict):
        for msg in reversed(result.get("messages") or []):
            text = message_text(msg)
            if text:
                return text
        return ""
    return message_text(result)


async def agent_to_openai_sse(
    agent: Any,
    messages: List[Any],
    *,
    model_name: str,
    config: Dict[str, Any],
) -> AsyncIterator[bytes]:
    """agent ``astream_events`` 真流式 → OpenAI chunk 线格式。"""
    emitted = False
    first = True
    tool_events: List[str] = []
    try:
        async for kind, payload in _iter_agent_texts(
            agent, messages, config, tool_events
        ):
            if kind == "tool":
                yield _tool_payload(model_name, payload)
                continue
            emitted = True
            delta: Dict[str, Any] = {"content": payload}
            if first:
                delta["role"] = "assistant"
                first = False
            yield _chunk_payload(model_name, delta)
    except Exception as exc:
        # KR-I5：仅记录异常类型，不落 base_url/key/参数
        logger.error(
            "AI agent 流式失败 model={} error_type={}",
            model_name,
            type(exc).__name__,
        )
        # 已产出文本或已发生任何工具执行时，禁止 ainvoke 整图重跑
        # （副作用工具如报工/改状态会重复执行），直接错误帧收尾。
        if emitted or tool_events:
            yield _error_payload()
            yield _SSE_DONE
            return
        # KR-D14 兼容分支：仅「首个模型调用即失败、零工具执行」时
        # 回退非流式补全，再适配同一 OpenAI chunk 线格式
        try:
            result = await agent.ainvoke({"messages": messages}, config=config)
            text = _final_message_text(result)
        except Exception:
            yield _error_payload()
            yield _SSE_DONE
            return
        if text:
            yield _chunk_payload(
                model_name, {"role": "assistant", "content": text}
            )
    yield _SSE_DONE


async def chat_to_openai_sse(
    model: Any,
    messages: List[Any],
    *,
    model_name: str,
) -> AsyncIterator[bytes]:
    """裸 ChatOpenAI ``astream`` → 同一 OpenAI chunk 线格式（无 tools 兜底路径）。"""
    emitted = False
    first = True
    try:
        async for chunk in model.astream(messages):
            text = message_text(chunk)
            if not text:
                continue
            emitted = True
            delta = {"content": text}
            if first:
                delta["role"] = "assistant"
                first = False
            yield _chunk_payload(model_name, delta)
    except Exception as exc:
        logger.error(
            "AI 流式对话失败 model={} error_type={}",
            model_name,
            type(exc).__name__,
        )
        if emitted:
            yield _error_payload()
            yield _SSE_DONE
            return
        # KR-D14 兼容分支：非流式补全再适配同一 OpenAI chunk 线格式
        try:
            response = await model.ainvoke(messages)
            text = message_text(response)
        except Exception:
            yield _error_payload()
            yield _SSE_DONE
            return
        if text:
            yield _chunk_payload(
                model_name, {"role": "assistant", "content": text}
            )
    yield _SSE_DONE
