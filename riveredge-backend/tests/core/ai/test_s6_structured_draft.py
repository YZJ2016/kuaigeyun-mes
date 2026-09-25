"""KU-AI S6 单测：structured_draft 主路径换 with_structured_output(json_mode)。

全部 mock 上游 LLM（with_structured_output 返回伪 Runnable），
不需要真实端点/数据库。
"""

from __future__ import annotations

import inspect
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from core.ai import structured_draft
from core.ai.structured_draft import DraftProfile, StructuredDraftService
from infra.exceptions.exceptions import ValidationError

TENANT = 7

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-image-body"


class _MiniResult(BaseModel):
    name: Optional[str] = None
    note: Optional[str] = None


class _ItemsResult(BaseModel):
    """带 items 列表字段的测试模型（对齐下游 sales/purchase schema 形态）。"""

    items: list = []
    name: Optional[str] = None


def _fake_runnable(result=None, exc=None):
    """伪 Runnable：bind() 返回自身、ainvoke() 返回预设结果/抛预设异常。"""
    runnable = MagicMock(name="structured_runnable")
    runnable.bind = MagicMock(return_value=runnable)
    if exc is not None:
        runnable.ainvoke = AsyncMock(side_effect=exc)
    else:
        runnable.ainvoke = AsyncMock(return_value=result)
    return runnable


def _fake_chat(runnable):
    """伪 ChatOpenAI：with_structured_output 返回伪 Runnable。"""
    chat = MagicMock(name="chat")
    chat.with_structured_output = MagicMock(return_value=runnable)
    return chat


@pytest.fixture
def mini_profile():
    """注册一个测试 DraftProfile，用完移除。"""
    profile = DraftProfile(
        schema_name="test_mini",
        system_prompt="sys prompt",
        json_spec="输出 JSON，字段 name, note",
        validate_meaningful=lambda r: bool((r.name or "").strip()),
        empty_ocr_message="EMPTY_OCR_MSG",
    )
    StructuredDraftService.register_profile(profile)
    yield profile
    StructuredDraftService._profiles.pop("test_mini", None)


# ------------------------------------------------------------- complete_json


@pytest.mark.asyncio
async def test_complete_json_none_schema_returns_dict():
    runnable = _fake_runnable(result={"a": 1, "b": "x"})
    chat = _fake_chat(runnable)
    with patch.object(
        structured_draft, "build_chat_model", AsyncMock(return_value=chat)
    ):
        result = await StructuredDraftService.complete_json(
            TENANT,
            system="s",
            user_content="u",
            error_prefix="ERR_PREFIX",
        )
    assert result == {"a": 1, "b": "x"}
    chat.with_structured_output.assert_called_once_with(None, method="json_mode")
    runnable.bind.assert_called_once_with(temperature=0.2)


@pytest.mark.asyncio
async def test_complete_json_pydantic_schema_returns_instance():
    expected = _MiniResult(name="n1")
    runnable = _fake_runnable(result=expected)
    chat = _fake_chat(runnable)
    with patch.object(
        structured_draft, "build_chat_model", AsyncMock(return_value=chat)
    ):
        result = await StructuredDraftService.complete_json(
            TENANT,
            system="s",
            user_content="u",
            error_prefix="ERR_PREFIX",
            temperature=0.1,
            schema=_MiniResult,
        )
    assert result is expected
    chat.with_structured_output.assert_called_once_with(
        _MiniResult, method="json_mode"
    )
    runnable.bind.assert_called_once_with(temperature=0.1)


@pytest.mark.asyncio
async def test_complete_json_upstream_error_raises_validation_error():
    runnable = _fake_runnable(exc=RuntimeError("upstream broke"))
    chat = _fake_chat(runnable)
    with patch.object(
        structured_draft, "build_chat_model", AsyncMock(return_value=chat)
    ):
        with pytest.raises(ValidationError, match="ERR_PREFIX"):
            await StructuredDraftService.complete_json(
                TENANT,
                system="s",
                user_content="u",
                error_prefix="ERR_PREFIX",
            )


# ------------------------------------------------------------ structure_text


@pytest.mark.asyncio
async def test_structure_text_returns_result_type_instance(mini_profile):
    expected = _MiniResult(name="ok", note="n")
    runnable = _fake_runnable(result=expected)
    chat = _fake_chat(runnable)
    with patch.object(
        structured_draft, "build_chat_model", AsyncMock(return_value=chat)
    ):
        result = await StructuredDraftService.structure_text(
            TENANT,
            schema_name="test_mini",
            source_text="一段文本",
            result_type=_MiniResult,
        )
    assert result is expected
    chat.with_structured_output.assert_called_once_with(
        _MiniResult, method="json_mode", include_raw=True
    )
    runnable.bind.assert_called_once_with(temperature=0.1)


