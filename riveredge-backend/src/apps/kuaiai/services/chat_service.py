"""KU-AI 对话编排服务（S2：纯对话路径 A + 档案装配路径 B）。

委托入口：``core/ai/chat_handler.py`` 以 ``importlib.find_spec`` 单名探测本模块，
命中后调用模块级 ``create_chat_completion``（入口形态已固定为模块级函数）。

路径 A 纯对话（无档案）：``model_factory.build_chat_model`` 目录行优先
（无目录行才 IntegrationConfig 兜底）；请求级模型仅接受 ``context.model_id``
（int 目录行）或请求 ``model`` 名匹配本租户启用 chat 行，不直通任意模型名。

路径 B 带工具（显式 ``context.agent_id`` 或 agent 路径默认档案）：
``agent_assembler.assemble`` 授权+装配（无授权 403，不静默降级）→
``set_ai_context`` → ``astream_events`` 真流式（端点不支持 tool_calls 流式时
走 sse_adapter 非流式兼容分支）；选中档案**忽略**请求级模型覆盖（KR-F3）；
tool 行（role=tool）与 assistant.tool_calls（OpenAI 线格式）落库（KR-D6/D7）。

写路径：先落 user 行 → 运行 → 结束后落 tool/assistant 行 + token 回填；
失败不回滚已提交 user 行；历史唯一来源 ``apps_kuaiai_chat_messages`` 回放
（回放/线格式转换 canonical 实现在 ``core/ai/runtime/memory``）。
日志 / SSE 不落 apiKey、cipher、JWT、内部路径（KR-I5）；空租户上下文失败
关闭（KR-I1–I3）。
"""

from __future__ import annotations

import inspect
import json
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from fastapi.responses import StreamingResponse
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI
from loguru import logger
from tortoise.transactions import in_transaction

