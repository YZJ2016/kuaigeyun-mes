"""OCR / 自然语言 → JSON 结构化草稿（统一 LLM 路径）。"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Type, TypeVar, Union

from loguru import logger
from pydantic import BaseModel

from core.ai.runtime.model_factory import build_chat_model
from core.ai.runtime.vision import extract_text_from_image
from core.utils.deepseek_vision_client import guess_image_mime
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
        # 注意：json_mode 下 dict schema 不参与请求也不做字段校验（仅选 parser）；
        # 要校验过的 pydantic 对象请传 BaseModel 子类。
        schema: Optional[Union[Type[T], Dict[str, Any]]] = None,
    ) -> Union[Dict[str, Any], T]:
        chat = await build_chat_model(tenant_id)
        # json_mode：响应面仍是 response_format=json_object，兼容面最广；
        # 不提供抠 JSON 回退——解析失败即整体失败。
        structured = chat.with_structured_output(schema, method="json_mode")
        bound = structured.bind(temperature=temperature)
        try:
            result = await bound.ainvoke(
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
        # dict/None schema 只保证「是合法 JSON」，不保证是对象；下游一律按 dict 消费，
        # 顶层为数组/标量时按失败关闭，不放任 AttributeError 漏成 500
        if not (isinstance(schema, type) and issubclass(schema, BaseModel)):
            if not isinstance(result, dict):
                logger.error(
                    "{} tenant_id={} non_object_json", error_prefix, tenant_id
                )
                raise ValidationError(error_prefix)
        return result

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
        # include_raw：解析失败不抛穿，先拿到 raw/parsed/parsing_error 再决定归一或失败
        structured = chat.with_structured_output(
            result_type, method="json_mode", include_raw=True
        )
        bound = structured.bind(temperature=0.1)
        try:
            out = await bound.ainvoke(
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
        result = out.get("parsed") if isinstance(out, dict) else out
        if result is None:
            result = cls._salvage_parsed(out, result_type, tenant_id, error_prefix)
        if (
            profile.validate_meaningful
            and source_label == "OCR 文本"
            and not profile.validate_meaningful(result)
        ):
            raise ValidationError(profile.empty_ocr_message)
        return result

    @staticmethod
    def _salvage_parsed(
        out: Any,
        result_type: Type[T],
        tenant_id: int,
        error_prefix: str,
    ) -> T:
        """解析失败的严格归一（非抠 JSON）：raw content 本就是 json_object 响应，
        仅做 json.loads + `items` 归一（None→[]、剔除非 dict 行，沿用旧口径），
        再 model_validate；仍失败则抛 ValidationError。"""
        raw = out.get("raw") if isinstance(out, dict) else None
        content = getattr(raw, "content", None)
        data: Any = None
        if isinstance(content, str) and content.strip():
            try:
                data = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                data = None
        elif isinstance(content, list):
            # 部分端点回 content blocks：拼接 text 块再解析
            text = "".join(
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
            if text.strip():
                try:
                    data = json.loads(text)
                except (json.JSONDecodeError, ValueError):
                    data = None
        if isinstance(data, dict):
            items_raw = data.get("items") or []
            data["items"] = (
                [row for row in items_raw if isinstance(row, dict)]
                if isinstance(items_raw, list)
                else []
            )
            try:
                return result_type.model_validate(data)
            except Exception:
                pass
        logger.error(
            "{} tenant_id={} parse_failed",
            error_prefix,
            tenant_id,
        )
        raise ValidationError(error_prefix)

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