@pytest.mark.asyncio
async def test_structure_text_empty_ocr_raises_empty_message(mini_profile):
    runnable = _fake_runnable(result=_MiniResult(name=None))
    chat = _fake_chat(runnable)
    with patch.object(
        structured_draft, "build_chat_model", AsyncMock(return_value=chat)
    ):
        with pytest.raises(ValidationError, match="EMPTY_OCR_MSG"):
            await StructuredDraftService.structure_text(
                TENANT,
                schema_name="test_mini",
                source_text="空白",
                source_label="OCR 文本",
                result_type=_MiniResult,
            )


@pytest.mark.asyncio
async def test_structure_text_empty_result_non_ocr_passes(mini_profile):
    """validate_meaningful 只在 source_label=='OCR 文本' 时生效。"""
    expected = _MiniResult(name=None)
    runnable = _fake_runnable(result=expected)
    chat = _fake_chat(runnable)
    with patch.object(
        structured_draft, "build_chat_model", AsyncMock(return_value=chat)
    ):
        result = await StructuredDraftService.structure_text(
            TENANT,
            schema_name="test_mini",
            source_text="空白",
            source_label="文本",
            result_type=_MiniResult,
        )
    assert result is expected


@pytest.mark.asyncio
async def test_structure_text_context_merge_branch(mini_profile):
    runnable = _fake_runnable(result=_MiniResult(name="ok"))
    chat = _fake_chat(runnable)
    with patch.object(
        structured_draft, "build_chat_model", AsyncMock(return_value=chat)
    ):
        await StructuredDraftService.structure_text(
            TENANT,
            schema_name="test_mini",
            source_text="把数量改成 5",
            result_type=_MiniResult,
            context={"name": "旧草稿"},
        )
    messages = runnable.ainvoke.await_args.args[0]
    user_msg = messages[1]["content"]
    assert "当前解析草稿" in user_msg
    assert '"name": "旧草稿"' in user_msg
    assert "把数量改成 5" in user_msg


@pytest.mark.asyncio
async def test_structure_text_upstream_error_raises_validation_error(
    mini_profile,
):
    runnable = _fake_runnable(exc=ValueError("parse fail"))
    chat = _fake_chat(runnable)
    with patch.object(
        structured_draft, "build_chat_model", AsyncMock(return_value=chat)
    ):
        with pytest.raises(ValidationError, match="test_mini 字段结构化失败"):
            await StructuredDraftService.structure_text(
                TENANT,
                schema_name="test_mini",
                source_text="t",
                result_type=_MiniResult,
            )


# -------------------------------------------------------- structure_from_image


@pytest.mark.asyncio
async def test_structure_from_image_two_step_flow(mini_profile):
    """vision OCR → structure_text：patch extract_text_from_image + chat。"""
    expected = _MiniResult(name="ok")
    runnable = _fake_runnable(result=expected)
    chat = _fake_chat(runnable)
    with (
        patch.object(
            structured_draft,
            "extract_text_from_image",
            AsyncMock(return_value="ocr 文本内容"),
        ) as ocr,
        patch.object(
            structured_draft, "build_chat_model", AsyncMock(return_value=chat)
        ),
    ):
        result = await StructuredDraftService.structure_from_image(
            TENANT,
            schema_name="test_mini",
            image_bytes=_PNG_BYTES,
            content_type=None,
            result_type=_MiniResult,
        )
    assert result is expected
    ocr.assert_awaited_once()
    assert ocr.await_args.kwargs["tenant_id"] == TENANT
    assert ocr.await_args.kwargs["mime"] == "image/png"
    # OCR 结果走 source_label="OCR 文本" 的 structure_text → json_mode
    chat.with_structured_output.assert_called_once_with(
        _MiniResult, method="json_mode", include_raw=True
    )


@pytest.mark.asyncio
async def test_structure_from_image_empty_bytes_fails():
    with pytest.raises(ValidationError, match="请上传图片文件"):
        await StructuredDraftService.structure_from_image(
            TENANT,
            schema_name="test_mini",
            image_bytes=b"",
            content_type=None,
            result_type=_MiniResult,
        )


# ----------------------------------------------------------------- 源码断言


def test_no_json_scraping_in_source():
    """主路径不再依赖字符串抠 JSON。"""
    source = inspect.getsource(structured_draft)
    assert "extract_json_object" not in source
    assert "message_text" not in source


# ------------------------------------------------- review 增补（S6 复核）

from langchain_core.messages import AIMessage  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402


