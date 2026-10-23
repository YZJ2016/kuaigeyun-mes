"""KU-AI spec 193 单测：HITL 人工确认闸（kind=write → LangGraph interrupt）。

与既有多数用例不同：本文件跑**真实装配**——真 ``create_agent`` 编译图 +
真 ``HumanInTheLoopMiddleware`` + 真 ``TortoiseCheckpointSaver``（sqlite
内存库落真实 checkpoint 行），仅替身 LLM（队列模型）与写 Tool handler、
穿透 guard（RBAC 由 spec 185/187 既有用例覆盖）。覆盖：

- 确认前业务数据不执行（interrupt + kuaiai_interrupt SSE 帧）
- approve 经 Command(resume) 后真实执行 + tool/assistant 落库 + 审计
- reject / 新消息拒绝（H2）/ 过期拒绝（H3）
- TTL 配置读取失败失败关闭；无会话写调用拒绝（H1）
- H4 决策闭集校验；thread_token 伪造/越权 404
- 信任中心三条件真实装配判定
"""

from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.responses import StreamingResponse
from langchain.agents.middleware import wrap_tool_call
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import StructuredTool
from pydantic import BaseModel
from tortoise import Tortoise

import apps.kuaiai.services.agent_assembler as agent_assembler
import apps.kuaiai.services.chat_service as cs
import apps.kuaiai.services.hitl_service as hs
from apps.kuaiai.models.chat import KuaiaiChatMessage, KuaiaiChatSession
from core.models.ai_audit_log import AiAuditLog
from infra.domain.tenant_context import clear_tenant_context, with_tenant
from infra.exceptions.exceptions import (
    BusinessLogicError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from infra.models.tenant_config import TenantConfig

TENANT = 7
USER_ID = 5
AGENT_ID = 3
WRITE_TOOL = "submit_production_feedback"

_MODULES = {
    "models": [
        "apps.kuaiai.models.chat",
        "apps.kuaiai.models.checkpoint",
        "core.models.ai_audit_log",
        "infra.models.tenant_config",
    ]
}


@pytest_asyncio.fixture
async def db():
    clear_tenant_context()
    await Tortoise.init(db_url="sqlite://:memory:", modules=_MODULES)
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        clear_tenant_context()
        await Tortoise.close_connections()


# ---------------------------------------------------------------- 替身件


def _user(uid: int = USER_ID):
    return SimpleNamespace(
        id=uid, full_name="测试用户", username="tester"
    )


class _QueueChatModel(BaseChatModel):
    """队列响应的对话模型替身：bind_tools 返回自身，按序吐 AIMessage。"""

    queue: List[BaseMessage]
    idx: int = 0
    model_name: str = "fake-hitl-model"

    @property
    def _llm_type(self) -> str:
        return "queue-chat-model"

    def bind_tools(self, tools: Any, **kwargs: Any):
        return self

    def _next(self) -> BaseMessage:
        if self.idx >= len(self.queue):
            raise IndexError("fake model queue exhausted")
        msg = self.queue[self.idx]
        self.idx += 1
        return msg

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(
            generations=[ChatGeneration(message=self._next())]
        )

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(
            messages, stop=stop, run_manager=run_manager, **kwargs
        )

    @staticmethod
    def _as_chunk(msg: BaseMessage) -> ChatGenerationChunk:
        if isinstance(msg, AIMessage):
            # 走 tool_call_chunks 聚合标准路径（args 为 JSON 串）→
            # 终态消息得到 tool_calls，触发 HITL after_model 中断
            tcc = list(getattr(msg, "tool_call_chunks", None) or [])
            if not tcc and msg.tool_calls:
                tcc = [
                    {
                        "name": c.get("name"),
                        "args": json.dumps(
                            c.get("args") or {}, ensure_ascii=False
                        ),
                        "id": c.get("id"),
                        "index": i,
                        "type": "tool_call_chunk",
                    }
                    for i, c in enumerate(msg.tool_calls)
                ]
            chunk = AIMessageChunk(
                content=msg.content,
                tool_call_chunks=tcc,
            )
        else:
            chunk = AIMessageChunk(content=str(getattr(msg, "content", "")))
        return ChatGenerationChunk(message=chunk)

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        yield self._as_chunk(self._next())

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        yield self._as_chunk(self._next())


def _tool_call_ai(name: str = WRITE_TOOL, call_id: str = "call_w1") -> AIMessage:
    args = {"work_order_id": 9, "operation_id": 11, "reported_quantity": 5}
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": call_id, "type": "tool_call"}
        ],
    )


