"""KU-AI S1 单测：委托探测、会话归属、消息回放、SSE 线格式。

全部 mock 上游 LLM 与 Tortoise 查询，不需要真实端点/数据库。
"""

from __future__ import annotations

import importlib.util
import inspect
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import StreamingResponse

import apps.kuaiai.services.chat_service as cs
from apps.kuaiai.models.chat import KuaiaiChatMessage
from apps.kuaiai.services import session_service
from infra.exceptions.exceptions import (
    AuthorizationError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)

TENANT = 7
USER_ID = 5


def _user(uid: int = USER_ID):
    return SimpleNamespace(id=uid)


def _session(session_id: int = 1, user_id: int = USER_ID, model=None, title=""):
    s = SimpleNamespace(
        id=session_id, user_id=user_id, tenant_id=TENANT, model=model, title=title
    )
    s.update_from_dict = MagicMock(return_value=s)
    s.save = AsyncMock()
    return s


def _config(**over):
    base = dict(
        chat_api_key="fake-key",
        chat_base_url="https://llm.example.invalid",
        chat_model="fake-model",
        custom_system_prompt=None,
        stream_enabled=True,
    )
    base.update(over)
    return SimpleNamespace(**base)


class _FakeChunk:
    def __init__(self, content, usage=None):
        self.content = content
        self.usage_metadata = usage


