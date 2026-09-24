"""统一 Chat Completion 入口（core 网关 + site-settings 薄转发）。"""

from __future__ import annotations

import importlib.util
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from fastapi.responses import StreamingResponse
from loguru import logger

from core.ai.deps import AiAuth
from core.ai.runtime_config import AiRuntimeConfig
from infra.exceptions.exceptions import ValidationError


def _normalize_user_chat_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = item.get("content")
        if isinstance(content, str):
            text = content.strip()
        elif content is None:
            text = ""
        else:
            text = str(content).strip()
        if not text:
            continue
        if role in {"ai", "assistant"}:
            role = "assistant"
        elif role == "user":
            role = "user"
        elif role == "system":
            role = "system"
        else:
            continue
        normalized.append({"role": role, "content": text})
    return normalized


def _kuaiai_composed() -> bool:
    # KR-D4：单名探测。旧名 apps.kuaiai.services.deepseek_service 已废止，不再探测。
    return importlib.util.find_spec("apps.kuaiai.services.chat_service") is not None


async def create_chat_completion(
    ai_auth: AiAuth,
    messages: List[Dict[str, Any]],
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = 0.7,
    stream: bool = False,
    context: Optional[Dict[str, Any]] = None,
) -> Union[Dict[str, Any], StreamingResponse]:
    if not messages:
        raise ValidationError("messages 不能为空")

    normalized = _normalize_user_chat_messages(messages)
    if not normalized:
        raise ValidationError("messages 不能为空")

    if _kuaiai_composed():
        from apps.kuaiai.services.chat_service import create_chat_completion as kuaiai_chat_completion

        result = await kuaiai_chat_completion(
            ai_auth.tenant_id,
            normalized,
            model=model,
            temperature=temperature,
            stream=stream,
            user=ai_auth.user,
            is_infra_admin=ai_auth.auth.is_infra_admin,
            is_tenant_admin=ai_auth.auth.is_tenant_admin,
            context=context,
        )
        if isinstance(result, StreamingResponse):
            return result
        if hasattr(result, "__aiter__"):
            return StreamingResponse(result, media_type="text/event-stream")
        return result

    # KR-G0 兜底分支（find_spec 未命中 kuaiai）：出站改走
    # core/ai/runtime/model_factory（目录行优先 → IntegrationConfig 兜底），
    # 退役 CompletionService / AgentRunner。
    from core.ai.runtime.memory import dicts_to_lc_messages, message_text
    from core.ai.runtime.model_factory import build_chat_model

    config = await AiRuntimeConfig.load(ai_auth.tenant_id)
    if stream and not config.stream_enabled:
        raise ValidationError("站点未启用流式对话")

    chat = await build_chat_model(ai_auth.tenant_id)
    # 兜底路径忽略客户端 model 覆盖（路径 A 走目录白名单，这里直绑任意值
    # 语义不一致）；模型名以目录行/IntegrationConfig 配置为准
    model_name = chat.model_name
    bound = chat.bind(
        temperature=temperature if temperature is not None else 0.7,
    )
    lc_messages = dicts_to_lc_messages(normalized)

    if stream:
        from core.ai.runtime.sse_adapter import chat_to_openai_sse
        from core.services.realtime.ai_stream_bridge import wrap_ai_sse_stream

        stream_iter = chat_to_openai_sse(bound, lc_messages, model_name=model_name)
        session_id = None
        if isinstance(context, dict):
            raw_session = context.get("session_id")
            if raw_session is not None:
                session_id = str(raw_session)
        wrapped = wrap_ai_sse_stream(
            stream_iter,
            tenant_id=ai_auth.tenant_id,
            user_id=ai_auth.user.id,
            session_id=session_id,
        )
        return StreamingResponse(wrapped, media_type="text/event-stream")

    try:
        response = await bound.ainvoke(lc_messages)
    except Exception as exc:
        # KR-I5：仅记录异常类型，不落 base_url/key
        logger.error(
            "AI 兜底对话失败 tenant_id={} error_type={}",
            ai_auth.tenant_id,
            type(exc).__name__,
        )
        raise ValidationError("AI 对话调用失败，请稍后重试") from exc

    usage_meta = getattr(response, "usage_metadata", None) or {}
    return {
        "id": getattr(response, "id", None) or "chatcmpl-kuaiai",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": message_text(response)},
                "finish_reason": (
                    (getattr(response, "response_metadata", None) or {}).get(
                        "finish_reason"
                    )
                    or "stop"
                ),
            }
        ],
        "usage": {
            "prompt_tokens": usage_meta.get("input_tokens"),
            "completion_tokens": usage_meta.get("output_tokens"),
            "total_tokens": usage_meta.get("total_tokens"),
        },
    }
