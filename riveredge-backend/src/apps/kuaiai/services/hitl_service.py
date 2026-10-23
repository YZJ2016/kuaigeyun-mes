"""KU-AI 人工确认闸（HITL）服务（spec 193）。

职责边界：本模块只管「确认闸」本身——``kind=write`` 工具识别、
``thread_id`` / ``thread_token`` 服务端生成、挂起 TTL 读取
（``kuaiai.hitl.pending_ttl_minutes``）、checkpoint 挂起元数据、
挂起提取、``core_ai_audit_logs`` 确认审计与过期线程清理。
消息表写行仍由 ``chat_service`` 完成（消息表为回放/审计真源）。

关键决策（spec 193 H1~H4）：

- ``thread_id`` 为 ``"{tenant}:{user}:{session}:{nonce}"``（服务端生成，
  nonce 为每次挂起运行新生成的 uuid4 随机段，不采信客户端）；
- ``thread_token`` = ``thread_id`` + HMAC 摘要，校验失败/越权一律 404；
  resume 经会话行锁 + ``HITL_META_CLAIMED_AT`` CAS 认领保证单次性；
- TTL 默认 30 分钟、合法区间 1~1440；**配置读取异常失败关闭**
  （``BusinessLogicError("确认闸配置读取失败，请稍后重试")``），
  值非法回落 30 并告警；
- 挂起元数据存 checkpoint ``metadata``（不新增表）。
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4

from langgraph.checkpoint.base import CheckpointTuple
from langgraph.checkpoint.serde.types import INTERRUPT
from loguru import logger

from apps.kuaiai.services.tool_catalog_service import manifest_tool_meta
from core.utils.timezone_utils import now_utc
from infra.config.infra_config import infra_settings
from infra.exceptions.exceptions import BusinessLogicError

HITL_TTL_CONFIG_KEY = "kuaiai.hitl.pending_ttl_minutes"
HITL_TTL_DEFAULT_MINUTES = 30
HITL_TTL_MIN_MINUTES = 1
HITL_TTL_MAX_MINUTES = 1440

HITL_META_TOKEN = "kuaiai_hitl_token"
HITL_META_EXPIRES_AT = "kuaiai_hitl_expires_at"
HITL_META_AGENT_ID = "kuaiai_agent_id"
HITL_META_SESSION_ID = "kuaiai_session_id"
HITL_META_USER_ID = "kuaiai_user_id"
# resume 原子认领标记：claim 成功时写入挂起 checkpoint 元数据（ISO 时间）。
# 存在即拒绝再次 resume——写 Tool/审计单次性靠它保证（崩溃残留由
# ``_close_pending_thread``/purge 按宽限收口，见下）。
HITL_META_CLAIMED_AT = "kuaiai_hitl_claimed_at"
# 认领宽限：claimed_at 距今仍在窗口内视为续跑在途，同会话新消息拒发；
# 超过窗口按「认领后崩溃」残留收口（决策审计已在认领时记录，不再重复审计）。
HITL_CLAIM_STALE_SECONDS = 300

HITL_AUDIT_CAPABILITY = "tool_confirm"
HITL_DECISION_TYPES = frozenset({"approve", "reject"})

_TOKEN_SIG_PREFIX = "kuaiai-hitl:"
_TOKEN_SIG_LEN = 24


# ---------------------------------------------------------------- manifest


def tool_label(tool_name: str) -> str:
    """manifest ``label``（SSE 待确认动作展示名）；缺失回 tool 名。"""
    meta = manifest_tool_meta().get(tool_name) or {}
    return str(meta.get("label") or "").strip() or tool_name


# ------------------------------------------------------------- thread 标识


def build_thread_id(tenant_id: int, user_id: int, session_id: int) -> str:
    """服务端 thread_id：``{tenant}:{user}:{session}:{nonce}``。

    nonce 为每次挂起运行新生成的 uuid4 随机段——同会话两次挂起的
    token 必然不同，旧 token 无法重放到新挂起（spec 193：tenant +
    session + 随机）。
    """
    return (
        f"{int(tenant_id)}:{int(user_id)}:{int(session_id)}:{uuid4().hex}"
    )


def session_thread_prefix(
    tenant_id: int, user_id: int, session_id: int
) -> str:
    """会话挂起线程前缀 ``{tenant}:{user}:{session}:``（随机段之前）。"""
    return f"{int(tenant_id)}:{int(user_id)}:{int(session_id)}:"


def _token_signature(thread_id: str) -> str:
    key = (infra_settings.SECRET_KEY or "").encode("utf-8")
    digest = hmac.new(
        key, (_TOKEN_SIG_PREFIX + thread_id).encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return digest[:_TOKEN_SIG_LEN]


def issue_thread_token(thread_id: str) -> str:
    """``thread_id`` + HMAC 摘要；摘要绑定 thread_id，伪造 token 无法通过。"""
    return f"{thread_id}.{_token_signature(thread_id)}"


def parse_thread_token(
    token: str,
) -> Optional[Tuple[int, int, int, str]]:
    """校验 thread_token → ``(tenant_id, user_id, session_id, thread_id)``。

    ``thread_id`` 含随机段，token 自身携带完整 thread_id（resume 直接
    按它定位 checkpoint，不能凭三元组重建）。非法 → ``None``。
    """
    raw = str(token or "").strip()
    if not raw or "." not in raw:
        return None
    thread_id, sig = raw.rsplit(".", 1)
    if not thread_id or not sig:
        return None
    if not hmac.compare_digest(sig, _token_signature(thread_id)):
        return None
    parts = thread_id.split(":")
    if len(parts) != 4:
        return None
    nonce = parts[3]
    if not nonce or len(nonce) > 64 or not nonce.isalnum():
        return None
    try:
        tenant_id, user_id, session_id = (int(p) for p in parts[:3])
    except ValueError:
        return None
    if tenant_id <= 0 or user_id <= 0 or session_id <= 0:
        return None
    return tenant_id, user_id, session_id, thread_id


# ------------------------------------------------------------------ TTL


async def pending_ttl_minutes(tenant_id: int) -> int:
    """挂起 TTL 分钟数。

    - 行缺失 → 默认 30；
    - ``config_value.minutes`` 非法（类型/区间）→ 默认 30 + 脱敏告警；
    - **读取异常 → ``BusinessLogicError`` 失败关闭**（不猜 TTL，不进挂起）。
    """
    from infra.services.tenant_service import TenantService

    try:
        config = await TenantService().get_tenant_config(
            tenant_id, HITL_TTL_CONFIG_KEY
        )
    except Exception as exc:
        logger.warning(
            "HITL 挂起 TTL 配置读取失败，失败关闭 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        raise BusinessLogicError("确认闸配置读取失败，请稍后重试") from exc
    if config is None:
        return HITL_TTL_DEFAULT_MINUTES
    value = getattr(config, "config_value", None)
    raw = value.get("minutes") if isinstance(value, dict) else None
    if (
        isinstance(raw, bool)
        or not isinstance(raw, int)
        or not (HITL_TTL_MIN_MINUTES <= raw <= HITL_TTL_MAX_MINUTES)
    ):
        logger.warning(
            "HITL 挂起 TTL 配置非法，回落默认 {} 分钟 tenant_id={}",
            HITL_TTL_DEFAULT_MINUTES,
            tenant_id,
        )
        return HITL_TTL_DEFAULT_MINUTES
    return raw


# ----------------------------------------------------- checkpoint 挂起元数据


def hitl_checkpoint_config(
    *,
    tenant_id: int,
    thread_id: str,
    thread_token: str,
    expires_at: datetime,
    agent_id: int,
    session_id: int,
    user_id: int,
) -> Dict[str, Any]:
    """``RunnableConfig`` 片段：``configurable`` + 挂起元数据 ``metadata``。"""
    return {
        "configurable": {"tenant_id": tenant_id, "thread_id": thread_id},
        "metadata": {
            HITL_META_TOKEN: thread_token,
            HITL_META_EXPIRES_AT: expires_at.isoformat(),
            HITL_META_AGENT_ID: agent_id,
            HITL_META_SESSION_ID: session_id,
            HITL_META_USER_ID: user_id,
        },
    }


def parse_expires_at(raw: Any) -> Optional[datetime]:
    """ISO 字符串 → aware datetime；非法/缺失 → ``None``（按未过期处理并拒绝写入）。"""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ------------------------------------------------------- checkpoint 挂起提取


def pending_interrupt_values(tpl: Any) -> List[Any]:
    """最新 checkpoint tuple 中的 ``__interrupt__`` pending writes → Interrupt 列表。"""
    values: List[Any] = []
    for _task_id, channel, value in (getattr(tpl, "pending_writes", None) or []):
        if channel != INTERRUPT:
            continue
        if isinstance(value, (list, tuple)):
            values.extend(v for v in value)
        else:
            values.append(value)
    return values


def has_pending_interrupt(tpl: Any) -> bool:
    return bool(pending_interrupt_values(tpl))


def pending_action_requests(interrupts: Iterable[Any]) -> List[Dict[str, Any]]:
    """Interrupt ``.value["action_requests"]`` 展开为 ``{name, args}`` 列表。"""
    out: List[Dict[str, Any]] = []
    for interrupt in interrupts:
        value = getattr(interrupt, "value", None)
        if isinstance(interrupt, dict):
            value = interrupt.get("value")
        if not isinstance(value, dict):
            continue
        for req in value.get("action_requests") or []:
            if not isinstance(req, dict):
                continue
            out.append(
                {
                    "name": str(req.get("name") or ""),
                    "args": dict(req.get("args") or {}),
                    "description": req.get("description"),
                }
            )
    return out


def unanswered_tool_calls(messages: Sequence[Any]) -> List[Dict[str, Any]]:
    """checkpoint state messages 中尚无 ToolMessage 应答的 tool_calls（按 id 去重）。"""
    answered = {
        getattr(m, "tool_call_id", None)
        for m in messages
        if getattr(m, "tool_call_id", None)
    }
    seen = set()
    calls: List[Dict[str, Any]] = []
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            call_id = tc.get("id")
            if not call_id or call_id in answered or call_id in seen:
                continue
            seen.add(call_id)
            calls.append(dict(tc))
    return calls


def checkpoint_messages(tpl: Any) -> List[Any]:
    """``tpl.checkpoint["channel_values"]["messages"]``（缺失回空表）。"""
    try:
        values = tpl.checkpoint.get("channel_values") or {}
    except AttributeError:
        return []
    msgs = values.get("messages")
    return list(msgs) if isinstance(msgs, (list, tuple)) else []


# ------------------------------------------------------------- 认领（CAS）


async def claim_pending_token(saver: Any, tpl: Any) -> bool:
    """原子认领挂起：把 ``HITL_META_CLAIMED_AT`` 写回该 checkpoint 元数据。

    调用前提：``resume_chat_completion`` 已在会话行锁事务内完成
    token/pending/过期/决策校验——并发 resume/收口由同一把会话行锁
    串行化，后到者重读即见 claimed 标记而 404。本函数按主键条件更新
    兜底并发清线：行已被删除（如过期 purge）→ 更新 0 行返回 ``False``，
    调用方按 404 处理，保证 ``Command(resume)`` 与决策审计单次性。
    """
    from apps.kuaiai.models.checkpoint import KuaiaiAgentCheckpoint

    configurable = (getattr(tpl, "config", None) or {}).get("configurable") or {}
    checkpoint_id = configurable.get("checkpoint_id")
    if not checkpoint_id:
        return False
    row = await (
        KuaiaiAgentCheckpoint.filter(
            tenant_id=int(configurable.get("tenant_id") or 0),
            thread_id=str(configurable.get("thread_id") or ""),
            checkpoint_ns=str(configurable.get("checkpoint_ns") or ""),
            checkpoint_id=str(checkpoint_id),
        )
        .first()
    )
    if row is None:
        return False
    meta = dict(getattr(tpl, "metadata", None) or {})
    meta[HITL_META_CLAIMED_AT] = now_utc().isoformat()
    meta_type, meta_blob = saver.serde.dumps_typed(meta)
    updated = await KuaiaiAgentCheckpoint.filter(id=row.id).update(
        metadata_type=meta_type, metadata_blob=meta_blob
    )
    return bool(updated)


# ------------------------------------------------------------------ 审计


async def audit_tool_confirm(
    tenant_id: int,
    user_id: Optional[int],
    tool_name: str,
    action: str,
    *,
    error: Optional[str] = None,
) -> None:
    """确认/拒绝/过期审计：``core_ai_audit_logs`` capability=tool_confirm。

    route = ``ai/tool/{name}/{approve|reject|expire}``；**不写参数值**。
    审计写失败只记日志，不把已完成动作变失败（与 ``_audit_tool_call`` 同策略）。
    """
    try:
        from core.models.ai_audit_log import AiAuditLog

        await AiAuditLog.create(
            tenant_id=tenant_id,
            user_id=user_id,
            route=f"ai/tool/{tool_name}/{action}"[:256],
            capability=HITL_AUDIT_CAPABILITY,
            status_code=200 if error is None else 400,
            error_message=error,
        )
    except Exception as exc:
        logger.warning(
            "HITL 确认审计写入失败 tool={} action={} error_type={}",
            tool_name,
            action,
            type(exc).__name__,
        )


# ------------------------------------------------------------- 过期清理


def _tuple_from_row(
    saver: Any, row: Any, write_rows: List[Any]
) -> Optional[CheckpointTuple]:
    """批量路径：checkpoint 行 + write 行 → ``CheckpointTuple``。

    反序列化失败返回 ``None``（只记脱敏日志，清理仍照常删行）。
    """
    try:
        checkpoint = saver.serde.loads_typed(
            (row.checkpoint_type, bytes(row.checkpoint_blob))
        )
        metadata = saver.serde.loads_typed(
            (row.metadata_type, bytes(row.metadata_blob))
        )
        pending = [
            (
                w.task_id,
                w.channel,
                saver.serde.loads_typed((w.value_type, bytes(w.value_blob))),
            )
            for w in write_rows
        ]
    except Exception as exc:
        logger.warning(
            "HITL 过期清理反序列化失败 thread_id={} error_type={}",
            getattr(row, "thread_id", None),
            type(exc).__name__,
        )
        return None
    return CheckpointTuple(
        config={
            "configurable": {
                "tenant_id": row.tenant_id,
                "thread_id": row.thread_id,
                "checkpoint_ns": row.checkpoint_ns,
                "checkpoint_id": row.checkpoint_id,
            }
        },
        checkpoint=checkpoint,
        metadata=metadata,
        parent_config=None,
        pending_writes=pending,
    )


async def _persist_expire_close_rows(
    tenant_id: int, session_id: Any, tpl: CheckpointTuple, meta: Dict[str, Any]
) -> None:
    """purge 收口：按 checkpoint metadata 的 session 写「已过期」tool 行。

    不写行的会话（已软删/异常）只记日志，不阻断审计与删行；写行失败
    同样记日志放行——清线优先，残留收口由后续新消息兜底。
    """
    try:
        from apps.kuaiai.models.chat import KuaiaiChatSession
        from apps.kuaiai.services.chat_service import _persist_hitl_close_rows

        session = await KuaiaiChatSession.get_or_none(
            tenant_id=tenant_id,
            id=int(session_id),
            deleted_at__isnull=True,
        )
        if session is None:
            return
        # 系统任务发起，无操作人：user=None（行审计字段留空）
        await _persist_hitl_close_rows(
            tenant_id,
            session,
            None,
            tpl,
            content="操作确认已过期，已取消",
            agent_id=meta.get(HITL_META_AGENT_ID),
        )
    except Exception as exc:
        logger.error(
            "HITL 过期收口写行失败 tenant_id={} session_id={} error_type={}",
            tenant_id,
            session_id,
            type(exc).__name__,
        )


async def purge_expired_pending() -> Dict[str, Any]:
    """逐租户清理：挂起超 TTL 的线程写收口行、记 ``expire`` 审计并整线程删除。

    按线程最新 checkpoint 行龄判定（活跃线程旧行不误删；全部行一次取回
    在内存分组，不逐 thread 查）；按 metadata 的 session_id 写「操作确认
    已过期」tool 收口行，防悬空 tool_calls 被历史回放（B-M2）；
    配置读取失败的租户跳过（失败关闭不清理）。
    Taskiq ``kuaiai_hitl_purge_tick`` 调用。
    """
    from apps.kuaiai.models.checkpoint import (
        KuaiaiAgentCheckpoint,
        KuaiaiAgentCheckpointWrite,
    )
    from apps.kuaiai.services.checkpoint_saver import TortoiseCheckpointSaver
    from infra.domain.tenant_context import unscoped, with_tenant

    saver = TortoiseCheckpointSaver()
    purged = 0
    tenants_skipped = 0
    async with unscoped(reason="HITL 过期清理枚举租户", resource="kuaiai_checkpoints"):
        tenant_ids = await (
            KuaiaiAgentCheckpoint.all()
            .distinct()
            .values_list("tenant_id", flat=True)
        )
    for tenant_id in tenant_ids or []:
        async with with_tenant(tenant_id):
            try:
                ttl = await pending_ttl_minutes(tenant_id)
            except Exception:
                tenants_skipped += 1
                continue
            cutoff = now_utc() - timedelta(minutes=ttl)
            # 批量取本租户全部 checkpoint 行，按 thread 取最新行（替代
            # 逐 thread 查最新的 N+1；id 大者后写，兼作 created_at 同值仲裁）
            latest_by_thread: Dict[str, Any] = {}
            for row in await KuaiaiAgentCheckpoint.filter(
                tenant_id=tenant_id
            ).all():
                cur = latest_by_thread.get(row.thread_id)
                if cur is None or (row.id or 0) > (cur.id or 0):
                    latest_by_thread[row.thread_id] = row
            expired_rows = []
            for row in latest_by_thread.values():
                created_at = row.created_at
                if created_at is None:
                    continue
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if created_at < cutoff:
                    expired_rows.append(row)
            if not expired_rows:
                continue
            # 过期行 pending writes 一次批量取回，按 checkpoint_id 分组
            write_rows = await (
                KuaiaiAgentCheckpointWrite.filter(
                    tenant_id=tenant_id,
                    checkpoint_id__in=[r.checkpoint_id for r in expired_rows],
                )
                .order_by("task_id", "idx")
                .all()
            )
            writes_by_cid: Dict[str, List[Any]] = {}
            for w in write_rows:
                writes_by_cid.setdefault(w.checkpoint_id, []).append(w)
            for row in expired_rows:
                tpl = _tuple_from_row(
                    saver, row, writes_by_cid.get(row.checkpoint_id, [])
                )
                if tpl is not None:
                    meta = tpl.metadata or {}
                    user_id = meta.get(HITL_META_USER_ID)
                    session_id = meta.get(HITL_META_SESSION_ID)
                    interrupts = pending_interrupt_values(tpl)
                    if session_id:
                        await _persist_expire_close_rows(
                            tenant_id, session_id, tpl, meta
                        )
                    for req in pending_action_requests(interrupts):
                        await audit_tool_confirm(
                            tenant_id,
                            user_id,
                            str(req.get("name") or ""),
                            "expire",
                        )
                await saver.adelete_thread(row.thread_id, tenant_id=tenant_id)
                purged += 1
    return {"purged_threads": purged, "tenants_skipped": tenants_skipped}