class _FakeChat:
    """模拟 ChatOpenAI：astream 吐两块 + usage，ainvoke 回 AIMessage 形态。

    S2 起由 ``model_factory.build_chat_model`` 产出，需带 ``model_name``
    （chat_service 校验非空）与 ``bind``（请求级 temperature 透传）。
    """

    instances: list["_FakeChat"] = []

    def __init__(self, model_name="fake-model", **kwargs):
        self.model_name = model_name
        self.kwargs = kwargs
        self.streamed_with = []
        self.invoked_with = []
        self.bind_calls = []
        _FakeChat.instances.append(self)

    def bind(self, **kwargs):
        self.bind_calls.append(kwargs)
        return self

    async def astream(self, messages):
        self.streamed_with.append(messages)
        yield _FakeChunk("你好")
        yield _FakeChunk(
            "，世界",
            {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
        )

    async def ainvoke(self, messages):
        self.invoked_with.append(messages)
        return SimpleNamespace(
            content="你好，世界",
            id="chatcmpl-fake",
            usage_metadata={
                "input_tokens": 3,
                "output_tokens": 2,
                "total_tokens": 5,
            },
            response_metadata={"finish_reason": "stop"},
        )


@pytest.fixture(autouse=True)
def _reset_fake_chat():
    _FakeChat.instances.clear()
    yield
    _FakeChat.instances.clear()


def _patch_runtime():
    return patch.object(
        cs.AiRuntimeConfig, "load", new=AsyncMock(return_value=_config())
    )


def _patch_build_chat_model(chat: "_FakeChat | None" = None):
    """S2 收口后路径 A 模型经 ``model_factory.build_chat_model`` 解析
    （目录行优先、IntegrationConfig 兜底），patch cs 模块内引用名。"""
    return patch.object(
        cs, "build_chat_model", new=AsyncMock(return_value=chat or _FakeChat())
    )


@pytest.fixture(autouse=True)
def _no_catalog_source():
    """U-2 起 send 主路径先判定目录行命中；本文件既有用例全部走
    IntegrationConfig 兜底（AiRuntimeConfig.load 由各用例自 patch），
    故默认目录行未命中。命中场景由 TestCatalogDecoupledFromConnector
    在测试体内覆盖 patch。"""
    with patch.object(
        cs, "_resolve_catalog_source", new=AsyncMock(return_value=None)
    ):
        yield


class TestFindSpecSingleName:
    def test_only_chat_service_probed(self):
        assert importlib.util.find_spec("apps.kuaiai.services.chat_service") is not None
        assert importlib.util.find_spec("apps.kuaiai.services.deepseek_service") is None

    def test_handler_probes_new_name_only(self):
        from core.ai import chat_handler

        assert chat_handler._kuaiai_composed() is True
        source = inspect.getsource(chat_handler)
        assert 'find_spec("apps.kuaiai.services.chat_service")' in source
        assert 'find_spec("apps.kuaiai.services.deepseek_service")' not in source


class TestSessionOwnership:
    @pytest.mark.asyncio
    async def test_cross_user_session_403(self):
        session = _session(user_id=999)
        with patch.object(
            session_service.KuaiaiChatSession,
            "get_or_none",
            new=AsyncMock(return_value=session),
        ):
            with pytest.raises(AuthorizationError):
                await session_service.get_owned_session(TENANT, 1, USER_ID)

    @pytest.mark.asyncio
    async def test_cross_tenant_session_404(self):
        with patch.object(
            session_service.KuaiaiChatSession,
            "get_or_none",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await session_service.get_owned_session(8, 1, USER_ID)

    @pytest.mark.asyncio
    async def test_chat_completion_denied_session_never_touches_upstream(self):
        """归属失败 → 404/403，且 AiRuntimeConfig.load / build_chat_model 均未触达。"""
        with (
            patch.object(
                cs,
                "get_owned_session",
                new=AsyncMock(side_effect=NotFoundError("会话", "9")),
            ),
            _patch_runtime() as mock_load,
            _patch_build_chat_model() as mock_build,
        ):
            with pytest.raises(NotFoundError):
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    stream=True,
                    user=_user(),
                    context={"session_id": 9},
                )
            mock_load.assert_not_called()
            mock_build.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_tenant_fails_closed(self):
        with pytest.raises(ValidationError):
            await cs.create_chat_completion(
                0, [{"role": "user", "content": "hi"}], user=_user()
            )


class TestHistoryReplay:
    def test_rows_to_lc_messages(self):
        rows = [
            SimpleNamespace(
                role="user", content="问1", tool_calls=None,
                tool_call_id=None, tool_name=None,
            ),
            SimpleNamespace(
                role="assistant", content="答1", tool_calls=None,
                tool_call_id=None, tool_name=None,
            ),
            SimpleNamespace(
                role="tool", content="结果", tool_calls=None,
                tool_call_id="call_1", tool_name="search_knowledge",
            ),
        ]
        msgs = cs._rows_to_lc_messages(rows)
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        assert isinstance(msgs[0], HumanMessage) and msgs[0].content == "问1"
        assert isinstance(msgs[1], AIMessage) and msgs[1].content == "答1"
        assert isinstance(msgs[2], ToolMessage)
        assert msgs[2].tool_call_id == "call_1"
        assert msgs[2].name == "search_knowledge"

    @pytest.mark.asyncio
    async def test_session_send_replays_table_history(self):
        """会话路径：先落 user 行 → 消息表回放为唯一历史 → 再调上游。"""
        user = _user()
        session = _session()
        history_rows = [
            SimpleNamespace(
                role="user", content="旧问", tool_calls=None,
                tool_call_id=None, tool_name=None,
            ),
            SimpleNamespace(
                role="assistant", content="旧答", tool_calls=None,
                tool_call_id=None, tool_name=None,
            ),
            SimpleNamespace(
                role="user", content="新问", tool_calls=None,
                tool_call_id=None, tool_name=None,
            ),
        ]
        order: list[str] = []

        async def _persist_user(*a, **kw):
            order.append("persist_user")

        with (
            patch.object(
                cs, "get_owned_session", new=AsyncMock(return_value=session)
            ),
            patch.object(cs, "_persist_user_message", new=_persist_user),
            patch.object(
                cs, "_history_rows", new=AsyncMock(return_value=history_rows)
            ),
            patch.object(
                cs, "_persist_assistant_message", new=AsyncMock()
            ) as mock_pa,
            _patch_runtime(),
            _patch_build_chat_model(),
        ):
            result = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "新问"}],
                stream=False,
                user=user,
                context={"session_id": 1},
            )

        assert order == ["persist_user"]
        chat = _FakeChat.instances[0]
        # 上游收到的消息来自消息表回放（唯一历史来源），而非请求原文
        sent = chat.invoked_with[0]
        assert [m.content for m in sent] == ["旧问", "旧答", "新问"]
        assert result["object"] == "chat.completion"
        assert result["choices"][0]["message"]["content"] == "你好，世界"
        assert result["usage"]["prompt_tokens"] == 3
        mock_pa.assert_awaited_once()