from apps.kuaiai.constants import MODEL_TYPE_CHAT, STATUS_ENABLED
from apps.kuaiai.models.catalog import KuaiaiLlmModel
from apps.kuaiai.models.chat import KuaiaiChatMessage, KuaiaiChatSession
from apps.kuaiai.services.agent_assembler import AssembledAgent, assemble
from apps.kuaiai.services.session_service import get_owned_session
from core.ai.runtime.agent_factory import DEFAULT_RECURSION_LIMIT
from core.ai.runtime.context import (
    AiRuntimeContext,
    reset_ai_context,
    set_ai_context,
)
from core.ai.runtime.memory import (
    dicts_to_lc_messages,
    lc_tool_calls_to_openai,
    message_text,
    normalize_tool_calls,
    to_lc_messages,
)
from core.ai.runtime.model_factory import (
    # 私有函数：目录行命中判定 seam（U-2 解耦需要知道模型来源分支；
    # model_factory 未暴露公开判定入口，与 catalog_service 引用
    # _mask_config_password 同款私有借用）
    _resolve_catalog_source,
    build_chat_model,
)
from core.ai.runtime.sse_adapter import agent_to_openai_sse
from core.ai.runtime_config import AiRuntimeConfig
from core.utils.timezone_utils import now_utc
from infra.exceptions.exceptions import (
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from infra.models.user import User

# 回放窗口：消息表尾部最近 N 条进入上下文（trim 收口见 runtime/memory limit）
_HISTORY_LIMIT = 50

_SSE_DONE = b"data: [DONE]\n\n"

# 兼容别名：spec 134 移交项/既有测试钉住的模块内名称；canonical 实现在
# core/ai/runtime/memory（S2 已收口，本地不再保留实现副本）。
_normalize_tool_calls = normalize_tool_calls
_rows_to_lc_messages = to_lc_messages
_dicts_to_lc_messages = dicts_to_lc_messages


def _context_value(context: Optional[Dict[str, Any]], key: str) -> Any:
    """context 取值：AiBusinessContext.extra 键经 to_broker_dict 已摊平为
    顶层，兼容顶层直传与嵌套 extra 两种形态。"""
    if not isinstance(context, dict):
        return None
    value = context.get(key)
    if value is None:
        extra = context.get("extra")
        if isinstance(extra, dict):
            value = extra.get(key)
    return value


def _context_session_id(context: Optional[Dict[str, Any]]) -> Optional[str]:
    """从 context 提取 session_id（AiBusinessContext.extra 已摊平为顶层键）。"""
    raw = _context_value(context, "session_id")
    if raw is None:
        return None
    ref = str(raw).strip()
    return ref or None


def _context_int(context: Optional[Dict[str, Any]], key: str) -> Optional[int]:
    """context 中正整数 id 取值（agent_id / model_id；str/int 均可，非法置 None）。"""
    raw = _context_value(context, key)
    if raw is None:
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _is_agent_path(context: Optional[Dict[str, Any]]) -> bool:
    """「走 agent 路径」判定：未传 agent_id 时是否解析本租户默认档案。

    约定 ``capability_mode == "agent"`` 为走 agent 路径（``AiBusinessContext.extra``
    既有闭集为 ``ask|query|guide``，本标记由产品侧在需默认档案时产出）。纯对话
    （未选档案、非 agent 路径）不解析、不挂默认档案。显式 ``context.agent_id``
    直达路径 B，与本判定无关。默认档案按名称「默认助手」解析（KR-D8，对齐
    A31）；无该档案则不编造（种子非强制）。
    """
    return (
        str(_context_value(context, "capability_mode") or "").strip() == "agent"
    )


def _last_user_content(messages: List[Dict[str, Any]]) -> Optional[str]:
    for item in reversed(messages):
        if isinstance(item, dict) and item.get("role") == "user":
            text = str(item.get("content") or "").strip()
            if text:
                return text
    return None


def _capture_usage(chunk: BaseMessage, usage: Dict[str, Optional[int]]) -> None:
    meta = getattr(chunk, "usage_metadata", None)
    if not isinstance(meta, dict):
        return
    if meta.get("input_tokens") is not None:
        usage["prompt_tokens"] = meta.get("input_tokens")
    if meta.get("output_tokens") is not None:
        usage["completion_tokens"] = meta.get("output_tokens")


def _sum_usage(messages: List[BaseMessage]) -> Dict[str, Optional[int]]:
    """汇总一轮 agent 运行内全部 AIMessage 的 usage_metadata（多次模型调用）。"""
    prompt = completion = total = 0
    seen = False
    for msg in messages:
        meta = getattr(msg, "usage_metadata", None)
        if not isinstance(meta, dict):
            continue
        seen = True
        prompt += meta.get("input_tokens") or 0
        completion += meta.get("output_tokens") or 0
        total += meta.get("total_tokens") or 0
    if not seen:
        return {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


async def _page_context_summary(
    context: Optional[Dict[str, Any]],
    tenant_id: int,
    user: Optional[User],
) -> Optional[str]:
    """抽屉页上下文摘要（KR-F4/F6）。

    仅当 context 携带 ``screen``/``resource_key``/``record_id`` 时调用服务端
    摘要服务；``page_context`` 模块由并行单元交付，lazy import 缺失即跳过
    不炸；摘要内部失败一律省略不 500。客户端 ``screenLabel``/``recordLabel``
    永不进 prompt（本函数只读白名单字段，label 键从不读取）。
    """
    if not isinstance(context, dict):
        return None
    # 与 _context_value 同口径：白名单键兼容顶层直传与 extra 嵌套
    if not any(
        _context_value(context, key) is not None
        for key in ("screen", "resource_key", "record_id")
    ):
        return None
    try:
        from apps.kuaiai.services.page_context import (
            build_page_context_summary,
        )
    except ImportError:
        return None
    # page_context 只读顶层键：extra 嵌套的白名单键摊平一层再传入
    flat = dict(context)
    extra = context.get("extra")
    if isinstance(extra, dict):
        for key in ("screen", "resource_key", "record_id"):
            if flat.get(key) is None and extra.get(key) is not None:
                flat[key] = extra[key]
    try:
        summary = build_page_context_summary(
            flat, tenant_id=tenant_id, user=user
        )
        if inspect.isawaitable(summary):
            summary = await summary
    except Exception as exc:
        logger.warning(
            "KU-AI 页上下文摘要失败，省略 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        return None
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return None


async def _match_catalog_model_id(
    tenant_id: int, model_name: str
) -> Optional[int]:
    """请求级模型名 → 本租户启用 chat 目录行 id；未命中 None（回默认解析）。"""
    name = (model_name or "").strip()
    if not name:
        return None
    row = await (
        KuaiaiLlmModel.filter(
            tenant_id=tenant_id,
            model_name=name,
            model_type=MODEL_TYPE_CHAT,
            status=STATUS_ENABLED,
            deleted_at__isnull=True,
        )
        .order_by("id")
        .first()
    )
    return row.id if row is not None else None


async def _history_rows(
    tenant_id: int, session_id: int
) -> List[KuaiaiChatMessage]:
    """取会话尾部最近 _HISTORY_LIMIT 条（按 seq 升序返回）。"""
    rows = await (
        KuaiaiChatMessage.filter(
            tenant_id=tenant_id, session_id=session_id, deleted_at__isnull=True
        )
        .order_by("-seq")
        .limit(_HISTORY_LIMIT)
    )
    rows.reverse()
    return _drop_orphaned_head_rows(rows)


def _row_tool_call_ids(row: Any) -> set:
    """assistant 行 tool_calls（OpenAI 线格式）里的调用 id 集合。"""
    calls = getattr(row, "tool_calls", None)
    ids = set()
    if isinstance(calls, list):
        for call in calls:
            if isinstance(call, dict) and call.get("id"):
                ids.add(str(call["id"]))
    return ids


def _drop_orphaned_head_rows(
    rows: List[KuaiaiChatMessage],
) -> List[KuaiaiChatMessage]:
    """丢弃截断窗口头部连续的孤儿行，防回放产生悬空 tool_calls。

    尾部取 N 条可能切断 tool 调用对：
    - 开头是 ``role=tool`` 行：其配对的 assistant(tool_calls) 行已被截掉；
    - 开头是带 ``tool_calls`` 的 assistant 行，其 tool_call_id 在窗口内
      无对应 ``role=tool`` 应答行（部分应答被截掉同样算孤儿）。
    遇到普通 user/assistant 行即停——窗口中段的孤儿不动（那不是截断
    造成的，属于数据本身的完整性问题，不在此修补范围）。
    """
    out = list(rows)
    while out:
        head = out[0]
        role = getattr(head, "role", None)
        if role == "tool":
            out.pop(0)
            continue
        if role == "assistant":
            call_ids = _row_tool_call_ids(head)
            if call_ids:
                answered = {
                    str(getattr(r, "tool_call_id", "") or "")
                    for r in out[1:]
                    if getattr(r, "role", None) == "tool"
                }
                if call_ids - answered:
                    out.pop(0)
                    continue
        break
    return out


async def _next_seq(tenant_id: int, session_id: int) -> int:
    last = await (
        KuaiaiChatMessage.filter(
            tenant_id=tenant_id, session_id=session_id, deleted_at__isnull=True
        )
        .order_by("-seq")
        .first()
    )
    return (last.seq + 1) if last else 1


async def _lock_session_row(
    tenant_id: int, session_id: int
) -> KuaiaiChatSession:
    """事务内 select_for_update 锁会话行：串行化同会话并发 send 的 seq 分配。

    调用前提：归属（tenant+user）已验过（见 get_owned_session），这里只按
    tenant_id + id 上锁，不再做归属判定；锁不到（已删/跨租户）→ 404。
    单把锁、无嵌套，不引入死锁面。
    """
    locked = await (
        KuaiaiChatSession.filter(
            tenant_id=tenant_id, id=session_id, deleted_at__isnull=True
        )
        .select_for_update()
        .first()
    )
    if locked is None:
        raise NotFoundError("会话", str(session_id))
    return locked


def _audit_update(actor: Optional[User]) -> Dict[str, Any]:
    """与 session_service.update_session 对齐的更新审计字段。"""
    if actor is None or getattr(actor, "id", None) is None:
        return {}
    return {
        "updated_by": actor.id,
        "updated_by_name": getattr(actor, "full_name", None)
        or getattr(actor, "username", None),
    }


def _audit_create(actor: Optional[User]) -> Dict[str, Any]:
    """消息行落库审计字段：created_by/updated_by 及 *_name（BaseModel 列名）。"""
    if actor is None or getattr(actor, "id", None) is None:
        return {}
    name = getattr(actor, "full_name", None) or getattr(actor, "username", None)
    return {
        "created_by": actor.id,
        "created_by_name": name,
        "updated_by": actor.id,
        "updated_by_name": name,
    }


async def _persist_user_message(
    tenant_id: int,
    session: KuaiaiChatSession,
    content: str,
    *,
    user: Optional[User] = None,
    agent_id: Optional[int] = None,
) -> None:
    async with in_transaction():
        await _lock_session_row(tenant_id, session.id)
        seq = await _next_seq(tenant_id, session.id)
        await KuaiaiChatMessage.create(
            tenant_id=tenant_id,
            session_id=session.id,
            seq=seq,
            role="user",
            content=content,
            **_audit_create(user),
        )
        update: Dict[str, Any] = {"last_message_at": now_utc()}
        update.update(_audit_update(user))
        if agent_id is not None:
            # 会话回写：send 携带 agent_id（含默认档案解析结果）时同步会话行
            update["agent_id"] = agent_id
        if not (session.title or "").strip():
            update["title"] = content[:50]
        await session.update_from_dict(update).save()


async def _persist_assistant_message(
    tenant_id: int,
    session: KuaiaiChatSession,
    content: str,
    *,
    user: Optional[User] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
) -> None:
    async with in_transaction():
        await _lock_session_row(tenant_id, session.id)
        seq = await _next_seq(tenant_id, session.id)
        await KuaiaiChatMessage.create(
            tenant_id=tenant_id,
            session_id=session.id,
            seq=seq,
            role="assistant",
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            **_audit_create(user),
        )
        update: Dict[str, Any] = {"last_message_at": now_utc()}
        update.update(_audit_update(user))
        await session.update_from_dict(update).save()


async def _persist_agent_messages(
    tenant_id: int,
    session: KuaiaiChatSession,
    messages: List[BaseMessage],
    *,
    user: Optional[User] = None,
    agent_id: Optional[int] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
) -> None:
    """路径 B 运行产物落库（§8 写路径 / AC#4）。

    按发生序：``AIMessage`` → ``role=assistant``（LC 形态 tool_calls 经
    ``lc_tool_calls_to_openai`` 转 OpenAI 线格式存列）、``ToolMessage`` →
    ``role=tool``（tool_call_id/tool_name/content）；token 回填到最后一条
    assistant 行；同事务回写 ``session.agent_id``。其余角色（system/回放
    输入）不落库。
    """
    specs: List[Dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            specs.append(
                {
                    "role": "tool",
                    "content": message_text(msg),
                    "tool_call_id": str(msg.tool_call_id or ""),
                    "tool_name": msg.name or None,
                }
            )
        elif isinstance(msg, AIMessage):
            specs.append(
                {
                    "role": "assistant",
                    "content": message_text(msg),
                    "tool_calls": lc_tool_calls_to_openai(
                        getattr(msg, "tool_calls", None)
                    )
                    or None,
                }
            )
    if not specs:
        return
    for spec in reversed(specs):
        if spec["role"] == "assistant":
            spec["prompt_tokens"] = prompt_tokens
            spec["completion_tokens"] = completion_tokens
            break
    async with in_transaction():
        await _lock_session_row(tenant_id, session.id)
        seq = await _next_seq(tenant_id, session.id)
        for spec in specs:
            await KuaiaiChatMessage.create(
                tenant_id=tenant_id,
                session_id=session.id,
                seq=seq,
                **_audit_create(user),
                **spec,
            )
            seq += 1
        update: Dict[str, Any] = {"last_message_at": now_utc()}
        update.update(_audit_update(user))
        if agent_id is not None:
            update["agent_id"] = agent_id
        await session.update_from_dict(update).save()


class _AgentRunTracer(AsyncCallbackHandler):
    """路径 B 运行收集器（经 ``config["callbacks"]`` 注入）。

    ``agent_to_openai_sse`` 的 ``astream_events`` 与其 KR-D14 ``ainvoke``
    兼容分支共用同一份 config → 两条执行路径都收得到：

    - ``on_tool_end``：按发生序收集 ``ToolMessage``（终态缺失时兜底）；
    - 根 run ``on_chain_end``（``parent_run_id=None``）：``outputs`` 为图
      终态 ``{"messages": [...]}``，与 ``ainvoke`` 返回同形态，落库首选。
    """

    def __init__(self) -> None:
        self.final_messages: Optional[List[BaseMessage]] = None
        self.tool_messages: List[ToolMessage] = []

    async def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        if isinstance(output, ToolMessage):
            self.tool_messages.append(output)

    async def on_chain_end(
        self, outputs: Any, *, parent_run_id: Any = None, **kwargs: Any
    ) -> None:
        if parent_run_id is not None:
            return
        if isinstance(outputs, dict) and isinstance(
            outputs.get("messages"), list
        ):
            self.final_messages = list(outputs["messages"])

    def new_messages(self, prefix_len: int) -> List[BaseMessage]:
        """终态切片出本轮新增消息。

        终态缺失（如运行中断、实现差异）但有工具轨迹时退化：tool 行照落，
        补一条空 content 的 assistant 行承接 tool_calls（args 不可得置 {}）。
        """
        if self.final_messages is not None:
            return list(self.final_messages[prefix_len:])
        if self.tool_messages:
            out: List[BaseMessage] = [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": m.name or "",
                            "args": {},
                            "id": m.tool_call_id,
                            "type": "tool_call",
                        }
                        for m in self.tool_messages
                    ],
                )
            ]
            out.extend(self.tool_messages)
            return out
        return []


def _openai_chunk_payload(model_name: str, delta: Dict[str, Any]) -> bytes:
    chunk = {
        "id": "chatcmpl-kuaiai",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_name,
        "choices": [{"index": 0, "delta": delta}],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8")


async def _openai_sse_stream(
    chat: ChatOpenAI,
    lc_messages: List[BaseMessage],
    *,
    model_name: str,
    tenant_id: int,
    session: Optional[KuaiaiChatSession],
    user: Optional[User] = None,
) -> AsyncIterator[bytes]:
    """ChatOpenAI.astream → OpenAI chunk 线格式（逐字节兼容 deepseekChat.ts）。

    SSE 边流边累积，结束后一次落 assistant 行 + token 回填；
    上游失败不回滚已提交 user 行，向流内写通用错误帧（不落敏感信息）。
    """
    parts: List[str] = []
    usage: Dict[str, Optional[int]] = {"prompt_tokens": None, "completion_tokens": None}
    failed = False
    first = True
    try:
        async for chunk in chat.astream(lc_messages):
            _capture_usage(chunk, usage)
            text = message_text(chunk)
            if not text:
                continue
            parts.append(text)
            delta: Dict[str, Any] = {"content": text}
            if first:
                delta["role"] = "assistant"
                first = False
            yield _openai_chunk_payload(model_name, delta)
    except Exception as exc:
        failed = True
        # KR-I5：仅记录异常类型，不落 base_url/key/堆栈细节
        logger.error(
            "KU-AI 流式对话失败 tenant_id={} session_id={} error_type={}",
            tenant_id,
            session.id if session else None,
            type(exc).__name__,
        )
        err = {"error": {"message": "AI 对话调用失败，请稍后重试"}}
        yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n".encode("utf-8")
    yield _SSE_DONE

    if session is not None and parts and not failed:
        try:
            await _persist_assistant_message(
                tenant_id,
                session,
                "".join(parts),
                user=user,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
            )
        except Exception:
            # 取舍：SSE 内容帧与 [DONE] 已发出，此处失败仅影响 assistant 行落库
            # （历史回放缺一条答复），无法也不应向客户端重发；只记日志不放行异常，
            # 避免把 DB 错误细节带进已收尾的流。user 行不回滚（对齐 KR-D6）。
            logger.error(
                "KU-AI assistant 消息落库失败 tenant_id={} session_id={}",
                tenant_id,
                session.id,
            )


async def _agent_sse_stream(
    assembled: AssembledAgent,
    lc_messages: List[BaseMessage],
    *,
    tenant_id: int,
    session: Optional[KuaiaiChatSession],
    user: Optional[User],
    rt_ctx: AiRuntimeContext,
) -> AsyncIterator[bytes]:
    """路径 B 流式：``astream_events`` 真流式 → OpenAI chunk 线格式。

    工具轨迹/终态经 config.callbacks 的 ``_AgentRunTracer`` 在同一次运行内
    收集（不重跑 agent）；流结束后按发生序落 tool/assistant 行。
    """
    tracer = _AgentRunTracer()
    config = {
        "recursion_limit": DEFAULT_RECURSION_LIMIT,
        "callbacks": [tracer],
    }
    # contextvar 在流消费上下文内置/复位（KR-I6：不假设与请求同一 task）
    token = set_ai_context(rt_ctx)
    try:
        async for chunk in agent_to_openai_sse(
            assembled.agent,
            lc_messages,
            model_name=assembled.model_name,
            config=config,
        ):
            yield chunk
    finally:
        reset_ai_context(token)

    if session is None:
        return
    new_messages = tracer.new_messages(len(lc_messages))
    if not new_messages:
        return
    try:
        usage = _sum_usage(new_messages)
        await _persist_agent_messages(
            tenant_id,
            session,
            new_messages,
            user=user,
            agent_id=assembled.profile.id,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
        )
    except Exception:
        # 同 _openai_sse_stream 取舍：流已收尾，落库失败只记日志
        logger.error(
            "KU-AI agent 消息落库失败 tenant_id={} session_id={}",
            tenant_id,
            session.id,
        )


async def create_chat_completion(
    tenant_id: int,
    messages: List[Dict[str, Any]],
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = 0.7,
    stream: bool = False,
    user: Optional[User] = None,
    is_infra_admin: bool = False,
    is_tenant_admin: bool = False,
    context: Optional[Dict[str, Any]] = None,
) -> Union[Dict[str, Any], StreamingResponse]:
    """网关委托入口（签名固定，见 spec 134/135 契约）。

    有 session_id：验归属（tenant+user，不符 404/403，不触达上游）→ 落 user 行
    → 消息表回放重建历史 → 运行 → 落 tool/assistant 行。
    无 session_id：纯转发不落库。
    """
    if not tenant_id:
        raise ValidationError("组织上下文缺失，无法进行 AI 对话")
    if not messages:
        raise ValidationError("messages 不能为空")

    session_ref = _context_session_id(context)
    session: Optional[KuaiaiChatSession] = None
    if session_ref is not None:
        if user is None or getattr(user, "id", None) is None:
            raise ValidationError("会话对话需要登录用户上下文")
        # 归属校验未通过时直接抛错，不会走到上游调用
        session = await get_owned_session(tenant_id, session_ref, user.id)

    # 路径 B 装配：显式 context.agent_id 或 agent 路径默认档案；
    # 授权/归属失败在此抛出（404/403），先于一切上游调用与落库（KR-D9）
    agent_id = _context_int(context, "agent_id")
    agent_path = agent_id is None and _is_agent_path(context)
    assembled: Optional[AssembledAgent] = None
    if agent_id is not None or agent_path:
        assembled = await assemble(
            tenant_id,
            user,
            is_infra_admin,
            is_tenant_admin,
            agent_id,
            agent_path=agent_path,
        )

    # U-2 解耦：目录行可独立支撑对话。先判定本次模型解析是否命中目录行——
    # 命中即跳过 AiRuntimeConfig.load（连接器未启用不再误伤 422）；
    # 站点开关 stream_enabled / custom_system_prompt 挂在连接器配置上，
    # 该路径无从读取，按默认放行（stream_enabled=True、无自定义 prompt）。
    # 仅当实际落到 IntegrationConfig 兜底来源时才 load()：连接器未启用
    # 仍 422（没有目录行兜底本来也发不出请求，语义不变）。
    if assembled is not None:
        # 路径 B 模型已在 assemble 内按 default_model_id 解析，此处只重放
        # 同一解析判定走哪个来源（目录行查询是只读的，无副作用）
        model_row_id = getattr(assembled.profile, "default_model_id", None)
    else:
        # 路径 A 请求级模型：context.model_id（目录行 id）优先，其次
        # 请求 model / 会话 model 名匹配本租户启用 chat 行；皆无 → 目录默认
        model_row_id = _context_int(context, "model_id")
        if model_row_id is None:
            model_row_id = await _match_catalog_model_id(tenant_id, model or "")
        if model_row_id is None and session is not None:
            model_row_id = await _match_catalog_model_id(
                tenant_id, session.model or ""
            )
    catalog_hit = (
        await _resolve_catalog_source(tenant_id, model_row_id, "chat")
        is not None
    )
    stream_enabled = True
    custom_system_prompt: Optional[str] = None
    if not catalog_hit:
        config = await AiRuntimeConfig.load(tenant_id)
        stream_enabled = config.stream_enabled
        custom_system_prompt = config.custom_system_prompt

    # 拒绝路径必须在落库之前：被拒请求不得污染消息历史
    if stream and not stream_enabled:
        raise ValidationError("站点未启用流式对话")

    if assembled is not None:
        # KR-F3：选中档案忽略请求级模型覆盖，只用档案 default_model_id
        model_name = (assembled.model_name or "").strip()
        if not model_name:
            raise ValidationError("未解析到可用对话模型，请检查模型目录配置")
    else:
        chat = await build_chat_model(tenant_id, model_row_id)
        model_name = str(getattr(chat, "model_name", None) or "").strip()
        if not model_name:
            raise ValidationError(
                "未解析到可用对话模型，请检查 AI 连接器或会话模型设置"
            )
        # 请求级 temperature 经 bind 透传，不新建缓存键
        chat = chat.bind(
            temperature=temperature if temperature is not None else 0.7
        )

    if session is not None:
        new_user_content = _last_user_content(messages)
        if new_user_content:
            await _persist_user_message(
                tenant_id,
                session,
                new_user_content,
                user=user,
                agent_id=assembled.profile.id if assembled else None,
            )
        lc_messages = to_lc_messages(
            await _history_rows(tenant_id, session.id)
        )
    else:
        lc_messages = dicts_to_lc_messages(messages)

    # 抽屉页上下文摘要（KR-F4/F6）：注入最前、在 custom_system_prompt 之后；
    # 全宽 chat 不传这些字段故自然不触发；客户端 label 永不进 prompt
    page_summary = await _page_context_summary(context, tenant_id, user)
    if page_summary:
        lc_messages.insert(0, SystemMessage(content=page_summary))
    custom_prompt = (custom_system_prompt or "").strip()
    if custom_prompt:
        lc_messages.insert(0, SystemMessage(content=custom_prompt))

    rt_ctx = AiRuntimeContext(
        tenant_id=tenant_id,
        user=user,
        is_infra_admin=is_infra_admin,
        is_tenant_admin=is_tenant_admin,
        session_id=str(session.id) if session else None,
        agent_id=assembled.profile.id if assembled else None,
    )

    if assembled is not None:
        if stream:
            from core.services.realtime.ai_stream_bridge import (
                wrap_ai_sse_stream,
            )

            stream_iter = _agent_sse_stream(
                assembled,
                lc_messages,
                tenant_id=tenant_id,
                session=session,
                user=user,
                rt_ctx=rt_ctx,
            )
            wrapped = wrap_ai_sse_stream(
                stream_iter,
                tenant_id=tenant_id,
                user_id=user.id if user and getattr(user, "id", None) else 0,
                session_id=str(session.id) if session else None,
            )
            return StreamingResponse(wrapped, media_type="text/event-stream")

        token = set_ai_context(rt_ctx)
        try:
            result = await assembled.agent.ainvoke(
                {"messages": lc_messages},
                config={"recursion_limit": DEFAULT_RECURSION_LIMIT},
            )
        except Exception as exc:
            # KR-I5：仅记录异常类型，不落 base_url/key/堆栈细节
            logger.error(
                "KU-AI agent 对话失败 tenant_id={} session_id={} error_type={}",
                tenant_id,
                session.id if session else None,
                type(exc).__name__,
            )
            # 上游失败是服务端语义：ExternalServiceError → HTTP 502
            # （原 ValidationError→422/400 属客户端语义误标，n2 修正）
            raise ExternalServiceError(
                "LLM", "AI 对话调用失败，请稍后重试"
            ) from exc
        finally:
            reset_ai_context(token)

        all_messages = result.get("messages") if isinstance(result, dict) else []
        new_messages = (
            list(all_messages[len(lc_messages):])
            if isinstance(all_messages, list)
            else []
        )
        content = ""
        for msg in reversed(new_messages):
            if isinstance(msg, AIMessage):
                content = message_text(msg)
                if content:
                    break
        if not content and new_messages:
            content = message_text(new_messages[-1])
        usage = _sum_usage(new_messages)

        if session is not None:
            await _persist_agent_messages(
                tenant_id,
                session,
                new_messages,
                user=user,
                agent_id=assembled.profile.id,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
            )

        return {
            "id": "chatcmpl-kuaiai",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": usage["prompt_tokens"],
                "completion_tokens": usage["completion_tokens"],
                "total_tokens": usage["total_tokens"],
            },
        }

    if stream:
        from core.services.realtime.ai_stream_bridge import wrap_ai_sse_stream

        stream_iter = _openai_sse_stream(
            chat,
            lc_messages,
            model_name=model_name,
            tenant_id=tenant_id,
            session=session,
            user=user,
        )
        wrapped = wrap_ai_sse_stream(
            stream_iter,
            tenant_id=tenant_id,
            user_id=user.id if user and getattr(user, "id", None) else 0,
            session_id=str(session.id) if session else None,
        )
        return StreamingResponse(wrapped, media_type="text/event-stream")

    try:
        response = await chat.ainvoke(lc_messages)
    except Exception as exc:
        # KR-I5：仅记录异常类型，不落 base_url/key/堆栈细节（与流式路径一致）
        logger.error(
            "KU-AI 非流式对话失败 tenant_id={} session_id={} error_type={}",
            tenant_id,
            session.id if session else None,
            type(exc).__name__,
        )
        # 同路径 B：上游失败属服务端语义，ExternalServiceError → HTTP 502
        raise ExternalServiceError(
            "LLM", "AI 对话调用失败，请稍后重试"
        ) from exc
    content = message_text(response)
    usage_meta = getattr(response, "usage_metadata", None) or {}
    prompt_tokens = usage_meta.get("input_tokens")
    completion_tokens = usage_meta.get("output_tokens")
    total_tokens = usage_meta.get("total_tokens")
    finish_reason = (
        (getattr(response, "response_metadata", None) or {}).get("finish_reason")
        or "stop"
    )

    if session is not None:
        await _persist_assistant_message(
            tenant_id,
            session,
            content,
            user=user,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    return {
        "id": getattr(response, "id", None) or "chatcmpl-kuaiai",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    }
