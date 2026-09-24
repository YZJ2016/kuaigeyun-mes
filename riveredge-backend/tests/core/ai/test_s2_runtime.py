"""KU-AI S2 运行时层单测：model_factory / memory / sse_adapter / tool_bridge。

全部 mock ORM 与上游 LLM，不需要真实端点/数据库。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from core.ai.runtime import memory, model_factory, sse_adapter, tool_bridge
from core.ai.runtime.context import (
    AiRuntimeContext,
    get_ai_context,
    reset_ai_context,
    set_ai_context,
)
from core.ai.tool_registry import ToolRegistry
from infra.exceptions.exceptions import ValidationError

TENANT = 7


class _Query:
    """Tortoise filter() 链替身：order_by().all() / .first()。"""

    def __init__(self, rows):
        self._rows = list(rows)

    def order_by(self, *_args, **_kwargs):
        return self

    async def all(self):
        return self._rows

    async def first(self):
        return self._rows[0] if self._rows else None


def _fake_config(**over):
    cfg = SimpleNamespace(
        chat_base_url="https://fb.example/v1",
        chat_api_key="k-fb",
        chat_model="fb-chat",
        ocr_base_url=None,
        ocr_model=None,
        ocr_api_key=None,
    )
    for key, value in over.items():
        setattr(cfg, key, value)
    return cfg


@pytest.fixture(autouse=True)
def _clear_caches():
    model_factory._MODEL_CACHE.clear()
    model_factory._EMBED_CACHE.clear()
    model_factory._VISION_CACHE.clear()
    yield
    model_factory._MODEL_CACHE.clear()
    model_factory._EMBED_CACHE.clear()
    model_factory._VISION_CACHE.clear()


@pytest.fixture
def registered_tool():
    """往 ToolRegistry 注一个临时工具，用完移除。"""
    added = []

    def _add(name, *, permission=None, handler=None):
        ToolRegistry.register(
            name,
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"desc {name}",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            permission=permission,
            handler=handler,
        )
        added.append(name)

    yield _add
    for name in added:
        ToolRegistry._tools.pop(name, None)


# ---------------------------------------------------------------- model_factory


@pytest.mark.asyncio
async def test_resolve_model_source_fallback_when_catalog_missing():
    with (
        patch.object(model_factory, "_catalog_models", return_value=None),
        patch(
            "core.ai.runtime_config.AiRuntimeConfig.load",
            AsyncMock(return_value=_fake_config()),
        ),
    ):
        source = await model_factory.resolve_model_source(TENANT)
    assert source.base_url == "https://fb.example/v1"
    assert source.api_key == "k-fb"
    assert source.model_name == "fb-chat"
    assert source.model_type == "chat"


@pytest.mark.asyncio
async def test_resolve_model_source_catalog_row_wins_over_fallback():
    model_row = SimpleNamespace(
        id=3,
        tenant_id=TENANT,
        status="0",
        is_default=True,
        model_type="chat",
        model_name="cat-chat",
        provider_id=9,
    )
    provider_row = SimpleNamespace(
        id=9,
        tenant_id=TENANT,
        status="0",
        base_url="https://cat.example/v1",
        api_key="k-cat",
    )
    KuaiaiLlmModel = MagicMock()
    KuaiaiLlmModel.filter = MagicMock(return_value=_Query([model_row]))
    KuaiaiLlmProvider = MagicMock()
    KuaiaiLlmProvider.filter = MagicMock(return_value=_Query([provider_row]))

    with (
        patch.object(
            model_factory,
            "_catalog_models",
            return_value=(KuaiaiLlmModel, KuaiaiLlmProvider),
        ),
        patch(
            "core.ai.runtime_config.AiRuntimeConfig.load",
            AsyncMock(return_value=_fake_config()),
        ) as load,
    ):
        source = await model_factory.resolve_model_source(TENANT)
    assert source.base_url == "https://cat.example/v1"
    assert source.api_key == "k-cat"
    assert source.model_name == "cat-chat"
    load.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_model_source_explicit_id_missing_fails_closed():
    KuaiaiLlmModel = MagicMock()
    KuaiaiLlmModel.filter = MagicMock(return_value=_Query([]))
    KuaiaiLlmProvider = MagicMock()

    with patch.object(
        model_factory,
        "_catalog_models",
        return_value=(KuaiaiLlmModel, KuaiaiLlmProvider),
    ):
        with pytest.raises(ValidationError):
            await model_factory.resolve_model_source(TENANT, model_id=404)


@pytest.mark.asyncio
async def test_build_chat_model_caches_and_evicts():
    with (
        patch.object(model_factory, "_catalog_models", return_value=None),
        patch(
            "core.ai.runtime_config.AiRuntimeConfig.load",
            AsyncMock(return_value=_fake_config()),
        ) as load,
    ):
        first = await model_factory.build_chat_model(TENANT)
        second = await model_factory.build_chat_model(TENANT)
        assert first is second
        assert load.call_count == 1

        model_factory.evict_model_cache(TENANT)
        third = await model_factory.build_chat_model(TENANT)
        assert third is not first
        assert load.call_count == 2


@pytest.mark.asyncio
async def test_build_vision_model_uses_ocr_fallback():
    cfg = _fake_config(
        ocr_base_url="https://ocr.example/v1",
        ocr_model="ocr-model",
        ocr_api_key="k-ocr",
    )
    with (
        patch.object(model_factory, "_catalog_models", return_value=None),
        patch(
            "core.ai.runtime_config.AiRuntimeConfig.load",
            AsyncMock(return_value=cfg),
        ),
    ):
        source = await model_factory.resolve_model_source(TENANT, model_type="vision")
        chat = await model_factory.build_vision_model(TENANT)
    assert source.model_type == "vision"
    assert source.model_name == "ocr-model"
    assert chat.model_name == "ocr-model"


@pytest.mark.asyncio
async def test_build_vision_model_unconfigured_fails_closed():
    with (
        patch.object(model_factory, "_catalog_models", return_value=None),
        patch(
            "core.ai.runtime_config.AiRuntimeConfig.load",
            AsyncMock(return_value=_fake_config()),
        ),
    ):
        with pytest.raises(ValidationError):
            await model_factory.build_vision_model(TENANT)


# ---------------------------------------------------------------- memory


def test_normalize_tool_calls_openai_wire_to_lc():
    raw = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "search", "arguments": '{"q": "abc"}'},
        }
    ]
    out = memory.normalize_tool_calls(raw)
    assert out == [
        {"name": "search", "args": {"q": "abc"}, "id": "call_1", "type": "tool_call"}
    ]


def test_normalize_tool_calls_passthrough_and_bad_json():
    lc_call = {"name": "done", "args": {"x": 1}, "id": "c2", "type": "tool_call"}
    bad_json = {
        "id": "c3",
        "type": "function",
        "function": {"name": "broken", "arguments": "{not-json"},
    }
    out = memory.normalize_tool_calls([lc_call, bad_json, "junk", None])
    assert out[0] == lc_call
    assert out[1]["args"] == {}
    assert out[1]["name"] == "broken"
    assert len(out) == 2


def test_to_lc_messages_replays_duck_typed_rows():
    rows = [
        SimpleNamespace(role="user", content="你好"),
        SimpleNamespace(
            role="assistant",
            content="调用工具",
            tool_calls=[
                {
                    "id": "call_9",
                    "type": "function",
                    "function": {"name": "f", "arguments": "{}"},
                }
            ],
        ),
        SimpleNamespace(
            role="tool",
            content="结果",
            tool_call_id="call_9",
            tool_name="f",
        ),
        SimpleNamespace(role="assistant", content=None, tool_calls=None),
    ]
    messages = memory.to_lc_messages(rows)
    assert isinstance(messages[0], HumanMessage)
    assert isinstance(messages[1], AIMessage)
    assert messages[1].tool_calls[0]["name"] == "f"
    assert isinstance(messages[2], ToolMessage)
    assert messages[2].tool_call_id == "call_9"
    assert isinstance(messages[3], AIMessage)
    assert messages[3].content == ""


# ---------------------------------------------------------------- sse_adapter


class _FakeAgent:
    def __init__(self, texts=None, stream_exc=None, ainvoke_result=None):
        self._texts = texts or []
        self._stream_exc = stream_exc
        self._ainvoke_result = ainvoke_result

    async def astream_events(self, payload, config=None, version=None):
        if self._stream_exc is not None:
            raise self._stream_exc
        for text in self._texts:
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": SimpleNamespace(content=text)},
            }

    async def ainvoke(self, payload, config=None):
        return self._ainvoke_result


async def _collect(agent, model_name="m"):
    chunks = [
        raw
        async for raw in sse_adapter.agent_to_openai_sse(
            agent, [], model_name=model_name, config={}
        )
    ]
    return b"".join(chunks).decode("utf-8")


@pytest.mark.asyncio
async def test_agent_to_openai_sse_chunk_wire_format():
    agent = _FakeAgent(texts=["你好", "世界"])
    body = await _collect(agent)
    frames = [line for line in body.split("\n") if line.startswith("data: ")]
    assert frames[-1] == "data: [DONE]"

    first = json.loads(frames[0][len("data: ") :])
    assert first["object"] == "chat.completion.chunk"
    assert first["model"] == "m"
    assert first["choices"][0]["delta"]["role"] == "assistant"
    assert first["choices"][0]["delta"]["content"] == "你好"

    second = json.loads(frames[1][len("data: ") :])
    assert "role" not in second["choices"][0]["delta"]
    assert second["choices"][0]["delta"]["content"] == "世界"


@pytest.mark.asyncio
async def test_agent_to_openai_sse_nonstream_fallback_before_first_chunk():
    agent = _FakeAgent(
        stream_exc=RuntimeError("upstream broke"),
        ainvoke_result={"messages": [AIMessage(content="完整回答")]},
    )
    body = await _collect(agent)
    frames = [line for line in body.split("\n") if line.startswith("data: ")]
    assert frames[-1] == "data: [DONE]"
    payload = json.loads(frames[0][len("data: ") :])
    assert payload["choices"][0]["delta"]["content"] == "完整回答"


@pytest.mark.asyncio
async def test_agent_to_openai_sse_error_after_emit_writes_error_frame():
    class _MidFailAgent:
        async def astream_events(self, payload, config=None, version=None):
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": SimpleNamespace(content="半截")},
            }
            raise RuntimeError("mid-stream")

        async def ainvoke(self, payload, config=None):
            raise AssertionError("不允许进入非流式补全")

    body = await _collect(_MidFailAgent())
    frames = [line for line in body.split("\n") if line.startswith("data: ")]
    assert frames[-1] == "data: [DONE]"
    error_frame = json.loads(frames[-2][len("data: ") :])
    assert "error" in error_frame


# ---------------------------------------------------------------- tool_bridge


def _ctx(user_id=5, **flags):
    return AiRuntimeContext(
        tenant_id=TENANT, user=SimpleNamespace(id=user_id), **flags
    )


def _request(name="t", call_id="call_1"):
    return SimpleNamespace(
        tool_call={"name": name, "id": call_id},
        tool=None,
        state={},
        runtime=None,
    )


@pytest.mark.asyncio
async def test_tool_guard_denies_without_permission(registered_tool):
    registered_tool("perm_tool", permission="kuaiai:entry:read")
    token = set_ai_context(_ctx())
    try:
        handler = AsyncMock()
        with (
            patch.object(
                tool_bridge.UserPermissionService,
                "has_permission",
                AsyncMock(return_value=False),
            ),
            patch.object(tool_bridge, "_audit_tool_call", AsyncMock()) as audit,
        ):
            result = await tool_bridge.build_tool_guard_middleware().awrap_tool_call(
                _request("perm_tool"), handler
            )
    finally:
        reset_ai_context(token)
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    handler.assert_not_called()
    assert audit.await_count == 1


@pytest.mark.asyncio
async def test_tool_guard_swallows_handler_exception(registered_tool):
    registered_tool("boom_tool", permission="kuaiai:entry:read")
    token = set_ai_context(_ctx(is_tenant_admin=True))
    try:
        async def handler(_request):
            raise RuntimeError("boom")

        with patch.object(tool_bridge, "_audit_tool_call", AsyncMock()):
            result = await tool_bridge.build_tool_guard_middleware().awrap_tool_call(
                _request("boom_tool"), handler
            )
    finally:
        reset_ai_context(token)
    assert isinstance(result, ToolMessage)
    assert result.status == "error"


@pytest.mark.asyncio
async def test_lc_tool_returns_error_message_without_context(registered_tool):
    registered_tool("need_ctx", handler=AsyncMock(return_value="ok"))
    tools = tool_bridge.registry_to_lc_tools(["need_ctx"])
    assert len(tools) == 1
    result = await tools[0].ainvoke({})
    assert isinstance(result, ToolMessage)
    assert result.status == "error"


@pytest.mark.asyncio
async def test_lc_tool_handler_exception_not_raised(registered_tool):
    async def boom(**_kwargs):
        raise RuntimeError("db down")

    registered_tool("h_boom", handler=boom)
    token = set_ai_context(_ctx())
    try:
        tools = tool_bridge.registry_to_lc_tools(["h_boom"])
        result = await tools[0].ainvoke({})
    finally:
        reset_ai_context(token)
    assert isinstance(result, ToolMessage)
    assert result.status == "error"


def test_context_roundtrip_and_empty():
    assert get_ai_context() is None
    token = set_ai_context(_ctx())
    try:
        ctx = get_ai_context()
        assert ctx is not None
        assert ctx.tenant_id == TENANT
    finally:
        reset_ai_context(token)
    assert get_ai_context() is None


# ------------------------------------------------------- review fixes (S2)


@pytest.mark.asyncio
async def test_agent_sse_no_ainvoke_fallback_after_tool_event():
    """工具事件发生后流式失败：禁止整图 ainvoke 重跑，直接错误帧。"""

    class _ToolThenFailAgent:
        def __init__(self):
            self.ainvoke_called = False

        async def astream_events(self, payload, config=None, version=None):
            yield {"event": "on_tool_start", "data": {"input": {}}}
            yield {"event": "on_tool_end", "data": {"output": "done"}}
            raise RuntimeError("stream broke after tool ran")

        async def ainvoke(self, payload, config=None):
            self.ainvoke_called = True
            return {"messages": [AIMessage(content="不应出现")]}

    agent = _ToolThenFailAgent()
    body = await _collect(agent)
    assert agent.ainvoke_called is False
    frames = [line for line in body.split("\n") if line.startswith("data: ")]
    assert frames[-1] == "data: [DONE]"
    error_frame = json.loads(frames[-2][len("data: ") :])
    assert "error" in error_frame


@pytest.mark.asyncio
async def test_tool_guard_denies_tool_without_permission(registered_tool):
    """无 permission 的注册工具 fail-closed（m2）。"""
    registered_tool("noperm_tool")  # permission=None
    token = set_ai_context(_ctx(is_tenant_admin=True))
    try:
        handler = AsyncMock()
        with patch.object(tool_bridge, "_audit_tool_call", AsyncMock()) as audit:
            result = await tool_bridge.build_tool_guard_middleware().awrap_tool_call(
                _request("noperm_tool"), handler
            )
    finally:
        reset_ai_context(token)
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    handler.assert_not_called()
    assert audit.await_count == 1
    assert audit.await_args.kwargs["status_code"] == 403


@pytest.mark.asyncio
async def test_tool_guard_denies_unregistered_tool():
    """未注册工具名 fail-closed（m2）。"""
    token = set_ai_context(_ctx(is_tenant_admin=True))
    try:
        handler = AsyncMock()
        result = await tool_bridge.build_tool_guard_middleware().awrap_tool_call(
            _request("ghost_tool_xyz"), handler
        )
    finally:
        reset_ai_context(token)
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_tool_guard_audit_business_error_is_4xx_not_500(registered_tool):
    """业务错误（error ToolMessage，无异常）记 4xx；业务键进 route。"""
    registered_tool("biz_tool", permission="kuaiai:entry:read")
    err_msg = ToolMessage(
        content="bad input", tool_call_id="call_9", name="biz_tool", status="error"
    )
    token = set_ai_context(_ctx(is_tenant_admin=True))
    try:
        request = SimpleNamespace(
            tool_call={
                "name": "biz_tool",
                "id": "call_9",
                "args": {"work_order_id": 11},
            }
        )
        with patch(
            "core.models.ai_audit_log.AiAuditLog.create", AsyncMock()
        ) as create:
            result = await tool_bridge.build_tool_guard_middleware().awrap_tool_call(
                request, AsyncMock(return_value=err_msg)
            )
    finally:
        reset_ai_context(token)
    assert result is err_msg
    kwargs = create.await_args.kwargs
    assert kwargs["status_code"] == 400
    assert kwargs["error_message"] == "tool_error"
    assert "work_order_id=11" in kwargs["route"]


@pytest.mark.asyncio
async def test_tool_guard_audit_exception_is_500(registered_tool):
    """handler 抛穿异常记 500。"""
    registered_tool("exc_tool", permission="kuaiai:entry:read")

    async def boom(_request):
        raise RuntimeError("db down")

    token = set_ai_context(_ctx(is_tenant_admin=True))
    try:
        request = SimpleNamespace(
            tool_call={"name": "exc_tool", "id": "c1", "args": {"record_id": 3}}
        )
        with patch(
            "core.models.ai_audit_log.AiAuditLog.create", AsyncMock()
        ) as create:
            result = await tool_bridge.build_tool_guard_middleware().awrap_tool_call(
                request, boom
            )
    finally:
        reset_ai_context(token)
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    kwargs = create.await_args.kwargs
    assert kwargs["status_code"] == 500
    assert kwargs["error_message"] == "RuntimeError"
    assert "record_id=3" in kwargs["route"]


@pytest.mark.asyncio
async def test_explicit_model_id_type_mismatch_fails_closed():
    """显式 model_id 指向 chat 行、按 vision 解析 → ValidationError（m4）。"""
    model_row = SimpleNamespace(
        id=3,
        tenant_id=TENANT,
        status="0",
        is_default=True,
        model_type="chat",
        model_name="cat-chat",
        provider_id=9,
    )
    KuaiaiLlmModel = MagicMock()
    KuaiaiLlmModel.filter = MagicMock(return_value=_Query([model_row]))
    KuaiaiLlmProvider = MagicMock()

    with patch.object(
        model_factory,
        "_catalog_models",
        return_value=(KuaiaiLlmModel, KuaiaiLlmProvider),
    ):
        with pytest.raises(ValidationError):
            await model_factory.resolve_model_source(
                TENANT, model_id=3, model_type="vision"
            )
        with pytest.raises(ValidationError):
            await model_factory.build_vision_model(TENANT, model_id=3)


def test_ensure_defaults_skips_items_without_permission():
    """兜底注册：无 permission 的定义不注册（m3 fail-closed 配套）。"""
    import sys
    import types

    fake = types.ModuleType("apps.kuaiai.services.chat_tools")
    fake.CHAT_TOOL_DEFINITIONS = [
        {"type": "function", "function": {"name": "ut_noperm_def"}},
        {
            "type": "function",
            "function": {"name": "ut_perm_def"},
            "permission": "ut:scope:read",
        },
    ]
    old_flag = ToolRegistry._defaults_loaded
    ToolRegistry._defaults_loaded = False
    try:
        with patch.dict(sys.modules, {"apps.kuaiai.services.chat_tools": fake}):
            ToolRegistry.ensure_defaults()
        assert "ut_noperm_def" not in ToolRegistry._tools
        assert "ut_perm_def" in ToolRegistry._tools
        assert ToolRegistry._defaults_loaded is True
    finally:
        ToolRegistry._tools.pop("ut_noperm_def", None)
        ToolRegistry._tools.pop("ut_perm_def", None)
        ToolRegistry._defaults_loaded = old_flag


def test_ensure_defaults_flag_not_set_on_non_import_error():
    """非 ImportError 异常不置位，允许下次重试（m3）。"""
    import sys

    class _BoomModule:
        def __getattr__(self, name):
            raise RuntimeError("module half-init")

    old_flag = ToolRegistry._defaults_loaded
    ToolRegistry._defaults_loaded = False
    try:
        with patch.dict(
            sys.modules, {"apps.kuaiai.services.chat_tools": _BoomModule()}
        ):
            with pytest.raises(RuntimeError):
                ToolRegistry.ensure_defaults()
        assert ToolRegistry._defaults_loaded is False
    finally:
        ToolRegistry._defaults_loaded = old_flag


def test_audit_middleware_ignores_client_tenant_header():
    """审计归属不读 X-Tenant-ID：优先 request.state（m1）。"""
    from core.ai.middleware import AiAuditMiddleware

    req = SimpleNamespace(
        headers={"X-Tenant-ID": "999"},
        state=SimpleNamespace(tenant_id=TENANT, user_id=5),
    )
    assert AiAuditMiddleware._extract_identity(req) == (TENANT, 5)

    # 无认证身份时客户端头不能伪造归属 → None（审计行不落）
    req2 = SimpleNamespace(headers={"X-Tenant-ID": "999"}, state=SimpleNamespace())
    assert AiAuditMiddleware._extract_identity(req2) == (None, None)


@pytest.mark.asyncio
async def test_fallback_ignores_client_model_override():
    """KR-G0 兜底路径忽略客户端 model，用配置模型名（n7）。"""
    from core.ai import chat_handler

    chat = MagicMock()
    chat.model_name = "cfg-chat"
    bound = MagicMock()
    bound.ainvoke = AsyncMock(return_value=AIMessage(content="hi"))
    chat.bind = MagicMock(return_value=bound)
    ai_auth = SimpleNamespace(
        tenant_id=TENANT,
        user=SimpleNamespace(id=5),
        auth=SimpleNamespace(is_infra_admin=False, is_tenant_admin=False),
    )
    with (
        patch.object(chat_handler, "_kuaiai_composed", return_value=False),
        patch(
            "core.ai.runtime.model_factory.build_chat_model",
            AsyncMock(return_value=chat),
        ),
        patch(
            "core.ai.runtime_config.AiRuntimeConfig.load",
            AsyncMock(return_value=_fake_config()),
        ),
    ):
        result = await chat_handler.create_chat_completion(
            ai_auth,
            [{"role": "user", "content": "hi"}],
            model="evil-model",
        )
    assert result["model"] == "cfg-chat"
    assert "model" not in chat.bind.call_args.kwargs