class TestPureForward:
    @pytest.mark.asyncio
    async def test_no_session_pure_forward_no_persist(self):
        """无 session_id：纯转发，不落库。"""
        with (
            patch.object(cs, "get_owned_session", new=AsyncMock()) as mock_get,
            patch.object(cs, "_persist_user_message", new=AsyncMock()) as mock_pu,
            patch.object(
                cs, "_persist_assistant_message", new=AsyncMock()
            ) as mock_pa,
            _patch_runtime(),
            _patch_build_chat_model(),
        ):
            result = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "hi"}],
                stream=False,
                user=_user(),
                context=None,
            )
        mock_get.assert_not_called()
        mock_pu.assert_not_called()
        mock_pa.assert_not_called()
        assert result["object"] == "chat.completion"


class TestSseWireFormat:
    @pytest.mark.asyncio
    async def test_openai_chunk_lines_and_done(self):
        user = _user()
        session = _session()
        with (
            patch.object(
                cs, "get_owned_session", new=AsyncMock(return_value=session)
            ),
            patch.object(cs, "_persist_user_message", new=AsyncMock()),
            patch.object(cs, "_history_rows", new=AsyncMock(return_value=[])),
            patch.object(
                cs, "_persist_assistant_message", new=AsyncMock()
            ) as mock_pa,
            patch(
                "core.services.realtime.ai_stream_bridge.schedule_user_realtime_event",
                new=MagicMock(),
            ),
            _patch_runtime(),
            _patch_build_chat_model(),
        ):
            resp = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "hi"}],
                stream=True,
                user=user,
                context={"session_id": 1},
            )
            assert isinstance(resp, StreamingResponse)
            assert resp.media_type == "text/event-stream"
            body = b""
            async for chunk in resp.body_iterator:
                body += chunk

        text = body.decode("utf-8")
        lines = [l for l in text.split("\n\n") if l.strip()]
        assert lines[-1] == "data: [DONE]"
        payloads = [
            json.loads(l[len("data: "):])
            for l in lines
            if l.startswith("data: ") and "[DONE]" not in l
        ]
        deltas = [p["choices"][0]["delta"]["content"] for p in payloads]
        assert deltas == ["你好", "，世界"]
        assert payloads[0]["choices"][0]["delta"].get("role") == "assistant"
        # assistant 行落库 + token 回填
        mock_pa.assert_awaited_once()
        kw = mock_pa.await_args.kwargs
        assert kw["prompt_tokens"] == 3
        assert kw["completion_tokens"] == 2

    @pytest.mark.asyncio
    async def test_stream_disabled_fails(self):
        with (
            patch.object(
                cs.AiRuntimeConfig,
                "load",
                new=AsyncMock(return_value=_config(stream_enabled=False)),
            ),
            _patch_build_chat_model(),
        ):
            with pytest.raises(ValidationError):
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    stream=True,
                    user=_user(),
                )

    @pytest.mark.asyncio
    async def test_stream_disabled_rejects_before_user_row_persisted(self):
        """站点关流式 + stream=True：拒绝必须发生在 user 行落库之前。"""
        with (
            patch.object(
                cs,
                "get_owned_session",
                new=AsyncMock(return_value=_session()),
            ),
            patch.object(
                cs, "_persist_user_message", new=AsyncMock()
            ) as mock_pu,
            patch.object(
                cs.AiRuntimeConfig,
                "load",
                new=AsyncMock(return_value=_config(stream_enabled=False)),
            ),
            _patch_build_chat_model(),
        ):
            with pytest.raises(ValidationError):
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    stream=True,
                    user=_user(),
                    context={"session_id": 1},
                )
        mock_pu.assert_not_called()


