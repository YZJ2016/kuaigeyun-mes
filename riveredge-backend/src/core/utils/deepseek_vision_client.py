"""
DeepSeek / OpenAI 兼容视觉 OCR 辅助函数

历史直发 HTTP（``post_chat_completions`` / ``extract_text_from_image``）已退役：
出站一律经 ``core.ai.runtime.model_factory`` / ``runtime.vision``。
本模块仅保留纯函数工具与 IntegrationConfig OCR 组读取
（``get_deepseek_runtime_config``），供兜底与 content/mime 归一复用。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from core.utils.integration_settings import (
    DEEPSEEK_DEFAULT_BASE_URL,
    DEEPSEEK_DEFAULT_MODEL,
    is_deepseek_ocr_endpoint_configured,
    resolve_active_llm_integration,
)
from infra.exceptions.exceptions import ValidationError

OCR_NOT_CONFIGURED_MSG = (
    "DeepSeek 对话 API 不支持图片输入。"
    "请在系统配置 → 应用连接器中配置 OCR 视觉端点（OCR Base URL 与 OCR 模型），"
    "例如硅基流动 https://api.siliconflow.cn/v1 + deepseek-ai/DeepSeek-OCR。"
)

DEFAULT_IMAGE_TEXT_EXTRACT_PROMPT = (
    "请完整识别这张单据图片中的全部文字、数字与表格内容，"
    "按从上到下、从左到右的阅读顺序输出，保留行列结构，不要总结或省略。"
)


def extract_json_object(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValidationError("模型未返回有效内容")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start : end + 1])
            except json.JSONDecodeError as inner:
                raise ValidationError("无法解析 OCR 结果 JSON") from inner
        else:
            raise ValidationError("无法解析 OCR 结果 JSON") from exc
    if not isinstance(data, dict):
        raise ValidationError("OCR 结果格式无效")
    return data


def content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str) and part.strip():
                parts.append(part.strip())
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()
    return str(content).strip()


def guess_image_mime(image_bytes: bytes, content_type: Optional[str] = None) -> str:
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime.startswith("image/"):
        return mime
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"GIF"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and len(image_bytes) >= 12 and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return "image/jpeg"


def is_deepseek_ocr_model(model: Optional[str]) -> bool:
    return "deepseek-ocr" in str(model or "").lower()


async def get_deepseek_runtime_config(tenant_id: int) -> Dict[str, Any]:
    active = await resolve_active_llm_integration(tenant_id)
    if not active.get("enabled"):
        raise ValidationError("AI 连接器未启用，请在应用连接器中启用并填写 API Key，并在 KU-AI → 模型设置中选用")
    api_key = active.get("api_key")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValidationError("未配置 AI API Key，无法使用对话或 OCR")

    chat_base_url = (active.get("base_url") or DEEPSEEK_DEFAULT_BASE_URL).strip().rstrip("/")
    chat_model = str(active.get("model") or DEEPSEEK_DEFAULT_MODEL).strip()

    ocr_base_raw = active.get("ocr_base_url") or active.get("vision_base_url")
    ocr_model_raw = active.get("ocr_model") or active.get("vision_model")
    ocr_base_url = str(ocr_base_raw).strip().rstrip("/") if ocr_base_raw else ""
    ocr_model = str(ocr_model_raw).strip() if ocr_model_raw else ""

    ocr_api_key_raw = active.get("ocr_api_key")
    ocr_api_key = (
        ocr_api_key_raw.strip()
        if isinstance(ocr_api_key_raw, str) and ocr_api_key_raw.strip()
        else api_key.strip()
    )

    return {
        "chat_api_key": api_key.strip(),
        "chat_base_url": chat_base_url,
        "chat_model": chat_model,
        "ocr_base_url": ocr_base_url or None,
        "ocr_model": ocr_model or None,
        "ocr_api_key": ocr_api_key,
        "ocr_configured": is_deepseek_ocr_endpoint_configured(active),
    }