def _final_ai(text: str = "已处理完毕") -> AIMessage:
    return AIMessage(
        content=text,
        usage_metadata={
            "input_tokens": 10,
            "output_tokens": 4,
            "total_tokens": 14,
        },
    )


class _WriteToolArgs(BaseModel):
    work_order_id: int = 0
    operation_id: int = 0
    reported_quantity: float = 0


def _write_tool(calls_log: List[Dict[str, Any]]) -> StructuredTool:
    async def _handler(**kwargs: Any) -> str:
        calls_log.append(dict(kwargs))
        return "报工已提交"

    return StructuredTool(
        name=WRITE_TOOL,
        description="测试报工写工具",
        coroutine=_handler,
        args_schema=_WriteToolArgs,
    )


def _passthrough_guard():
    @wrap_tool_call
    async def _g(request, handler):
        return await handler(request)

    return _g


def _profile(**over) -> SimpleNamespace:
    base = dict(
        id=AGENT_ID,
        tenant_id=TENANT,
        name="写档案",
        system_prompt="你是助手",
        default_model_id=42,
        enabled_tools=[WRITE_TOOL],
        status="启用",
        grant_mode="USER",
        mcp_server_ids=None,
        knowledge_ids=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _assemble_patches(model, tools, profile=None):
    return (
        patch.object(
            agent_assembler.KuaiaiAgentProfile,
            "get_or_none",
            new=AsyncMock(return_value=profile or _profile()),
        ),
        patch.object(
            agent_assembler.grant_service,
            "check_use_grant",
            new=AsyncMock(return_value=True),
        ),
        patch.object(
            agent_assembler,
            "build_chat_model",
            new=AsyncMock(return_value=model),
        ),
        patch.object(
            agent_assembler,
            "registry_to_lc_tools",
            new=MagicMock(return_value=list(tools)),
        ),
        patch.object(
            agent_assembler,
            "build_mcp_aware_tool_guard",
            new=MagicMock(return_value=_passthrough_guard()),
        ),
    )


async def _passthrough_wrap(stream, **kwargs):
    async for chunk in stream:
        yield chunk


def _send_patches():
    return (
        patch.object(
            cs,
            "_resolve_catalog_source",
            new=AsyncMock(return_value=SimpleNamespace(id=1)),
        ),
        patch(
            "core.services.realtime.ai_stream_bridge.wrap_ai_sse_stream",
            new=_passthrough_wrap,
        ),
    )


async def _make_session(user_id: int = USER_ID) -> KuaiaiChatSession:
    return await KuaiaiChatSession.create(
        tenant_id=TENANT, user_id=user_id, title=""
    )


async def _consume(resp: StreamingResponse) -> bytes:
    parts = [chunk async for chunk in resp.body_iterator]
    return b"".join(
        p if isinstance(p, bytes) else str(p).encode() for p in parts
    )


def _sse_frames(raw: bytes) -> List[Dict[str, Any]]:
    out = []
    for part in raw.decode("utf-8").split("\n\n"):
        part = part.strip()
        if not part.startswith("data: ") or part == "data: [DONE]":
            continue
        out.append(json.loads(part[len("data: ") :]))
    return out


def _interrupt_frame(frames: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for frame in frames:
        if frame.get("kuaiai_interrupt"):
            return frame["kuaiai_interrupt"]
    return None


async def _send_to_interrupt(
    session: KuaiaiChatSession,
    calls_log: List[Dict[str, Any]],
    *,
    queue: Optional[List[BaseMessage]] = None,
):
    """一次流式发送 → 挂起；返回 (interrupt_frame, model)。"""
    model = _QueueChatModel(queue=queue or [_tool_call_ai(), _final_ai()])
    p1, p2, p3, p4, p5 = _assemble_patches(model, [_write_tool(calls_log)])
    s1, s2 = _send_patches()
    with p1, p2, p3, p4, p5, s1, s2:
        resp = await cs.create_chat_completion(
            TENANT,
            [{"role": "user", "content": "帮我给 WO-9 报工 5 件"}],
            stream=True,
            user=_user(),
            context={"session_id": session.id, "agent_id": AGENT_ID},
        )
        assert isinstance(resp, StreamingResponse)
        frames = _sse_frames(await _consume(resp))
    return _interrupt_frame(frames), model


async def _msg_rows(session_id: int) -> List[KuaiaiChatMessage]:
    return await (
        KuaiaiChatMessage.filter(tenant_id=TENANT, session_id=session_id)
        .order_by("seq")
        .all()
    )


async def _confirm_audits() -> List[AiAuditLog]:
    return await (
        AiAuditLog.filter(tenant_id=TENANT, capability="tool_confirm")
        .order_by("id")
        .all()
    )


def _thread_prefix(session_id: int) -> str:
    """会话挂起线程前缀（thread_id 末段为每次挂起的随机 nonce）。"""
    return hs.session_thread_prefix(TENANT, USER_ID, session_id)


async def _checkpoint_exists(session_id: int) -> bool:
    from apps.kuaiai.models.checkpoint import KuaiaiAgentCheckpoint

    return await KuaiaiAgentCheckpoint.filter(
        tenant_id=TENANT, thread_id__startswith=_thread_prefix(session_id)
    ).exists()


async def _pending_thread_id(thread_token: str) -> str:
    """token 内含完整 thread_id（含 nonce），解析取出供断言/认领用。"""
    parsed = hs.parse_thread_token(thread_token)
    assert parsed is not None
    return parsed[3]


# ================================================================= 发送闸


@pytest.mark.asyncio
class TestInterruptGate:
    async def test_write_tool_interrupts_before_execute(self, db):
        """kind=write → SSE 下发 kuaiai_interrupt，Tool 未执行，checkpoint 挂起。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            calls: List[Dict[str, Any]] = []
            frame, _ = await _send_to_interrupt(session, calls)

            assert frame is not None, "缺少 kuaiai_interrupt 扩展帧"
            assert frame["thread_token"]
            assert frame["expires_at"]
            assert len(frame["actions"]) == 1
            action = frame["actions"][0]
            assert action["tool"] == WRITE_TOOL
            assert action["label"]
            assert "work_order_id" in action["args_summary"]

            assert calls == [], "确认前写 Tool 绝不可执行"
            assert await _checkpoint_exists(session.id)

            rows = await _msg_rows(session.id)
            roles = [r.role for r in rows]
            assert roles == ["user", "assistant"]
            assert rows[-1].tool_calls, "assistant 行应存 tool_calls"
            assert not any(r.role == "tool" for r in rows), "确认前不落 tool 行"

    async def test_approve_executes_and_audits(self, db):
        """approve → 同一 run 续跑执行写 Tool，tool+assistant 落库，记审计。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            calls: List[Dict[str, Any]] = []
            frame, _ = await _send_to_interrupt(session, calls)
            assert frame is not None

            model2 = _QueueChatModel(queue=[_final_ai("报工完成")])
            p1, p2, p3, p4, p5 = _assemble_patches(
                model2, [_write_tool(calls)]
            )
            s1, s2 = _send_patches()
            with p1, p2, p3, p4, p5, s1, s2:
                resp = await cs.resume_chat_completion(
                    TENANT,
                    thread_token=frame["thread_token"],
                    decisions=[{"type": "approve"}],
                    stream=True,
                    user=_user(),
                )
                frames = _sse_frames(await _consume(resp))

            assert len(calls) == 1 and calls[0]["work_order_id"] == 9
            assert _interrupt_frame(frames) is None

            rows = await _msg_rows(session.id)
            roles = [r.role for r in rows]
            assert roles == ["user", "assistant", "tool", "assistant"]
            assert rows[2].tool_name == WRITE_TOOL
            assert rows[2].tool_call_id == "call_w1"
            assert "报工已提交" in rows[2].content
            assert rows[3].content == "报工完成"

            audits = await _confirm_audits()
            assert [a.route for a in audits] == [
                f"ai/tool/{WRITE_TOOL}/approve"
            ]
            assert audits[0].user_id == USER_ID
            assert not await _checkpoint_exists(session.id), (
                "完成运行应清线程"
            )

    async def test_reject_skips_execute_and_audits(self, db):
        """reject → 写 Tool 不执行，收口 tool 行落库，reject 审计。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            calls: List[Dict[str, Any]] = []
            frame, _ = await _send_to_interrupt(session, calls)

            model2 = _QueueChatModel(queue=[_final_ai("好的，已取消")])
            p1, p2, p3, p4, p5 = _assemble_patches(
                model2, [_write_tool(calls)]
            )
            s1, s2 = _send_patches()
            with p1, p2, p3, p4, p5, s1, s2:
                resp = await cs.resume_chat_completion(
                    TENANT,
                    thread_token=frame["thread_token"],
                    decisions=[{"type": "reject", "message": "先不报"}],
                    stream=True,
                    user=_user(),
                )
                await _consume(resp)

            assert calls == [], "reject 后写 Tool 不可执行"
            rows = await _msg_rows(session.id)
            tool_rows = [r for r in rows if r.role == "tool"]
            assert len(tool_rows) == 1
            audits = await _confirm_audits()
            assert [a.route for a in audits] == [
                f"ai/tool/{WRITE_TOOL}/reject"
            ]
            assert not await _checkpoint_exists(session.id)

    async def test_nonstream_send_auto_rejects(self, db):
        """非流式不支持确认交互 → 失败关闭自动拒绝（reject 审计）。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            calls: List[Dict[str, Any]] = []
            model = _QueueChatModel(
                queue=[_tool_call_ai(), _final_ai("已取消该操作")]
            )
            p1, p2, p3, p4, p5 = _assemble_patches(
                model, [_write_tool(calls)]
            )
            s1, s2 = _send_patches()
            with p1, p2, p3, p4, p5, s1, s2:
                result = await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "报工 5 件"}],
                    stream=False,
                    user=_user(),
                    context={"session_id": session.id, "agent_id": AGENT_ID},
                )
            assert isinstance(result, dict)
            assert calls == [], "非流式确认闸未生效，写 Tool 被执行了"
            audits = await _confirm_audits()
            assert [a.route for a in audits] == [
                f"ai/tool/{WRITE_TOOL}/reject"
            ]
            assert not await _checkpoint_exists(session.id)


