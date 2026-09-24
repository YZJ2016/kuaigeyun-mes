"""视觉 / OCR 出站（KR-D5：一律经 model_factory）。

目录 ``model_type=vision`` 行优先，无目录行走 ``AiRuntimeConfig`` 的
OCR 组兜底（仍是 OpenAI 兼容 ``/chat/completions``，多模态 content block）。
出站经 ``model_factory``；复用 ``deepseek_vision_client`` 的纯函数工具
（mime 猜测 / deepseek-ocr prompt 约定 / content 归一），不直发 HTTP。
"""

from __future__ import annotations

from typing import Optional

from langchain_core.messages import HumanMessage
from loguru import logger

from core.ai.runtime.model_factory import build_vision_model
from core.utils.deepseek_vision_client import (
    DEFAULT_IMAGE_TEXT_EXTRACT_PROMPT,
    content_to_text,
    is_deepseek_ocr_model,
)
from infra.exceptions.exceptions import ValidationError

_VALID_IMAGE_DETAIL = ("low", "high", "auto")


async def extract_text_from_image(
    *,
    tenant_id: int,
    mime: str,
    b64: str,
    prompt: Optional[str] = None,
    max_tokens: int = 4096,
    image_detail: str = "high",
    model_id: Optional[int] = None,
) -> str:
    """图片 → OCR 文本（视觉模型目录行 / OCR 组兜底，OpenAI 兼容多模态）。"""
    chat = await build_vision_model(tenant_id, model_id)

    text_prompt = prompt or DEFAULT_IMAGE_TEXT_EXTRACT_PROMPT
    # DeepSeek-OCR 类端点要求 <image> 前缀（prompt 约定，非厂商客户端分支）
    if is_deepseek_ocr_model(chat.model_name):
        text_prompt = f"<image>\n{text_prompt}"

    detail = image_detail if image_detail in _VALID_IMAGE_DETAIL else "high"
    message = HumanMessage(
        content=[
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}", "detail": detail},
            },
            {"type": "text", "text": text_prompt},
        ]
    )
    bound = chat.bind(temperature=0.1, max_tokens=max_tokens)
    try:
        response = await bound.ainvoke([message])
    except Exception as exc:
        # KR-I5：仅记录异常类型，不落 base_url/key
        logger.error(
            "vision OCR 调用失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        raise ValidationError("OCR 视觉识别失败，请检查模型目录或连接器配置") from exc
    text = content_to_text(getattr(response, "content", None))
    if not text:
        raise ValidationError("OCR 未识别到有效文本，请更换更清晰的单据图片")
    return text