class TestModelResolution:
    @pytest.mark.asyncio
    async def test_all_blank_model_fails_before_upstream(self):
        """model 请求值/会话值皆空白 → 名匹配短路走默认解析；解析结果
        model_name 空白 → ValidationError，不触达上游调用。"""
        blank = _FakeChat(model_name="")
        with (
            patch.object(
                cs,
                "get_owned_session",
                new=AsyncMock(return_value=_session(model="   ")),
            ),
            _patch_runtime(),
            _patch_build_chat_model(blank) as mock_build,
        ):
            with pytest.raises(ValidationError):
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    model="   ",
                    user=_user(),
                    context={"session_id": 1},
                )
        # 空白名不形成目录行 id（_match_catalog_model_id 短路，不查库），
        # 以默认槽 model_id=None 解析
        mock_build.assert_awaited_once_with(TENANT, None)
        assert blank.invoked_with == []
        assert blank.streamed_with == []


class TestChatModelConstruction:
    @pytest.mark.asyncio
    async def test_chat_openai_stream_usage_and_timeout(self):
        """出站 ChatOpenAI 必须显式开 stream_usage（token 回填）+ 120s 超时。

        S2 起构造收口在 ``model_factory._new_chat_model``，断言相应下移一层：
        chat_service 调 ``build_chat_model``，其内部构造 ChatOpenAI 的参数
        在 model_factory 模块命名空间捕获。
        """
        from core.ai.runtime import model_factory

        captured: dict = {}

        def _ctor(**kw):
            captured.update(kw)
            return _FakeChat()

        source = model_factory.ModelSource(
            base_url="https://llm.example.invalid",
            api_key="sk-fake",
            model_name="fake-model",
        )
        model_factory._MODEL_CACHE.clear()
        try:
            with (
                patch.object(
                    model_factory,
                    "resolve_model_source",
                    new=AsyncMock(return_value=source),
                ),
                patch.object(
                    model_factory, "ChatOpenAI", side_effect=_ctor
                ),
                patch.object(
                    model_factory, "get_http_client", return_value=MagicMock()
                ),
                _patch_runtime(),
            ):
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    user=_user(),
                )
        finally:
            # 清掉缓存进去的 fake，避免污染其它用例
            model_factory._MODEL_CACHE.clear()
        assert captured["stream_usage"] is True
        assert captured["request_timeout"] == 120


class TestUpstreamFailureMasked:
    @pytest.mark.asyncio
    async def test_nonstream_upstream_error_not_leaked(self):
        """ainvoke 抛 SDK 异常 → ExternalServiceError(502) 通用文案，
        不泄露 base_url/原文（n2：上游失败属服务端语义，非客户端 4xx）。"""
        leaky = Exception(
            "Connection error: https://llm.example.invalid/v1 refused (api_key=sk-xxx)"
        )

        class _BoomChat(_FakeChat):
            async def ainvoke(self, messages):
                raise leaky

        with (
            _patch_build_chat_model(_BoomChat()),
            _patch_runtime(),
        ):
            with pytest.raises(ExternalServiceError) as excinfo:
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    user=_user(),
                )
        assert excinfo.value.status_code == 502
        assert "llm.example.invalid" not in str(excinfo.value.message)
        assert "sk-xxx" not in str(excinfo.value.message)


