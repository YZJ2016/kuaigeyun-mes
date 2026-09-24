"""KU-AI S2 单测：chat_service 路径 B（档案装配）+ tool 行落库 + 回放。

全部 mock Tortoise 查询与上游 LLM，不需要真实端点/数据库。覆盖：
- 无授权/停用/跨租户档案 send → 403/404，且不构造 agent、不触达上游
- 纯对话（无 agent_id、无 capability_mode=agent）不解析/不挂默认档案
- 选中档案忽略请求级模型覆盖（KR-F3）
- 路径 B 落 role=tool 行 + assistant.tool_calls（OpenAI 线格式），
  to_lc_messages 回放可重建 ToolMessage/AIMessage（AC#4）
- tool 结果 error ToolMessage 落库不 500
- lc_tool_calls_to_openai 与 normalize_tool_calls 双向形态
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import apps.kuaiai.services.agent_assembler as agent_assembler
import apps.kuaiai.services.chat_service as cs
from apps.kuaiai.models.agent import KuaiaiAgentProfile
from apps.kuaiai.models.chat import KuaiaiChatMessage
from apps.kuaiai.services.agent_assembler import AssembledAgent
from core.ai.runtime import memory
from infra.exceptions.exceptions import AuthorizationError, NotFoundError

TENANT = 7
USER_ID = 5
AGENT_ID = 3


def _user(uid: int = USER_ID):
    return SimpleNamespace(id=uid, full_name="测试用户", username="tester")


def _session(session_id: int = 1, user_id: int = USER_ID):
    s = SimpleNamespace(
        id=session_id,
        user_id=user_id,
        tenant_id=TENANT,
        model=None,
        title="",
        agent_id=None,
    )
    updates = []

    def _upd(data):
        updates.append(dict(data))
        s.__dict__.update(data)
        return s

    s.update_from_dict = MagicMock(side_effect=_upd)
    s.updates = updates
    s.save = AsyncMock()
    return s


def _profile(**over):
    base = dict(
        id=AGENT_ID,
        tenant_id=TENANT,
        name="档案3",
        system_prompt="你是助手",
        default_model_id=42,
        enabled_tools=["query_workorder"],
        status="启用",
        grant_mode="USER",
    )
    base.update(over)
    return SimpleNamespace(**base)


def _config(**over):
    base = dict(
        chat_api_key="fake-key",
        chat_base_url="https://llm.example.invalid",
        chat_model="fb-chat",
        custom_system_prompt=None,
        stream_enabled=True,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _patch_runtime_config(**over):
    return patch.object(
        cs.AiRuntimeConfig, "load", new=AsyncMock(return_value=_config(**over))
    )


@pytest.fixture(autouse=True)
def _no_catalog_source():
    """U-2 起 send 主路径先判定目录行命中；本文件用例默认目录行未命中，
    走 IntegrationConfig 兜底（AiRuntimeConfig.load 由各用例自 patch）。"""
    with patch.object(
        cs, "_resolve_catalog_source", new=AsyncMock(return_value=None)
    ):
        yield


class _FakeChat:
    """路径 A 用：build_chat_model 的替身（model_name + bind + ainvoke）。"""

    def __init__(self, model_name="fb-chat"):
        self.model_name = model_name
        self.bound_kwargs = None
        self.invoked_with = []

    def bind(self, **kwargs):
        self.bound_kwargs = kwargs
        return self

    async def ainvoke(self, messages):
        self.invoked_with.append(messages)
        return SimpleNamespace(
            content="路径A回答",
            id="chatcmpl-fake",
            usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            response_metadata={"finish_reason": "stop"},
        )


class _FakeAgent:
    """路径 B 非流式替身：ainvoke 返回终态 messages（输入 + 新增）。"""

    def __init__(self, new_messages):
        self._new = list(new_messages)
        self.invoked_with = None
        self.config = None

    async def ainvoke(self, payload, config=None):
        self.invoked_with = payload["messages"]
        self.config = config
        return {"messages": list(payload["messages"]) + self._new}


class _FakeStreamAgent(_FakeAgent):
    """路径 B 流式替身：astream_events 吐 chunk，并按真实运行时语义
    调 config.callbacks 的根 run on_chain_end（outputs=图终态）。"""

    def __init__(self, texts, new_messages):
        super().__init__(new_messages)
        self._texts = list(texts)
        self.streamed_with = None

    async def astream_events(self, payload, config=None, version=None):
        self.streamed_with = payload["messages"]
        for text in self._texts:
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": SimpleNamespace(content=text)},
            }
        for cb in (config or {}).get("callbacks", []):
            await cb.on_chain_end(
                {"messages": list(payload["messages"]) + self._new},
                run_id="root",
                parent_run_id=None,
            )


def _assembled(agent, model_name="profile-model", agent_id=AGENT_ID):
    return AssembledAgent(
        profile=_profile(id=agent_id), agent=agent, model_name=model_name
    )


class _FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _patch_tx():
    return patch.object(cs, "in_transaction", MagicMock(return_value=_FakeTx()))


def _capture_creates():
    """KuaiaiChatMessage.create 捕获 + 单调 seq。"""
    created = []

    async def _create(**kw):
        created.append(kw)
        return SimpleNamespace(**kw)

    seq = {"n": 0}

    async def _next(tenant_id, session_id):
        seq["n"] += 1
        return seq["n"]

    return created, _create, _next


def _tool_roundtrip_messages():
    """一轮工具调用的新增消息：AI(tool_calls) → Tool → AI(最终文本)。"""
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "query_workorder",
                    "args": {"work_order_id": 9},
                    "id": "call_1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content="工单 WO-9 状态：进行中",
            tool_call_id="call_1",
            name="query_workorder",
        ),
        AIMessage(
            content="工单 WO-9 目前进行中。",
            usage_metadata={
                "input_tokens": 11,
                "output_tokens": 7,
                "total_tokens": 18,
            },
        ),
    ]


# ------------------------------------------------------------------ assemble


class TestAssemble:
    @pytest.mark.asyncio
    async def test_no_grant_403_and_upstream_untouched(self):
        """无授权档案 → 403，build_chat_model/build_agent 均未调用。"""
        with (
            patch.object(
                KuaiaiAgentProfile,
                "get_or_none",
                new=AsyncMock(return_value=_profile()),
            ),
            patch.object(
                agent_assembler.grant_service,
                "check_use_grant",
                new=AsyncMock(return_value=False),
            ),
            patch.object(
                agent_assembler, "build_chat_model", new=AsyncMock()
            ) as mock_model,
            patch.object(
                agent_assembler, "build_agent", new=MagicMock()
            ) as mock_agent,
        ):
            with pytest.raises(AuthorizationError):
                await agent_assembler.assemble(
                    TENANT, _user(), False, False, AGENT_ID, agent_path=False
                )
        mock_model.assert_not_called()
        mock_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_profile_403(self):
        with patch.object(
            KuaiaiAgentProfile,
            "get_or_none",
            new=AsyncMock(return_value=_profile(status="停用")),
        ):
            with pytest.raises(AuthorizationError):
                await agent_assembler.assemble(
                    TENANT, _user(), False, False, AGENT_ID, agent_path=False
                )

    @pytest.mark.asyncio
    async def test_cross_tenant_profile_404(self):
        with patch.object(
            KuaiaiAgentProfile, "get_or_none", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await agent_assembler.assemble(
                    TENANT, _user(), False, False, 999, agent_path=False
                )

    @pytest.mark.asyncio
    async def test_no_agent_id_no_agent_path_returns_none(self):
        """纯对话：不查档案、不解析默认档案（默认档案存在也不挂）。"""
        with patch.object(
            KuaiaiAgentProfile,
            "get_or_none",
            new=AsyncMock(return_value=_profile()),
        ) as mock_get:
            out = await agent_assembler.assemble(
                TENANT, _user(), False, False, None, agent_path=False
            )
        assert out is None
        mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_agent_path_default_profile_same_grant_check(self):
        """agent 路径默认档案：按名称解析并同样过 check_use_grant。"""
        from apps.kuaiai.constants import DEFAULT_AGENT_PROFILE_NAME

        with (
            patch.object(
                KuaiaiAgentProfile,
                "get_or_none",
                new=AsyncMock(
                    return_value=_profile(
                        id=8, name=DEFAULT_AGENT_PROFILE_NAME
                    )
                ),
            ) as mock_get,
            patch.object(
                agent_assembler.grant_service,
                "check_use_grant",
                new=AsyncMock(return_value=True),
            ) as mock_grant,
            patch.object(
                agent_assembler,
                "build_chat_model",
                new=AsyncMock(return_value=SimpleNamespace(model_name="m8")),
            ),
            patch.object(
                agent_assembler,
                "registry_to_lc_tools",
                new=MagicMock(return_value=[]),
            ),
            patch.object(
                agent_assembler,
                "build_tool_guard_middleware",
                new=MagicMock(),
            ),
            patch.object(
                agent_assembler, "build_agent", new=MagicMock(return_value="agent-obj")
            ) as mock_agent,
        ):
            out = await agent_assembler.assemble(
                TENANT, _user(), False, False, None, agent_path=True
            )
        assert out is not None and out.profile.id == 8
        mock_get.assert_awaited_once()
        assert mock_get.await_args.kwargs["name"] == DEFAULT_AGENT_PROFILE_NAME
        mock_grant.assert_awaited_once()
        assert mock_agent.call_args.kwargs["system_prompt"] == "你是助手"

    @pytest.mark.asyncio
    async def test_agent_path_no_default_profile_returns_none(self):
        """agent 路径但无「默认助手」档案 → None，不编造/不种子。"""
        with patch.object(
            KuaiaiAgentProfile, "get_or_none", new=AsyncMock(return_value=None)
        ) as mock_get:
            out = await agent_assembler.assemble(
                TENANT, _user(), False, False, None, agent_path=True
            )
        assert out is None
        mock_get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_agent_path_disabled_default_profile_403(self):
        """agent 路径解析到停用默认档案 → 与显式 agent_id 同一 403。"""
        from apps.kuaiai.constants import DEFAULT_AGENT_PROFILE_NAME

        with patch.object(
            KuaiaiAgentProfile,
            "get_or_none",
            new=AsyncMock(
                return_value=_profile(
                    id=8, name=DEFAULT_AGENT_PROFILE_NAME, status="停用"
                )
            ),
        ):
            with pytest.raises(AuthorizationError):
                await agent_assembler.assemble(
                    TENANT, _user(), False, False, None, agent_path=True
                )

    @pytest.mark.asyncio
    async def test_tools_intersect_closed_set(self):
        """enabled_tools ∩ 五值闭集后交给 registry（脏名不进入装配）。"""
        with (
            patch.object(
                KuaiaiAgentProfile,
                "get_or_none",
                new=AsyncMock(
                    return_value=_profile(
                        enabled_tools=["query_workorder", "drop_table"]
                    )
                ),
            ),
            patch.object(
                agent_assembler.grant_service,
                "check_use_grant",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                agent_assembler,
                "build_chat_model",
                new=AsyncMock(return_value=SimpleNamespace(model_name="m")),
            ),
            patch.object(
                agent_assembler,
                "registry_to_lc_tools",
                new=MagicMock(return_value=[]),
            ) as mock_tools,
            patch.object(
                agent_assembler, "build_tool_guard_middleware", new=MagicMock()
            ),
            patch.object(
                agent_assembler, "build_agent", new=MagicMock(return_value="a")
            ),
        ):
            await agent_assembler.assemble(
                TENANT, _user(), False, False, AGENT_ID, agent_path=False
            )
        assert mock_tools.call_args.args[0] == ["query_workorder"]


# ------------------------------------------------- send 入口：授权与路径选择


class TestSendPathBGate:
    @pytest.mark.asyncio
    async def test_denied_profile_403_no_upstream(self):
        """无授权档案 send → 403；build_agent / 模型构造均未触达。"""
        with (
            patch.object(
                KuaiaiAgentProfile,
                "get_or_none",
                new=AsyncMock(return_value=_profile()),
            ),
            patch.object(
                agent_assembler.grant_service,
                "check_use_grant",
                new=AsyncMock(return_value=False),
            ),
            patch.object(
                agent_assembler, "build_agent", new=MagicMock()
            ) as mock_agent,
            patch.object(
                agent_assembler, "build_chat_model", new=AsyncMock()
            ) as mock_model,
            patch.object(
                cs, "build_chat_model", new=AsyncMock()
            ) as mock_path_a,
            _patch_runtime_config(),
        ):
            with pytest.raises(AuthorizationError):
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    user=_user(),
                    context={"agent_id": AGENT_ID},
                )
        mock_agent.assert_not_called()
        mock_model.assert_not_called()
        mock_path_a.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_profile_send_403(self):
        with (
            patch.object(
                KuaiaiAgentProfile,
                "get_or_none",
                new=AsyncMock(return_value=_profile(status="停用")),
            ),
            patch.object(
                agent_assembler, "build_agent", new=MagicMock()
            ) as mock_agent,
        ):
            with pytest.raises(AuthorizationError):
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    user=_user(),
                    context={"agent_id": str(AGENT_ID)},
                )
        mock_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_pure_chat_never_assembles(self):
        """纯对话（无 agent_id、无 capability_mode=agent）：assemble 不被调，
        默认档案存在也不自动挂。"""
        chat = _FakeChat()
        with (
            patch.object(cs, "assemble", new=AsyncMock()) as mock_assemble,
            patch.object(
                KuaiaiAgentProfile,
                "get_or_none",
                new=AsyncMock(return_value=_profile()),
            ) as mock_profile_get,
            patch.object(
                cs, "build_chat_model", new=AsyncMock(return_value=chat)
            ),
            _patch_runtime_config(),
        ):
            result = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "hi"}],
                user=_user(),
                context=None,
            )
        assert result["choices"][0]["message"]["content"] == "路径A回答"
        mock_assemble.assert_not_called()
        mock_profile_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_capability_mode_agent_triggers_assembly(self):
        """capability_mode=='agent'（agent 路径标记）→ assemble(agent_path=True)。"""
        chat = _FakeChat()
        with (
            patch.object(
                cs, "assemble", new=AsyncMock(return_value=None)
            ) as mock_assemble,
            patch.object(
                cs, "build_chat_model", new=AsyncMock(return_value=chat)
            ),
            _patch_runtime_config(),
        ):
            result = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "hi"}],
                user=_user(),
                context={"extra": {"capability_mode": "agent"}},
            )
        assert result["object"] == "chat.completion"
        mock_assemble.assert_awaited_once()
        assert mock_assemble.await_args.kwargs["agent_path"] is True
        assert mock_assemble.await_args.args[4] is None

    @pytest.mark.asyncio
    async def test_profile_ignores_request_level_model(self):
        """KR-F3：选中档案只用 default_model_id，请求级 model 覆盖被忽略。"""
        fake_agent = _FakeAgent([AIMessage(content="档案回答")])
        with (
            patch.object(
                KuaiaiAgentProfile,
                "get_or_none",
                new=AsyncMock(return_value=_profile(default_model_id=42)),
            ),
            patch.object(
                agent_assembler.grant_service,
                "check_use_grant",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                agent_assembler,
                "build_chat_model",
                new=AsyncMock(
                    return_value=SimpleNamespace(model_name="profile-model")
                ),
            ) as mock_model,
            patch.object(
                agent_assembler,
                "registry_to_lc_tools",
                new=MagicMock(return_value=[]),
            ),
            patch.object(
                agent_assembler, "build_tool_guard_middleware", new=MagicMock()
            ),
            patch.object(
                agent_assembler,
                "build_agent",
                new=MagicMock(return_value=fake_agent),
            ),
            patch.object(cs, "build_chat_model", new=AsyncMock()) as mock_pa,
            _patch_runtime_config(),
        ):
            result = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "hi"}],
                model="request-override-model",
                user=_user(),
                context={"agent_id": AGENT_ID},
            )
        # 档案模型解析用的是 profile.default_model_id，而非请求 model 名
        mock_model.assert_awaited_once_with(TENANT, 42)
        mock_pa.assert_not_called()
        assert result["model"] == "profile-model"
        assert result["choices"][0]["message"]["content"] == "档案回答"

    @pytest.mark.asyncio
    async def test_agent_upstream_failure_is_502(self):
        """n2：路径 B 上游 ainvoke 失败 → ExternalServiceError（502 语义），
        不泄露上游细节。"""
        from infra.exceptions.exceptions import ExternalServiceError

        class _BoomAgent:
            async def ainvoke(self, payload, config=None):
                raise RuntimeError("Connection error: api_key=sk-xxx")

        with (
            patch.object(
                cs,
                "assemble",
                new=AsyncMock(return_value=_assembled(_BoomAgent())),
            ),
            _patch_runtime_config(),
        ):
            with pytest.raises(ExternalServiceError) as excinfo:
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    user=_user(),
                    context={"agent_id": AGENT_ID},
                )
        assert excinfo.value.status_code == 502
        assert "sk-xxx" not in str(excinfo.value.message)


# --------------------------------------------------------------- 落库 / 回放


class TestAgentRunPersistence:
    @pytest.mark.asyncio
    async def test_tool_rows_and_openai_wire_tool_calls(self):
        """路径 B 非流式：tool 行 + assistant.tool_calls（OpenAI 线格式）落库，
        seq 按发生序（user → assistant(calls) → tool → assistant(final)）。"""
        created, _create, _next = _capture_creates()
        session = _session()
        agent = _FakeAgent(_tool_roundtrip_messages())

        with (
            patch.object(
                cs, "get_owned_session", new=AsyncMock(return_value=session)
            ),
            patch.object(cs, "_history_rows", new=AsyncMock(return_value=[])),
            patch.object(cs, "assemble", new=AsyncMock(return_value=_assembled(agent))),
            patch.object(cs, "_lock_session_row", new=AsyncMock(return_value=session)),
            patch.object(cs, "_next_seq", new=_next),
            patch.object(KuaiaiChatMessage, "create", new=AsyncMock(side_effect=_create)),
            _patch_tx(),
            _patch_runtime_config(),
        ):
            result = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "查工单"}],
                user=_user(),
                context={"session_id": 1, "agent_id": AGENT_ID},
            )

        roles = [r["role"] for r in created]
        assert roles == ["user", "assistant", "tool", "assistant"]
        assert [r["seq"] for r in created] == [1, 2, 3, 4]

        # assistant 行 tool_calls 存 OpenAI 线格式
        calls = created[1]["tool_calls"]
        assert calls == [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "query_workorder",
                    "arguments": json.dumps(
                        {"work_order_id": 9}, ensure_ascii=False
                    ),
                },
            }
        ]
        # tool 行
        assert created[2]["tool_call_id"] == "call_1"
        assert created[2]["tool_name"] == "query_workorder"
        assert "WO-9" in created[2]["content"]
        # token 回填到最后一条 assistant 行
        assert created[3]["prompt_tokens"] == 11
        assert created[3]["completion_tokens"] == 7
        # 会话回写 agent_id
        assert any(u.get("agent_id") == AGENT_ID for u in session.updates)
        assert result["choices"][0]["message"]["content"] == "工单 WO-9 目前进行中。"
        assert result["usage"]["total_tokens"] == 18

        # 回放：行形态经 to_lc_messages 重建 ToolMessage/AIMessage
        rows = [
            SimpleNamespace(
                role=r["role"],
                content=r.get("content"),
                tool_calls=r.get("tool_calls"),
                tool_call_id=r.get("tool_call_id"),
                tool_name=r.get("tool_name"),
            )
            for r in created
        ]
        msgs = memory.to_lc_messages(rows)
        assert isinstance(msgs[0], HumanMessage)
        assert isinstance(msgs[1], AIMessage)
        assert msgs[1].tool_calls[0]["name"] == "query_workorder"
        assert msgs[1].tool_calls[0]["args"] == {"work_order_id": 9}
        assert isinstance(msgs[2], ToolMessage)
        assert msgs[2].tool_call_id == "call_1"
        assert msgs[2].name == "query_workorder"
        assert isinstance(msgs[3], AIMessage)
        assert msgs[3].content == "工单 WO-9 目前进行中。"

    @pytest.mark.asyncio
    async def test_tool_error_message_persisted_not_500(self):
        """tool 结果 status=error 的 ToolMessage 照常落 tool 行，send 不 500。"""
        created, _create, _next = _capture_creates()
        session = _session()
        agent = _FakeAgent(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "query_workorder",
                            "args": {},
                            "id": "call_e",
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(
                    content="工具 query_workorder 执行失败",
                    tool_call_id="call_e",
                    name="query_workorder",
                    status="error",
                ),
                AIMessage(content="查询失败了，请稍后重试。"),
            ]
        )
        with (
            patch.object(
                cs, "get_owned_session", new=AsyncMock(return_value=session)
            ),
            patch.object(cs, "_history_rows", new=AsyncMock(return_value=[])),
            patch.object(cs, "assemble", new=AsyncMock(return_value=_assembled(agent))),
            patch.object(cs, "_lock_session_row", new=AsyncMock(return_value=session)),
            patch.object(cs, "_next_seq", new=_next),
            patch.object(KuaiaiChatMessage, "create", new=AsyncMock(side_effect=_create)),
            _patch_tx(),
            _patch_runtime_config(),
        ):
            result = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "查"}],
                user=_user(),
                context={"session_id": 1, "agent_id": AGENT_ID},
            )
        assert result["object"] == "chat.completion"
        tool_rows = [r for r in created if r["role"] == "tool"]
        assert len(tool_rows) == 1
        assert "执行失败" in tool_rows[0]["content"]

    @pytest.mark.asyncio
    async def test_streaming_path_b_persists_tool_rows(self):
        """路径 B 流式：astream_events 帧转 OpenAI chunk + [DONE]；
        工具轨迹经 config.callbacks 终态收集落库。"""
        created, _create, _next = _capture_creates()
        session = _session()
        agent = _FakeStreamAgent(["工单 WO-9 ", "进行中"], _tool_roundtrip_messages())

        with (
            patch.object(
                cs, "get_owned_session", new=AsyncMock(return_value=session)
            ),
            patch.object(cs, "_history_rows", new=AsyncMock(return_value=[])),
            patch.object(cs, "assemble", new=AsyncMock(return_value=_assembled(agent))),
            patch.object(cs, "_lock_session_row", new=AsyncMock(return_value=session)),
            patch.object(cs, "_next_seq", new=_next),
            patch.object(KuaiaiChatMessage, "create", new=AsyncMock(side_effect=_create)),
            patch(
                "core.services.realtime.ai_stream_bridge.schedule_user_realtime_event",
                new=MagicMock(),
            ),
            _patch_tx(),
            _patch_runtime_config(),
        ):
            resp = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "查工单"}],
                stream=True,
                user=_user(),
                context={"session_id": 1, "agent_id": AGENT_ID},
            )
            assert isinstance(resp, StreamingResponse)
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
        assert deltas == ["工单 WO-9 ", "进行中"]
        assert payloads[0]["model"] == "profile-model"

        roles = [r["role"] for r in created]
        assert roles == ["user", "assistant", "tool", "assistant"]
        assert created[2]["tool_call_id"] == "call_1"
        assert created[1]["tool_calls"][0]["function"]["name"] == "query_workorder"


# ------------------------------------------------------- lc_tool_calls_to_openai


class TestToolCallsWireRoundtrip:
    def test_lc_to_openai_wire(self):
        lc = [{"name": "t", "args": {"a": 1}, "id": "c1", "type": "tool_call"}]
        out = memory.lc_tool_calls_to_openai(lc)
        assert out == [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "t", "arguments": '{"a": 1}'},
            }
        ]

    def test_lc_to_openai_roundtrip_back(self):
        lc = [{"name": "t", "args": {"a": 1}, "id": "c1", "type": "tool_call"}]
        back = memory.normalize_tool_calls(memory.lc_tool_calls_to_openai(lc))
        assert back[0]["name"] == "t"
        assert back[0]["args"] == {"a": 1}
        assert back[0]["id"] == "c1"

    def test_openai_wire_to_lc_and_back(self):
        wire = [
            {
                "id": "c9",
                "type": "function",
                "function": {"name": "f", "arguments": '{"x": "y"}'},
            }
        ]
        lc = memory.normalize_tool_calls(wire)
        assert lc[0]["name"] == "f" and lc[0]["args"] == {"x": "y"}
        out = memory.lc_tool_calls_to_openai(lc)
        assert out[0]["id"] == "c9"
        assert out[0]["type"] == "function"
        assert json.loads(out[0]["function"]["arguments"]) == {"x": "y"}
        assert out[0]["function"]["name"] == "f"

    def test_openai_wire_input_passthrough(self):
        wire = [
            {
                "id": "c2",
                "type": "function",
                "function": {"name": "g", "arguments": "{}"},
            }
        ]
        assert memory.lc_tool_calls_to_openai(wire) == wire

    def test_non_list_and_junk(self):
        assert memory.lc_tool_calls_to_openai(None) == []
        assert memory.lc_tool_calls_to_openai([None, "x", {"args": {}}]) == []
