"""OCR / 自然语言 → JSON 结构化草稿（统一 LLM 路径）。"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Type, TypeVar

from loguru import logger
from pydantic import BaseModel

from core.ai.runtime.memory import message_text
from core.ai.runtime.model_factory import build_chat_model
from core.ai.runtime.vision import extract_text_from_image
from core.utils.deepseek_vision_client import (
    extract_json_object,
    guess_image_mime,
)
from infra.exceptions.exceptions import ValidationError

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class DraftProfile:
    schema_name: str
    system_prompt: str
    json_spec: str
    ocr_user_prefix: str = ""
    validate_meaningful: Optional[Callable[[Any], bool]] = None
    empty_ocr_message: str = "未能从图片中识别出有效信息，请上传更清晰的照片或改用文字描述"


class StructuredDraftService:
    _profiles: Dict[str, DraftProfile] = {}

    @classmethod
    def register_profile(cls, profile: DraftProfile) -> None:
        cls._profiles[profile.schema_name] = profile

    @classmethod
    def get_profile(cls, schema_name: str) -> DraftProfile:
        profile = cls._profiles.get(schema_name)
        if not profile:
            raise ValidationError(f"未知结构化 schema: {schema_name}")
        return profile

    @classmethod
    async def complete_json(
        cls,
        tenant_id: int,
        *,
        system: str,
        user_content: str,
        error_prefix: str,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        chat = await build_chat_model(tenant_id)
        bound = chat.bind(
            response_format={"type": "json_object"},
            temperature=temperature,
        )
        try:
            response = await bound.ainvoke(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ]
            )
        except Exception as exc:
            # KR-I5：仅记录异常类型，不落 base_url/key
            logger.error(
                "{} tenant_id={} error_type={}",
                error_prefix,
                tenant_id,
                type(exc).__name__,
            )
            raise ValidationError(error_prefix) from exc
        return extract_json_object(message_text(response))

    @classmethod
    async def structure_text(
        cls,
        tenant_id: int,
        *,
        schema_name: str,
        source_text: str,
        source_label: str = "文本",
        result_type: Type[T],
        context: Optional[Dict[str, Any]] = None,
    ) -> T:
        profile = cls.get_profile(schema_name)
        user_content = f"根据以下{source_label}，{profile.json_spec}\n\n---\n{source_text}"
        if profile.ocr_user_prefix and source_label == "OCR 文本":
            user_content = f"{profile.ocr_user_prefix}{profile.json_spec}\n\n---\nOCR 文本：\n{source_text}"
        if context is not None:
            user_content = (
                "当前解析草稿（JSON，可在其基础上合并用户补充）：\n"
                f"{json.dumps(context, ensure_ascii=False)}\n\n"
                f"用户说明：\n{source_text}"
            )

        error_prefix = f"{schema_name} 字段结构化失败"
        chat = await build_chat_model(tenant_id)
        bound = chat.bind(
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        try:
            response = await bound.ainvoke(
                [
                    {"role": "system", "content": profile.system_prompt},
                    {"role": "user", "content": user_content},
                ]
            )
        except Exception as exc:
            logger.error(
                "{} tenant_id={} error_type={}",
                error_prefix,
                tenant_id,
                type(exc).__name__,
            )
            raise ValidationError(error_prefix) from exc
        data = extract_json_object(message_text(response))
        items_raw = data.get("items") or []
        if isinstance(items_raw, list):
            data["items"] = [row for row in items_raw if isinstance(row, dict)]
        else:
            data["items"] = []
        result = result_type.model_validate(data)
        if (
            profile.validate_meaningful
            and source_label == "OCR 文本"
            and not profile.validate_meaningful(result)
        ):
            raise ValidationError(profile.empty_ocr_message)
        return result

    @classmethod
    async def structure_from_image(
        cls,
        tenant_id: int,
        *,
        schema_name: str,
        image_bytes: bytes,
        content_type: Optional[str],
        result_type: Type[T],
        ocr_prompt: Optional[str] = None,
    ) -> T:
        if not image_bytes:
            raise ValidationError("请上传图片文件")
        if len(image_bytes) > 12 * 1024 * 1024:
            raise ValidationError("图片大小不能超过 12MB")

        mime = guess_image_mime(image_bytes, content_type)
        if not mime.startswith("image/"):
            raise ValidationError("仅支持图片格式（JPG、PNG、WEBP 等）")

        b64 = base64.b64encode(image_bytes).decode("ascii")
        ocr_text = await extract_text_from_image(
            tenant_id=tenant_id,
            mime=mime,
            b64=b64,
            prompt=ocr_prompt,
        )
        return await cls.structure_text(
            tenant_id,
            schema_name=schema_name,
            source_text=ocr_text,
            source_label="OCR 文本",
            result_type=result_type,
        )