class TestToolCallsNormalize:
    def test_openai_wire_form_converted(self):
        raw = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "search_knowledge", "arguments": '{"q": "x"}'},
            }
        ]
        out = cs._normalize_tool_calls(raw)
        assert out == [
            {
                "name": "search_knowledge",
                "args": {"q": "x"},
                "id": "call_1",
                "type": "tool_call",
            }
        ]

    def test_langchain_form_passthrough(self):
        raw = [{"name": "search_knowledge", "args": {"q": "x"}, "id": "call_1"}]
        out = cs._normalize_tool_calls(raw)
        assert out == raw

    def test_bad_arguments_json_falls_back_empty_args(self):
        raw = [
            {
                "id": "call_2",
                "type": "function",
                "function": {"name": "f", "arguments": "{broken"},
            }
        ]
        out = cs._normalize_tool_calls(raw)
        assert out[0]["args"] == {}

    def test_replay_converts_openai_wire_row(self):
        """消息表存的 OpenAI 线格式经回放转为 LangChain 形态。"""
        from langchain_core.messages import AIMessage

        rows = [
            SimpleNamespace(
                role="assistant",
                content="",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "search_knowledge",
                            "arguments": '{"q": "x"}',
                        },
                    }
                ],
                tool_call_id=None,
                tool_name=None,
            ),
        ]
        msgs = cs._rows_to_lc_messages(rows)
        assert isinstance(msgs[0], AIMessage)
        assert msgs[0].tool_calls[0]["name"] == "search_knowledge"
        assert msgs[0].tool_calls[0]["args"] == {"q": "x"}


class TestCatalogDecoupledFromConnector:
    """U-2：目录行独立支撑对话——catalog 命中跳过 AiRuntimeConfig.load。"""

    def _source(self):
        return SimpleNamespace(
            base_url="https://cat.invalid/v1",
            api_key="sk-cat",
            model_name="cat-chat",
            model_type="chat",
        )

    @pytest.mark.asyncio
    async def test_catalog_hit_skips_runtime_config_load(self):
        """目录行命中 + 连接器未启用：不再 422，正常对话。"""
        with (
            patch.object(
                cs,
                "_resolve_catalog_source",
                new=AsyncMock(return_value=self._source()),
            ),
            patch.object(
                cs.AiRuntimeConfig,
                "load",
                new=AsyncMock(side_effect=ValidationError("AI 连接器未启用")),
            ) as mock_load,
            _patch_build_chat_model(),
        ):
            result = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "hi"}],
                user=_user(),
            )
        assert result["object"] == "chat.completion"
        assert result["choices"][0]["message"]["content"] == "你好，世界"
        mock_load.assert_not_called()

    @pytest.mark.asyncio
    async def test_catalog_hit_stream_defaults_enabled(self):
        """目录行命中路径读不到 stream_enabled 开关 → 默认放行流式。"""
        session = _session()
        with (
            patch.object(
                cs,
                "_resolve_catalog_source",
                new=AsyncMock(return_value=self._source()),
            ),
            patch.object(
                cs.AiRuntimeConfig,
                "load",
                new=AsyncMock(side_effect=ValidationError("AI 连接器未启用")),
            ) as mock_load,
            patch.object(
                cs, "get_owned_session", new=AsyncMock(return_value=session)
            ),
            patch.object(cs, "_persist_user_message", new=AsyncMock()),
            patch.object(cs, "_history_rows", new=AsyncMock(return_value=[])),
            patch.object(cs, "_persist_assistant_message", new=AsyncMock()),
            patch(
                "core.services.realtime.ai_stream_bridge.schedule_user_realtime_event",
                new=MagicMock(),
            ),
            _patch_build_chat_model(),
        ):
            resp = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "hi"}],
                stream=True,
                user=_user(),
                context={"session_id": 1},
            )
            assert isinstance(resp, StreamingResponse)
            body = b""
            async for chunk in resp.body_iterator:
                body += chunk
        assert b"data: [DONE]" in body
        mock_load.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_still_422_when_connector_disabled(self):
        """无目录行 → IntegrationConfig 兜底，连接器未启用仍 422（语义不变）。"""
        with (
            patch.object(
                cs.AiRuntimeConfig,
                "load",
                new=AsyncMock(side_effect=ValidationError("AI 连接器未启用")),
            ),
            _patch_build_chat_model() as mock_build,
        ):
            with pytest.raises(ValidationError):
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    user=_user(),
                )
        mock_build.assert_not_called()