# ---------------------------------------------------------------- H1/H2/H3


@pytest.mark.asyncio
class TestSessionAndClose:
    async def test_write_profile_requires_session(self, db):
        """H1：无会话 + 写类档案 → BusinessLogicError（不构造 agent/不触上游）。"""
        async with with_tenant(TENANT):
            calls: List[Dict[str, Any]] = []
            model = _QueueChatModel(queue=[_final_ai()])
            p1, p2, p3, p4, p5 = _assemble_patches(
                model, [_write_tool(calls)]
            )
            s1, s2 = _send_patches()
            build_agent_mock = MagicMock()
            with p1, p2, p3, p4, p5, s1, s2, patch.object(
                agent_assembler, "build_agent", new=build_agent_mock
            ):
                with pytest.raises(BusinessLogicError) as exc_info:
                    await cs.create_chat_completion(
                        TENANT,
                        [{"role": "user", "content": "报工"}],
                        stream=True,
                        user=_user(),
                        context={"agent_id": AGENT_ID},
                    )
            assert "写操作需要会话" in str(exc_info.value)
            build_agent_mock.assert_not_called()

    async def test_new_message_rejects_pending(self, db):
        """H2：挂起期间同会话新消息 → 拒绝收口 + reject 审计 + 写不执行。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            calls: List[Dict[str, Any]] = []
            frame, _ = await _send_to_interrupt(session, calls)
            assert frame is not None

            model2 = _QueueChatModel(queue=[_final_ai("新问题回答")])
            p1, p2, p3, p4, p5 = _assemble_patches(
                model2, [_write_tool(calls)]
            )
            s1, s2 = _send_patches()
            with p1, p2, p3, p4, p5, s1, s2:
                resp = await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "先别管，查个库存"}],
                    stream=True,
                    user=_user(),
                    context={"session_id": session.id, "agent_id": AGENT_ID},
                )
                await _consume(resp)

            assert calls == [], "新消息到来后挂起写调用绝不可执行"
            rows = await _msg_rows(session.id)
            tool_rows = [r for r in rows if r.role == "tool"]
            assert len(tool_rows) == 1
            assert "用户未确认" in tool_rows[0].content
            audits = await _confirm_audits()
            assert [a.route for a in audits] == [
                f"ai/tool/{WRITE_TOOL}/reject"
            ]
            assert not await _checkpoint_exists(session.id)

    async def test_expired_pending_lazy_resume_404(self, db):
        """H3：挂起超 TTL → resume 404 + expire 审计 + 清线程。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            calls: List[Dict[str, Any]] = []
            frame, _ = await _send_to_interrupt(session, calls)

            future = cs.now_utc() + timedelta(minutes=31)
            with patch.object(cs, "now_utc", return_value=future):
                with pytest.raises(NotFoundError):
                    await cs.resume_chat_completion(
                        TENANT,
                        thread_token=frame["thread_token"],
                        decisions=[{"type": "approve"}],
                        stream=True,
                        user=_user(),
                    )
            assert calls == []
            audits = await _confirm_audits()
            assert [a.route for a in audits] == [
                f"ai/tool/{WRITE_TOOL}/expire"
            ]
            assert not await _checkpoint_exists(session.id)

    async def test_ttl_config_read_failure_fail_closed(self, db):
        """H3：TTL 读取异常 → 失败关闭（不落库、不运行、不猜默认值）。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            calls: List[Dict[str, Any]] = []
            model = _QueueChatModel(queue=[_tool_call_ai(), _final_ai()])
            p1, p2, p3, p4, p5 = _assemble_patches(
                model, [_write_tool(calls)]
            )
            s1, s2 = _send_patches()
            with p1, p2, p3, p4, p5, s1, s2, patch(
                "infra.services.tenant_service.TenantService.get_tenant_config",
                new=AsyncMock(side_effect=RuntimeError("db down")),
            ):
                with pytest.raises(BusinessLogicError) as exc_info:
                    await cs.create_chat_completion(
                        TENANT,
                        [{"role": "user", "content": "报工"}],
                        stream=True,
                        user=_user(),
                        context={
                            "session_id": session.id,
                            "agent_id": AGENT_ID,
                        },
                    )
            assert "确认闸配置读取失败" in str(exc_info.value)
            assert calls == []
            rows = await _msg_rows(session.id)
            assert rows == [], "失败关闭路径不得落 user 行"


@pytest.mark.asyncio
class TestTtlConfig:
    async def test_default_and_valid_and_invalid(self, db):
        async with with_tenant(TENANT):
            # 行缺失 → 30
            assert await hs.pending_ttl_minutes(TENANT) == 30
            # 合法值
            await TenantConfig.create(
                tenant_id=TENANT,
                config_key=hs.HITL_TTL_CONFIG_KEY,
                config_value={"minutes": 60},
            )
            assert await hs.pending_ttl_minutes(TENANT) == 60
            # 越界 → 30
            cfg = await TenantConfig.get(
                tenant_id=TENANT, config_key=hs.HITL_TTL_CONFIG_KEY
            )
            cfg.config_value = {"minutes": 9999}
            await cfg.save()
            assert await hs.pending_ttl_minutes(TENANT) == 30
            # 值类型非法 → 30
            cfg.config_value = {"minutes": "abc"}
            await cfg.save()
            assert await hs.pending_ttl_minutes(TENANT) == 30
            # 缺 minutes 键 → 30
            cfg.config_value = {"other": 1}
            await cfg.save()
            assert await hs.pending_ttl_minutes(TENANT) == 30

    async def test_read_exception_raises(self, db):
        async with with_tenant(TENANT):
            with patch(
                "infra.services.tenant_service.TenantService.get_tenant_config",
                new=AsyncMock(side_effect=KeyError("x")),
            ):
                with pytest.raises(BusinessLogicError):
                    await hs.pending_ttl_minutes(TENANT)


# ---------------------------------------------------------------- H4 / token


@pytest.mark.asyncio
class TestResumeValidation:
    async def test_invalid_decision_type_rejected(self, db):
        """H4：非 approve/reject → ValidationError（HTTP 层 schema 422）。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            calls: List[Dict[str, Any]] = []
            frame, _ = await _send_to_interrupt(session, calls)
            with pytest.raises(ValidationError):
                await cs.resume_chat_completion(
                    TENANT,
                    thread_token=frame["thread_token"],
                    decisions=[{"type": "edit"}],
                    stream=True,
                    user=_user(),
                )
            assert calls == []
            assert await _confirm_audits() == []
            assert await _checkpoint_exists(session.id)

    async def test_decision_count_must_match(self, db):
        async with with_tenant(TENANT):
            session = await _make_session()
            calls: List[Dict[str, Any]] = []
            frame, _ = await _send_to_interrupt(session, calls)
            with pytest.raises(ValidationError):
                await cs.resume_chat_completion(
                    TENANT,
                    thread_token=frame["thread_token"],
                    decisions=[],
                    stream=True,
                    user=_user(),
                )
            with pytest.raises(ValidationError):
                await cs.resume_chat_completion(
                    TENANT,
                    thread_token=frame["thread_token"],
                    decisions=[{"type": "approve"}, {"type": "reject"}],
                    stream=True,
                    user=_user(),
                )

    async def test_token_forgery_and_cross_user_404(self, db):
        """token HMAC 校验 + tenant/user 归属：伪造/越权一律 404。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            calls: List[Dict[str, Any]] = []
            frame, _ = await _send_to_interrupt(session, calls)
            token = frame["thread_token"]

            with pytest.raises(NotFoundError):
                await cs.resume_chat_completion(
                    TENANT,
                    thread_token=token[:-4] + "ffff",
                    decisions=[{"type": "approve"}],
                    stream=True,
                    user=_user(),
                )
            with pytest.raises(NotFoundError):
                await cs.resume_chat_completion(
                    TENANT,
                    thread_token=token,
                    decisions=[{"type": "approve"}],
                    stream=True,
                    user=_user(uid=999),
                )
            other_session_token = hs.issue_thread_token(
                hs.build_thread_id(TENANT, USER_ID, session.id + 100)
            )
            with pytest.raises(NotFoundError):
                await cs.resume_chat_completion(
                    TENANT,
                    thread_token=other_session_token,
                    decisions=[{"type": "approve"}],
                    stream=True,
                    user=_user(),
                )
            with pytest.raises(NotFoundError):
                await cs.resume_chat_completion(
                    TENANT + 1,
                    thread_token=token,
                    decisions=[{"type": "approve"}],
                    stream=True,
                    user=_user(),
                )
            # 挂起仍未被触碰
            assert calls == []
            assert await _checkpoint_exists(session.id)
            assert await _confirm_audits() == []

    async def test_unknown_thread_404(self, db):
        async with with_tenant(TENANT):
            session = await _make_session()
            token = hs.issue_thread_token(hs.build_thread_id(TENANT, USER_ID, session.id))
            with pytest.raises(NotFoundError):
                await cs.resume_chat_completion(
                    TENANT,
                    thread_token=token,
                    decisions=[{"type": "approve"}],
                    stream=True,
                    user=_user(),
                )


# ------------------------------------------------------------- 信任中心


@pytest.mark.asyncio
class TestTrustHitlState:
    async def test_hitl_feature_state_ready(self, db):
        """三条件全真（中断配置 + saver 装配 + resume 端点）→ implemented。"""
        from apps.kuaiai.services import operations_service as ops

        state = ops._hitl_feature_state()
        assert state["implemented"] is True
        assert state["mode"] == "human_gate"
        assert len(state["evidence"]) == 3
        assert state["interrupt_wired"] and state["saver_wired"]
        assert state["resume_route_found"]

    async def test_trust_hitl_card_ready(self, db):
        """get_trust HITL 卡 ready（spec 184 卡面结构不变）。"""
        from apps.kuaiai.services import operations_service as ops

        def _qs(rows=()):
            q = MagicMock()
            q.filter = MagicMock(return_value=q)
            q.exists = AsyncMock(return_value=bool(rows))
            return q

        with patch(
            "core.models.ai_audit_log.AiAuditLog.filter",
            MagicMock(return_value=_qs([SimpleNamespace(id=1)])),
        ), patch(
            "core.services.authorization.user_permission_service.UserPermissionService.is_admin_bypass",
            AsyncMock(return_value=False),
        ), patch(
            "core.services.authorization.user_permission_service.UserPermissionService.get_user_permissions",
            AsyncMock(return_value=set()),
        ):
            out = await ops.get_trust(TENANT, _user())
        cards = {c["key"]: c for c in out["cards"]}
        assert cards["hitl"]["status"] == "ready"
        assert out["hitl"] == {
            "implemented": True,
            "mode": "human_gate",
        }


# ------------------------------------------------- 认领单次性 / 收口健壮性


@pytest.mark.asyncio
class TestClaimAndClose:
    async def test_token_rotates_per_suspend(self, db):
        """B-C2：同会话两次挂起 token 不同（thread_id 含随机 nonce）。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            calls: List[Dict[str, Any]] = []
            frame1, _ = await _send_to_interrupt(session, calls)
            assert frame1 is not None

            # 第二次发送先收口旧挂起，再挂起新一轮（新 thread_id）
            model = _QueueChatModel(
                queue=[_tool_call_ai(call_id="call_w2"), _final_ai()]
            )
            p1, p2, p3, p4, p5 = _assemble_patches(
                model, [_write_tool(calls)]
            )
            s1, s2 = _send_patches()
            with p1, p2, p3, p4, p5, s1, s2:
                resp = await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "再报工 3 件"}],
                    stream=True,
                    user=_user(),
                    context={"session_id": session.id, "agent_id": AGENT_ID},
                )
                frames = _sse_frames(await _consume(resp))
            frame2 = _interrupt_frame(frames)
            assert frame2 is not None
            assert frame2["thread_token"] != frame1["thread_token"], (
                "两次挂起 token 必须不同（随机 nonce）"
            )

            # 旧 token 其线程已被收口删除 → resume 404
            with pytest.raises(NotFoundError):
                await cs.resume_chat_completion(
                    TENANT,
                    thread_token=frame1["thread_token"],
                    decisions=[{"type": "approve"}],
                    stream=True,
                    user=_user(),
                )

    async def test_resume_single_use_no_replay(self, db):
        """B-C1：同一 token resume 完成后再次提交 → 404，审计不重复。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            calls: List[Dict[str, Any]] = []
            frame, _ = await _send_to_interrupt(session, calls)

            model2 = _QueueChatModel(queue=[_final_ai("报工完成")])
            p1, p2, p3, p4, p5 = _assemble_patches(
                model2, [_write_tool(calls)]
            )
            s1, s2 = _send_patches()
            with p1, p2, p3, p4, p5, s1, s2:
                resp = await cs.resume_chat_completion(
                    TENANT,
                    thread_token=frame["thread_token"],
                    decisions=[{"type": "approve"}],
                    stream=True,
                    user=_user(),
                )
                await _consume(resp)
                # 同 token 重放 → 404（线程已删除/已被认领）
                with pytest.raises(NotFoundError):
                    await cs.resume_chat_completion(
                        TENANT,
                        thread_token=frame["thread_token"],
                        decisions=[{"type": "approve"}],
                        stream=True,
                        user=_user(),
                    )

            assert len(calls) == 1, "写 Tool 只执行一次"
            audits = await _confirm_audits()
            assert [a.route for a in audits] == [
                f"ai/tool/{WRITE_TOOL}/approve"
            ], "审计不得重复"

    async def test_claimed_pending_second_resume_404(self, db):
        """B-C1：认领后续跑崩溃残留 claimed 标记 → 同 token resume 404。

        决策审计已在认领事务提交；claim 不随失败回滚，防止重放导致
        写 Tool 重复执行。
        """
        async with with_tenant(TENANT):
            session = await _make_session()
            calls: List[Dict[str, Any]] = []
            frame, _ = await _send_to_interrupt(session, calls)

            # 续跑图在 ainvoke 处直接失败 → claimed 标记残留
            fake_agent = MagicMock()
            fake_agent.ainvoke = AsyncMock(
                side_effect=RuntimeError("llm down")
            )
            model2 = _QueueChatModel(queue=[_final_ai()])
            p1, p2, p3, p4, p5 = _assemble_patches(
                model2, [_write_tool(calls)]
            )
            s1, s2 = _send_patches()
            with p1, p2, p3, p4, p5, s1, s2, patch.object(
                agent_assembler,
                "build_agent",
                new=MagicMock(return_value=fake_agent),
            ):
                with pytest.raises(ExternalServiceError):
                    await cs.resume_chat_completion(
                        TENANT,
                        thread_token=frame["thread_token"],
                        decisions=[{"type": "approve"}],
                        stream=False,
                        user=_user(),
                    )

            assert calls == []
            audits = await _confirm_audits()
            assert [a.route for a in audits] == [
                f"ai/tool/{WRITE_TOOL}/approve"
            ]

            # 挂起仍在但已被认领 → 再次 resume 404，不重复执行/审计
            assert await _checkpoint_exists(session.id)
            with pytest.raises(NotFoundError):
                await cs.resume_chat_completion(
                    TENANT,
                    thread_token=frame["thread_token"],
                    decisions=[{"type": "approve"}],
                    stream=True,
                    user=_user(),
                )
            assert calls == []
            audits = await _confirm_audits()
            assert [a.route for a in audits] == [
                f"ai/tool/{WRITE_TOOL}/approve"
            ]

    async def test_inflight_claim_refuses_new_message(self, db):
        """B-C1：认领在途窗口内新消息 → 拒发，不写「已取消」谎报。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            calls: List[Dict[str, Any]] = []
            frame, _ = await _send_to_interrupt(session, calls)

            # 直接认领挂起（模拟 in-flight resume）
            saver = cs.TortoiseCheckpointSaver()
            thread_id = await _pending_thread_id(frame["thread_token"])
            tpl = await saver.aget_tuple(
                {
                    "configurable": {
                        "tenant_id": TENANT,
                        "thread_id": thread_id,
                    }
                }
            )
            assert tpl is not None
            assert await hs.claim_pending_token(saver, tpl) is True

            model2 = _QueueChatModel(queue=[_final_ai()])
            p1, p2, p3, p4, p5 = _assemble_patches(
                model2, [_write_tool(calls)]
            )
            s1, s2 = _send_patches()
            with p1, p2, p3, p4, p5, s1, s2:
                with pytest.raises(BusinessLogicError) as exc_info:
                    await cs.create_chat_completion(
                        TENANT,
                        [{"role": "user", "content": "新消息"}],
                        stream=True,
                        user=_user(),
                        context={
                            "session_id": session.id,
                            "agent_id": AGENT_ID,
                        },
                    )
            assert "正在执行" in str(exc_info.value)
            rows = await _msg_rows(session.id)
            assert [r.role for r in rows] == ["user", "assistant"], (
                "拒发不得落新 user 行/「已取消」tool 行"
            )
            assert await _confirm_audits() == []

    async def test_checkpoint_read_failure_refuses_send(self, db):
        """B-M3：挂起 checkpoint 读失败 → 失败关闭拒绝发送（不落 user 行）。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            calls: List[Dict[str, Any]] = []
            frame, _ = await _send_to_interrupt(session, calls)
            assert frame is not None

            model2 = _QueueChatModel(queue=[_final_ai()])
            p1, p2, p3, p4, p5 = _assemble_patches(
                model2, [_write_tool(calls)]
            )
            s1, s2 = _send_patches()
            with p1, p2, p3, p4, p5, s1, s2, patch.object(
                cs.TortoiseCheckpointSaver,
                "aget_tuple",
                new=AsyncMock(side_effect=RuntimeError("db down")),
            ):
                with pytest.raises(BusinessLogicError) as exc_info:
                    await cs.create_chat_completion(
                        TENANT,
                        [{"role": "user", "content": "新消息"}],
                        stream=True,
                        user=_user(),
                        context={
                            "session_id": session.id,
                            "agent_id": AGENT_ID,
                        },
                    )
            assert "读取失败" in str(exc_info.value)
            rows = await _msg_rows(session.id)
            assert [r.role for r in rows] == ["user", "assistant"]
            assert calls == []
            assert await _checkpoint_exists(session.id)

    async def test_purge_writes_close_rows_and_replay_clean(self, db):
        """B-M2：purge 过期挂起写「已过期」tool 收口行，再发送不回放悬空。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            calls: List[Dict[str, Any]] = []
            frame, _ = await _send_to_interrupt(session, calls)
            assert frame is not None

            future = hs.now_utc() + timedelta(minutes=31)
            with patch.object(hs, "now_utc", return_value=future):
                out = await hs.purge_expired_pending()
            assert out["purged_threads"] == 1
            assert not await _checkpoint_exists(session.id)

            rows = await _msg_rows(session.id)
            assert [r.role for r in rows] == ["user", "assistant", "tool"]
            assert "已过期" in rows[2].content
            assert rows[2].tool_call_id == "call_w1"
            audits = await _confirm_audits()
            assert [a.route for a in audits] == [
                f"ai/tool/{WRITE_TOOL}/expire"
            ]

            # 再发送：悬空 tool_calls 已收口，历史回放正常、流程走完
            model = _QueueChatModel(queue=[_final_ai("后续回答")])
            p1, p2, p3, p4, p5 = _assemble_patches(
                model, [_write_tool(calls)]
            )
            s1, s2 = _send_patches()
            with p1, p2, p3, p4, p5, s1, s2:
                resp = await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "再问一句"}],
                    stream=True,
                    user=_user(),
                    context={"session_id": session.id, "agent_id": AGENT_ID},
                )
                await _consume(resp)
            rows = await _msg_rows(session.id)
            assert [r.role for r in rows] == [
                "user",
                "assistant",
                "tool",
                "user",
                "assistant",
            ]