@pytest.mark.asyncio
async def test_complete_json_non_dict_result_fails_closed():
    """schema=None 时模型返回数组/标量 → ValidationError，不放任下游 .get 变 500。"""
    runnable = _fake_runnable(result=[1, 2, 3])
    chat = _fake_chat(runnable)
    with patch.object(
        structured_draft, "build_chat_model", AsyncMock(return_value=chat)
    ):
        with pytest.raises(ValidationError, match="ERR_PREFIX"):
            await StructuredDraftService.complete_json(
                TENANT,
                system="s",
                user_content="u",
                error_prefix="ERR_PREFIX",
            )


@pytest.mark.asyncio
async def test_complete_json_model_resolution_error_not_rewrapped():
    """build_chat_model 的 ValidationError（租户/配置缺失）原样传播，不重包。"""
    with patch.object(
        structured_draft,
        "build_chat_model",
        AsyncMock(side_effect=ValidationError("组织上下文缺失")),
    ):
        with pytest.raises(ValidationError, match="组织上下文缺失"):
            await StructuredDraftService.complete_json(
                TENANT,
                system="s",
                user_content="u",
                error_prefix="ERR_PREFIX",
            )


@pytest.mark.asyncio
async def test_structure_text_unknown_schema_name_fails():
    with pytest.raises(ValidationError, match="未知结构化 schema"):
        await StructuredDraftService.structure_text(
            TENANT,
            schema_name="ghost_schema",
            source_text="t",
            result_type=_MiniResult,
        )


@pytest.mark.asyncio
async def test_structure_text_salvage_normalizes_items(mini_profile):
    """解析失败走严格归一：items=None→[]、剔非 dict 行，再 model_validate。

    mock 仅验证调用契约；envelope 用 include_raw 真实形态
    {raw, parsed, parsing_error}。
    """
    raw_msg = AIMessage(
        content='{"name": "ok", "items": [1, "x", {"material_code": "M1"}]}'
    )
    envelope = {"raw": raw_msg, "parsed": None, "parsing_error": ValueError("x")}
    runnable = _fake_runnable(result=envelope)
    chat = _fake_chat(runnable)

    class _ItemRow(BaseModel):
        material_code: Optional[str] = None

    class _SalesLike(BaseModel):
        name: Optional[str] = None
        items: list[_ItemRow] = []

    with patch.object(
        structured_draft, "build_chat_model", AsyncMock(return_value=chat)
    ):
        result = await StructuredDraftService.structure_text(
            TENANT,
            schema_name="test_mini",
            source_text="t",
            result_type=_SalesLike,
        )
    assert result.name == "ok"
    assert len(result.items) == 1
    assert result.items[0].material_code == "M1"


@pytest.mark.asyncio
async def test_structure_text_salvage_total_failure_raises(mini_profile):
    """raw content 非对象 JSON（如数组）→ 归一失败 → ValidationError。"""
    envelope = {
        "raw": AIMessage(content='[1, 2, 3]'),
        "parsed": None,
        "parsing_error": ValueError("x"),
    }
    runnable = _fake_runnable(result=envelope)
    chat = _fake_chat(runnable)
    with patch.object(
        structured_draft, "build_chat_model", AsyncMock(return_value=chat)
    ):
        with pytest.raises(ValidationError, match="test_mini 字段结构化失败"):
            await StructuredDraftService.structure_text(
                TENANT,
                schema_name="test_mini",
                source_text="t",
                result_type=_MiniResult,
            )


@pytest.mark.asyncio
async def test_structure_from_image_too_large_fails():
    with pytest.raises(ValidationError, match="12MB"):
        await StructuredDraftService.structure_from_image(
            TENANT,
            schema_name="test_mini",
            image_bytes=b"x" * (12 * 1024 * 1024 + 1),
            content_type=None,
            result_type=_MiniResult,
        )


@pytest.mark.asyncio
async def test_structure_from_image_non_image_mime_fails():
    with patch.object(
        structured_draft,
        "guess_image_mime",
        MagicMock(return_value="application/pdf"),
    ):
        with pytest.raises(ValidationError, match="仅支持图片格式"):
            await StructuredDraftService.structure_from_image(
                TENANT,
                schema_name="test_mini",
                image_bytes=_PNG_BYTES,
                content_type="application/pdf",
                result_type=_MiniResult,
            )


def test_with_structured_output_none_schema_constructs():
    """不触网 smoke：真实 ChatOpenAI 上 schema=None + json_mode 可构造 runnable。"""
    chat = ChatOpenAI(api_key="sk-test", model="m")
    runnable = chat.with_structured_output(None, method="json_mode")
    assert runnable is not None