class TestHistoryWindowOrphans:
    """n5：尾部截断切断 tool 对时，丢弃窗口头部连续孤儿行。"""

    def _row(self, role, **kw):
        base = dict(
            role=role,
            content="",
            tool_calls=None,
            tool_call_id=None,
            tool_name=None,
        )
        base.update(kw)
        return SimpleNamespace(**base)

    def _assistant_with_calls(self, *call_ids):
        return self._row(
            "assistant",
            tool_calls=[
                {
                    "id": cid,
                    "type": "function",
                    "function": {"name": "t", "arguments": "{}"},
                }
                for cid in call_ids
            ],
        )

    def test_head_tool_row_dropped(self):
        rows = [
            self._row("tool", content="结果", tool_call_id="c1"),
            self._row("user", content="问"),
        ]
        out = cs._drop_orphaned_head_rows(rows)
        assert [r.role for r in out] == ["user"]

    def test_head_assistant_unanswered_calls_dropped(self):
        rows = [
            self._assistant_with_calls("c1"),
            self._row("user", content="问"),
        ]
        out = cs._drop_orphaned_head_rows(rows)
        assert [r.role for r in out] == ["user"]

    def test_answered_calls_kept(self):
        rows = [
            self._assistant_with_calls("c1"),
            self._row("tool", content="结果", tool_call_id="c1"),
            self._row("assistant", content="答"),
        ]
        out = cs._drop_orphaned_head_rows(rows)
        assert [r.role for r in out] == ["assistant", "tool", "assistant"]

    def test_consecutive_orphans_all_dropped(self):
        """开头连续孤儿：tool 行 + 应答被截的 assistant 行一并丢弃。"""
        rows = [
            self._row("tool", content="结果1", tool_call_id="c1"),
            self._row("tool", content="结果2", tool_call_id="c2"),
            self._assistant_with_calls("c3"),
            self._row("user", content="问"),
        ]
        out = cs._drop_orphaned_head_rows(rows)
        assert [r.role for r in out] == ["user"]

    def test_partially_answered_calls_dropped(self):
        """部分 tool_call_id 被截掉同样算孤儿（悬空调用不可回放）。"""
        rows = [
            self._assistant_with_calls("c1", "c2"),
            self._row("tool", content="结果", tool_call_id="c1"),
            self._row("user", content="问"),
        ]
        out = cs._drop_orphaned_head_rows(rows)
        assert [r.role for r in out] == ["user"]

    def test_normal_window_untouched(self):
        rows = [
            self._row("user", content="问"),
            self._row("assistant", content="答"),
        ]
        out = cs._drop_orphaned_head_rows(rows)
        assert [r.role for r in out] == ["user", "assistant"]

    @pytest.mark.asyncio
    async def test_history_rows_applies_head_drop(self):
        """_history_rows 尾部截断后实际执行孤儿行丢弃。"""

        class _AwaitableRows:
            """伪 QuerySet：order_by/limit 链式返回自身，await 得行列表。"""

            def __init__(self, rows):
                self._rows = rows

            def order_by(self, *a):
                return self

            def limit(self, *a):
                return self

            def __await__(self):
                async def _coro():
                    return self._rows

                return _coro().__await__()

        # order_by("-seq") 返回倒序（最新在前）：窗口头部即被截断的一侧
        desc_rows = [
            self._row("user", content="新问"),
            self._row("tool", content="孤儿结果", tool_call_id="c1"),
        ]
        with patch.object(
            KuaiaiChatMessage,
            "filter",
            MagicMock(return_value=_AwaitableRows(desc_rows)),
        ):
            rows = await cs._history_rows(TENANT, 1)
        assert [r.role for r in rows] == ["user"]
