"""KU-AI spec 214 单测：异常上报写 Tool（HITL）。

覆盖两层：
1. handler 行为（全 mock / 假数据，无库）：必填校验、闭集校验、
   工单/物料行级范围复核、service 调用参数透传、业务异常→service
   文案、通用异常→固定文案、成功返回异常单号与状态；
2. 确认闸真装配（沿用 spec 193 线束：真 create_agent + 真
   HumanInTheLoopMiddleware + 真 TortoiseCheckpointSaver，sqlite
   内存库）：确认前 service 不触达、approve 后执行一次、reject 不产出。
   真装配段通过补丁把登记后状态（manifest kind=write ∩
   ENABLED_TOOL_NAMES）打进来，只测装配逻辑；登记本身由
   TestWriteToolRegistration 读真 manifest/constants 断言。
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
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
from langchain_core.outputs import (
    ChatGeneration,
    ChatGenerationChunk,
    ChatResult,
)
from langchain_core.tools import StructuredTool
from pydantic import BaseModel
from tortoise import Tortoise

import apps.kuaiai.services.agent_assembler as agent_assembler
import apps.kuaiai.services.chat_service as cs
import apps.kuaiai.services.hitl_service as hs
from apps.kuaiai.constants import ENABLED_TOOL_NAMES, SCENE_READONLY_TOOL_NAMES
from apps.kuaiai.models.chat import KuaiaiChatMessage, KuaiaiChatSession
from apps.kuaiai.services.tools import exception_report as er
from core.ai.runtime.context import AiRuntimeContext
from core.models.ai_audit_log import AiAuditLog
from infra.domain.tenant_context import clear_tenant_context, with_tenant
from infra.exceptions.exceptions import NotFoundError, ValidationError

TENANT = 7
USER_ID = 5
AGENT_ID = 3
TOOL_NAME = "create_material_shortage_exception"

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


def _ctx():
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
    )


class _FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _patch_tx():
    return patch.object(er, "in_transaction", MagicMock(return_value=_FakeTx()))


def _patch_wo_scope(visible=True):
    return patch(
        "apps.kuaiai.services.chat_tools._work_order_in_scope",
        AsyncMock(return_value=visible),
    )


def _patch_row_scope(visible_ids=None):
    """``scene_tools._scoped_row_ids`` 替身：默认放行全部候选 id。"""

    async def _fake(model, ctx, resource, ids):
        return set(ids if visible_ids is None else visible_ids)

    return patch(
        "apps.kuaiai.services.scene_tools._scoped_row_ids",
        AsyncMock(side_effect=_fake),
    )


def _exception_service(**methods):
    svc = SimpleNamespace()
    for name, fn in methods.items():
        setattr(svc, name, fn)
    return patch(
        "apps.kuaizhizao.services.exception_service.ExceptionService",
        return_value=svc,
    ), svc


def _shortage_resp(**kw):
    base = dict(
        id=101,
        uuid="uuid-shortage-1",
        work_order_code="WO-009",
        material_code="M-001",
        material_name="物料一",
        shortage_quantity=Decimal("4"),
        alert_level="high",
        status="pending",
        suggested_action="purchase",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _delay_resp(**kw):
    base = dict(
        id=102,
        uuid="uuid-delay-1",
        work_order_code="WO-009",
        delay_days=5,
        delay_reason="物料未到",
        alert_level="high",
        status="pending",
        suggested_action="expedite",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _quality_resp(**kw):
    base = dict(
        id=103,
        uuid="uuid-quality-1",
        exception_type="process_deviation",
        severity="major",
        status="pending",
        work_order_code="WO-009",
        material_code="M-001",
        material_name="物料一",
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ================================================================== 缺料


class TestMaterialShortageParams:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await er.create_material_shortage_exception(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_required_fields(self):
        out = await er.create_material_shortage_exception(ctx=_ctx())
        assert "work_order_id" in out
        out = await er.create_material_shortage_exception(
            work_order_id=0, ctx=_ctx()
        )
        assert "work_order_id" in out
        out = await er.create_material_shortage_exception(
            work_order_id=9, ctx=_ctx()
        )
        assert "material_id" in out
        out = await er.create_material_shortage_exception(
            work_order_id=9, material_id=21, ctx=_ctx()
        )
        assert "shortage_quantity" in out
        out = await er.create_material_shortage_exception(
            work_order_id=9, material_id=21, shortage_quantity=0, ctx=_ctx()
        )
        assert "shortage_quantity" in out
        out = await er.create_material_shortage_exception(
            work_order_id=9,
            material_id=21,
            shortage_quantity="abc",
            ctx=_ctx(),
        )
        assert "shortage_quantity" in out

    @pytest.mark.asyncio
    async def test_optional_quantity_and_level_validation(self):
        out = await er.create_material_shortage_exception(
            work_order_id=9,
            material_id=21,
            shortage_quantity=4,
            required_quantity=-1,
            ctx=_ctx(),
        )
        assert "required_quantity" in out
        out = await er.create_material_shortage_exception(
            work_order_id=9,
            material_id=21,
            shortage_quantity=4,
            available_quantity=-1,
            ctx=_ctx(),
        )
        assert "available_quantity" in out
        out = await er.create_material_shortage_exception(
            work_order_id=9,
            material_id=21,
            shortage_quantity=4,
            alert_level="bad",
            ctx=_ctx(),
        )
        assert "alert_level" in out

    @pytest.mark.asyncio
    async def test_scope_rejects_before_service(self):
        patcher, svc = _exception_service(
            report_material_shortage=AsyncMock(return_value=_shortage_resp())
        )
        with patcher, _patch_wo_scope(False), _patch_row_scope(), _patch_tx():
            out = await er.create_material_shortage_exception(
                work_order_id=9,
                material_id=21,
                shortage_quantity=4,
                ctx=_ctx(),
            )
        assert "工单不存在" in out
        svc.report_material_shortage.assert_not_called()

        with patcher, _patch_wo_scope(True), _patch_row_scope(set()), (
            _patch_tx()
        ):
            out = await er.create_material_shortage_exception(
                work_order_id=9,
                material_id=21,
                shortage_quantity=4,
                ctx=_ctx(),
            )
        assert "物料不存在" in out
        svc.report_material_shortage.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_success_returns_number_and_status(self):
        patcher, svc = _exception_service(
            report_material_shortage=AsyncMock(return_value=_shortage_resp())
        )
        with patcher, _patch_wo_scope(True), _patch_row_scope(), _patch_tx():
            out = await er.create_material_shortage_exception(
                work_order_id=9,
                material_id=21,
                shortage_quantity=4,
                required_quantity=10,
                available_quantity=6,
                alert_level="HIGH",
                remarks=" 停线风险 ",
                ctx=_ctx(),
            )
        assert svc.report_material_shortage.await_count == 1
        call = svc.report_material_shortage.await_args
        assert call.kwargs["tenant_id"] == TENANT
        assert call.kwargs["created_by"] == USER_ID
        data = call.kwargs["data"]
        assert data.work_order_id == 9
        assert data.material_id == 21
        assert data.shortage_quantity == Decimal("4")
        assert data.required_quantity == Decimal("10")
        assert data.available_quantity == Decimal("6")
        # 闭集归一小写后透传
        assert data.alert_level == "high"
        assert data.remarks == "停线风险"
        assert "uuid-shortage-1" in out
        assert "WO-009" in out and "M-001" in out
        assert "pending" in out

    @pytest.mark.asyncio
    async def test_business_error_passthrough(self):
        """幂等复核：service 同工单同物料去重 → 业务文案透回，不产生新单。"""
        patcher, svc = _exception_service(
            report_material_shortage=AsyncMock(
                side_effect=ValidationError(
                    "该工单物料已有未处理缺料异常 #7，请在异常追踪中跟进"
                )
            )
        )
        with patcher, _patch_wo_scope(True), _patch_row_scope(), _patch_tx():
            out = await er.create_material_shortage_exception(
                work_order_id=9,
                material_id=21,
                shortage_quantity=4,
                ctx=_ctx(),
            )
        assert "创建缺料异常失败" in out
        assert "已有未处理缺料异常" in out

    @pytest.mark.asyncio
    async def test_generic_error_fixed_text(self):
        patcher, svc = _exception_service(
            report_material_shortage=AsyncMock(
                side_effect=RuntimeError("db down")
            )
        )
        with patcher, _patch_wo_scope(True), _patch_row_scope(), _patch_tx():
            out = await er.create_material_shortage_exception(
                work_order_id=9,
                material_id=21,
                shortage_quantity=4,
                ctx=_ctx(),
            )
        assert out == "创建缺料异常失败，请稍后重试"
        assert "db down" not in out


# ================================================================== 延期


class TestDeliveryDelayParams:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await er.create_delivery_delay_exception(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_required_and_validation(self):
        out = await er.create_delivery_delay_exception(ctx=_ctx())
        assert "work_order_id" in out
        out = await er.create_delivery_delay_exception(
            work_order_id=9, delay_reason="   ", ctx=_ctx()
        )
        assert "delay_reason" in out
        out = await er.create_delivery_delay_exception(
            work_order_id=9, delay_reason="x" * 501, ctx=_ctx()
        )
        assert "delay_reason" in out
        out = await er.create_delivery_delay_exception(
            work_order_id=9,
            delay_reason="物料未到",
            delay_days=-1,
            ctx=_ctx(),
        )
        assert "delay_days" in out
        out = await er.create_delivery_delay_exception(
            work_order_id=9,
            delay_reason="物料未到",
            alert_level="bad",
            ctx=_ctx(),
        )
        assert "alert_level" in out

    @pytest.mark.asyncio
    async def test_create_success(self):
        patcher, svc = _exception_service(
            report_delivery_delay=AsyncMock(return_value=_delay_resp())
        )
        with patcher, _patch_wo_scope(True), _patch_tx():
            out = await er.create_delivery_delay_exception(
                work_order_id=9,
                delay_reason=" 物料未到 ",
                delay_days=5,
                ctx=_ctx(),
            )
        call = svc.report_delivery_delay.await_args
        assert call.kwargs["tenant_id"] == TENANT
        data = call.kwargs["data"]
        assert data.work_order_id == 9
        assert data.delay_reason == "物料未到"
        assert data.delay_days == 5
        assert "uuid-delay-1" in out
        assert "延期 5 天" in out and "pending" in out

    @pytest.mark.asyncio
    async def test_business_error_passthrough(self):
        patcher, svc = _exception_service(
            report_delivery_delay=AsyncMock(
                side_effect=NotFoundError("工单不存在: 9")
            )
        )
        with patcher, _patch_wo_scope(True), _patch_tx():
            out = await er.create_delivery_delay_exception(
                work_order_id=9,
                delay_reason="物料未到",
                ctx=_ctx(),
            )
        assert "创建延期异常失败" in out

    @pytest.mark.asyncio
    async def test_generic_error_fixed_text(self):
        patcher, svc = _exception_service(
            report_delivery_delay=AsyncMock(
                side_effect=RuntimeError("boom")
            )
        )
        with patcher, _patch_wo_scope(True), _patch_tx():
            out = await er.create_delivery_delay_exception(
                work_order_id=9,
                delay_reason="物料未到",
                ctx=_ctx(),
            )
        assert out == "创建延期异常失败，请稍后重试"


# ================================================================== 质量


class TestQualityExceptionParams:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await er.create_quality_exception(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_required_and_closed_sets(self):
        out = await er.create_quality_exception(ctx=_ctx())
        assert "problem_description" in out
        out = await er.create_quality_exception(
            problem_description="  ", ctx=_ctx()
        )
        assert "problem_description" in out
        out = await er.create_quality_exception(
            problem_description="尺寸超差", severity="bad", ctx=_ctx()
        )
        assert "severity" in out
        out = await er.create_quality_exception(
            problem_description="尺寸超差", exception_type="bad", ctx=_ctx()
        )
        assert "exception_type" in out

    @pytest.mark.asyncio
    async def test_optional_assoc_scope_checks(self):
        patcher, svc = _exception_service(
            report_quality_exception=AsyncMock(return_value=_quality_resp())
        )
        with patcher, _patch_wo_scope(False), _patch_row_scope(), _patch_tx():
            out = await er.create_quality_exception(
                problem_description="尺寸超差",
                work_order_id=9,
                ctx=_ctx(),
            )
        assert "工单不存在" in out
        svc.report_quality_exception.assert_not_called()

        with patcher, _patch_wo_scope(True), _patch_row_scope(set()), (
            _patch_tx()
        ):
            out = await er.create_quality_exception(
                problem_description="尺寸超差",
                material_id=21,
                ctx=_ctx(),
            )
        assert "物料不存在" in out
        svc.report_quality_exception.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_success_defaults(self):
        patcher, svc = _exception_service(
            report_quality_exception=AsyncMock(return_value=_quality_resp())
        )
        with patcher, _patch_wo_scope(True), _patch_row_scope(), _patch_tx():
            out = await er.create_quality_exception(
                problem_description="尺寸超差",
                work_order_id=9,
                material_id=21,
                severity="MAJOR",
                batch_no="B-1",
                ctx=_ctx(),
            )
        data = svc.report_quality_exception.await_args.kwargs["data"]
        assert data.problem_description == "尺寸超差"
        assert data.work_order_id == 9
        assert data.material_id == 21
        assert data.severity == "major"
        # 未给 exception_type → service 默认 process_deviation
        assert data.exception_type == "process_deviation"
        assert data.batch_no == "B-1"
        assert "uuid-quality-1" in out
        assert "major" in out and "pending" in out
        assert "WO-009" in out and "M-001" in out

    @pytest.mark.asyncio
    async def test_generic_error_fixed_text(self):
        patcher, svc = _exception_service(
            report_quality_exception=AsyncMock(
                side_effect=RuntimeError("notify down")
            )
        )
        with patcher, _patch_wo_scope(True), _patch_row_scope(), _patch_tx():
            out = await er.create_quality_exception(
                problem_description="尺寸超差",
                ctx=_ctx(),
            )
        assert out == "创建质量异常失败，请稍后重试"


# ================================================================== 登记断言

_WRITE_TOOLS = {
    "create_material_shortage_exception": (
        "kuaizhizao:production-execution-material-shortage-exceptions:create"
    ),
    "create_delivery_delay_exception": (
        "kuaizhizao:production-execution-delivery-delay-exceptions:create"
    ),
    "create_quality_exception": (
        "kuaizhizao:production-execution-quality-exceptions:create"
    ),
}


class TestWriteToolRegistration:
    """真 manifest/constants 登记断言（不打补丁）——登记已在集成阶段完成。

    e2e 装配段的 ``manifest_write_tool_names``/``ENABLED_TOOL_NAMES`` 补丁只
    测装配逻辑；本用例对真源断言，防 manifest 丢条目/权限码漂移静默通过。
    """

    def test_manifest_write_entries_and_closed_set(self):
        manifest_path = (
            Path(er.__file__).resolve().parents[2] / "manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tools = {t["name"]: t for t in manifest.get("ai_tools") or []}
        for name, perm in _WRITE_TOOLS.items():
            entry = tools.get(name)
            assert entry is not None, f"manifest 缺 {name} 条目"
            assert entry.get("kind") == "write", name
            assert entry.get("permission") == perm, name
            assert name in ENABLED_TOOL_NAMES, name
            assert name not in SCENE_READONLY_TOOL_NAMES, name


# ================================================================== 确认闸真装配
# 沿用 spec 193 线束（替身 LLM + 真 middleware/checkpointer），
# 补丁模拟「manifest kind=write 条目 + ENABLED_TOOL_NAMES 登记」后的状态。


class _QueueChatModel(BaseChatModel):
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


class _ShortageToolArgs(BaseModel):
    work_order_id: int
    material_id: int
    shortage_quantity: float
    remarks: Optional[str] = None


def _user(uid: int = USER_ID):
    return SimpleNamespace(id=uid, full_name="测试用户", username="tester")


def _tool_call_ai(call_id: str = "call_e1") -> AIMessage:
    args = {"work_order_id": 9, "material_id": 21, "shortage_quantity": 4}
    return AIMessage(
        content="",
        tool_calls=[
            {"name": TOOL_NAME, "args": args, "id": call_id, "type": "tool_call"}
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


def _real_shortage_tool() -> StructuredTool:
    """StructuredTool 直挂真 handler——ctx 由 tool_bridge/桥外 contextvar 解析。"""
    return StructuredTool(
        name=TOOL_NAME,
        description="创建缺料异常",
        coroutine=er.create_material_shortage_exception,
        args_schema=_ShortageToolArgs,
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
        name="异常上报档案",
        system_prompt="你是助手",
        default_model_id=42,
        enabled_tools=[TOOL_NAME],
        status="启用",
        grant_mode="USER",
        mcp_server_ids=None,
        knowledge_ids=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _assemble_patches(model, tools, profile=None):
    """装配替身 + 登记后状态模拟（manifest kind=write ∩ ENABLED_TOOL_NAMES）。"""
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
        # 登记模拟：manifest kind=write 条目生效后本 Tool 进确认闸名单；
        # ENABLED_TOOL_NAMES 含本 Tool 才进档案 enabled_tools 白名单
        patch.object(
            agent_assembler,
            "manifest_write_tool_names",
            new=MagicMock(return_value=frozenset({TOOL_NAME})),
        ),
        patch.object(
            agent_assembler,
            "ENABLED_TOOL_NAMES",
            new=ENABLED_TOOL_NAMES | {TOOL_NAME},
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


async def _send_to_interrupt(session: KuaiaiChatSession):
    model = _QueueChatModel(queue=[_tool_call_ai(), _final_ai()])
    p1, p2, p3, p4, p5, p6, p7 = _assemble_patches(
        model, [_real_shortage_tool()]
    )
    s1, s2 = _send_patches()
    with p1, p2, p3, p4, p5, p6, p7, s1, s2:
        resp = await cs.create_chat_completion(
            TENANT,
            [{"role": "user", "content": "WO-009 缺料停线了，缺 4 件"}],
            stream=True,
            user=_user(),
            context={"session_id": session.id, "agent_id": AGENT_ID},
        )
        assert isinstance(resp, StreamingResponse)
        frames = _sse_frames(await _consume(resp))
    return _interrupt_frame(frames)


async def _msg_rows(session_id: int) -> List[KuaiaiChatMessage]:
    return await (
        KuaiaiChatMessage.filter(tenant_id=TENANT, session_id=session_id)
        .order_by("seq")
        .all()
    )


def _service_patch():
    """缺料 service 替身 + 范围/事务替身，供真装配段使用。"""
    svc = SimpleNamespace(
        report_material_shortage=AsyncMock(return_value=_shortage_resp())
    )
    return svc, (
        patch(
            "apps.kuaizhizao.services.exception_service.ExceptionService",
            return_value=svc,
        ),
        _patch_wo_scope(True),
        _patch_row_scope(),
        _patch_tx(),
    )


@pytest.mark.asyncio
class TestHitlGateE2E:
    async def test_write_tool_interrupts_before_execute(self, db):
        """确认前：kuaiai_interrupt 帧下发，service 不触达，不落 tool 行。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            svc, (p_svc, p_wo, p_row, p_tx) = _service_patch()
            with p_svc, p_wo, p_row, p_tx:
                frame = await _send_to_interrupt(session)

            assert frame is not None, "缺少 kuaiai_interrupt 扩展帧"
            assert frame["thread_token"] and frame["expires_at"]
            assert len(frame["actions"]) == 1
            action = frame["actions"][0]
            assert action["tool"] == TOOL_NAME
            assert action["label"]
            assert "work_order_id" in action["args_summary"]
            assert svc.report_material_shortage.await_count == 0, (
                "确认前写 Tool 绝不可执行"
            )
            rows = await _msg_rows(session.id)
            assert not any(r.role == "tool" for r in rows)

    async def test_approve_executes_once(self, db):
        """approve → 真 handler 执行一次：service 调用 + 单号落 tool 行。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            svc, (p_svc, p_wo, p_row, p_tx) = _service_patch()
            with p_svc, p_wo, p_row, p_tx:
                frame = await _send_to_interrupt(session)
                assert frame is not None

                model2 = _QueueChatModel(queue=[_final_ai("缺料异常已登记")])
                p1, p2, p3, p4, p5, p6, p7 = _assemble_patches(
                    model2, [_real_shortage_tool()]
                )
                s1, s2 = _send_patches()
                with p1, p2, p3, p4, p5, p6, p7, s1, s2:
                    resp = await cs.resume_chat_completion(
                        TENANT,
                        thread_token=frame["thread_token"],
                        decisions=[{"type": "approve"}],
                        stream=True,
                        user=_user(),
                    )
                    frames = _sse_frames(await _consume(resp))

            assert svc.report_material_shortage.await_count == 1
            call = svc.report_material_shortage.await_args
            assert call.kwargs["tenant_id"] == TENANT
            data = call.kwargs["data"]
            assert (data.work_order_id, data.material_id) == (9, 21)
            assert _interrupt_frame(frames) is None

            rows = await _msg_rows(session.id)
            tool_rows = [r for r in rows if r.role == "tool"]
            assert len(tool_rows) == 1
            assert tool_rows[0].tool_name == TOOL_NAME
            assert "缺料异常已创建" in tool_rows[0].content
            assert "uuid-shortage-1" in tool_rows[0].content
            audits = await AiAuditLog.filter(
                tenant_id=TENANT, capability="tool_confirm"
            ).all()
            assert [a.route for a in audits] == [
                f"ai/tool/{TOOL_NAME}/approve"
            ]

    async def test_reject_produces_nothing(self, db):
        """reject → service 不触达，无业务数据，reject 审计。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            svc, (p_svc, p_wo, p_row, p_tx) = _service_patch()
            with p_svc, p_wo, p_row, p_tx:
                frame = await _send_to_interrupt(session)
                assert frame is not None

                model2 = _QueueChatModel(queue=[_final_ai("好的，已取消")])
                p1, p2, p3, p4, p5, p6, p7 = _assemble_patches(
                    model2, [_real_shortage_tool()]
                )
                s1, s2 = _send_patches()
                with p1, p2, p3, p4, p5, p6, p7, s1, s2:
                    resp = await cs.resume_chat_completion(
                        TENANT,
                        thread_token=frame["thread_token"],
                        decisions=[{"type": "reject", "message": "先不建"}],
                        stream=True,
                        user=_user(),
                    )
                    await _consume(resp)

            assert svc.report_material_shortage.await_count == 0
            rows = await _msg_rows(session.id)
            assert len([r for r in rows if r.role == "tool"]) == 1
            audits = await AiAuditLog.filter(
                tenant_id=TENANT, capability="tool_confirm"
            ).all()
            assert [a.route for a in audits] == [
                f"ai/tool/{TOOL_NAME}/reject"
            ]

    async def test_resume_single_use_no_replay(self, db):
        """幂等复核：同 token 二次 resume → 404，写 Tool 仍只执行一次。"""
        async with with_tenant(TENANT):
            session = await _make_session()
            svc, (p_svc, p_wo, p_row, p_tx) = _service_patch()
            with p_svc, p_wo, p_row, p_tx:
                frame = await _send_to_interrupt(session)
                assert frame is not None

                model2 = _QueueChatModel(queue=[_final_ai("完成")])
                p1, p2, p3, p4, p5, p6, p7 = _assemble_patches(
                    model2, [_real_shortage_tool()]
                )
                s1, s2 = _send_patches()
                with p1, p2, p3, p4, p5, p6, p7, s1, s2:
                    resp = await cs.resume_chat_completion(
                        TENANT,
                        thread_token=frame["thread_token"],
                        decisions=[{"type": "approve"}],
                        stream=True,
                        user=_user(),
                    )
                    await _consume(resp)
                    with pytest.raises(NotFoundError):
                        await cs.resume_chat_completion(
                            TENANT,
                            thread_token=frame["thread_token"],
                            decisions=[{"type": "approve"}],
                            stream=True,
                            user=_user(),
                        )

            assert svc.report_material_shortage.await_count == 1, (
                "同一挂起只执行一次写"
            )
            audits = await AiAuditLog.filter(
                tenant_id=TENANT, capability="tool_confirm"
            ).all()
            assert [a.route for a in audits] == [
                f"ai/tool/{TOOL_NAME}/approve"
            ], "审计不得重复"
