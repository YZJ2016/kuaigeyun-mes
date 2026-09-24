"""KU-AI 会话/消息服务（REST 薄层 + 归属校验 helper）。

归属校验统一入口：get_owned_session —— tenant_id + user_id 双过滤，
跨租户 404（不可见）、同租户跨用户 403，调用方不得在失败时继续触达上游。
"""

from __future__ import annotations

from typing import List, Optional, Tuple, Union

from apps.kuaiai.models.chat import KuaiaiChatMessage, KuaiaiChatSession
from apps.kuaiai.schemas.chat import ChatSessionCreate, ChatSessionUpdate
from core.utils.timezone_utils import now_utc
from infra.exceptions.exceptions import AuthorizationError, NotFoundError, ValidationError
from infra.models.user import User


def _parse_session_ref(session_ref: Union[int, str]) -> dict:
    """把 REST path int id 或 context 传入的 id/uuid 归一为查询条件。"""
    if isinstance(session_ref, int):
        return {"id": session_ref}
    ref = str(session_ref or "").strip()
    if not ref:
        raise ValidationError("session_id 不能为空")
    if ref.isdigit():
        return {"id": int(ref)}
    return {"uuid": ref}


async def get_owned_session(
    tenant_id: int,
    session_ref: Union[int, str],
    user_id: int,
) -> KuaiaiChatSession:
    """按 tenant_id + user_id 校验会话归属。

    跨租户（含不存在/已软删）→ 404；同租户但归属他人 → 403。
    """
    filters = _parse_session_ref(session_ref)
    session = await KuaiaiChatSession.get_or_none(
        tenant_id=tenant_id, deleted_at__isnull=True, **filters
    )
    if session is None:
        raise NotFoundError("会话", str(session_ref))
    if session.user_id != user_id:
        raise AuthorizationError("无权访问该会话")
    return session


async def list_sessions(
    tenant_id: int,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[KuaiaiChatSession], int]:
    q = KuaiaiChatSession.filter(
        tenant_id=tenant_id, user_id=user_id, deleted_at__isnull=True
    )
    total = await q.count()
    # -created_at 兜底：last_message_at 为 NULL 的新会话不至于沉底/次序不定
    items = await (
        q.order_by("-last_message_at", "-created_at", "-id")
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return items, total


async def create_session(
    tenant_id: int,
    user: User,
    payload: ChatSessionCreate,
) -> KuaiaiChatSession:
    if payload.agent_id is not None:
        # S2：档案表已落地，挂接前复核本租户归属（跨租户 404）
        from apps.kuaiai.services.agent_service import get_profile

        await get_profile(tenant_id, payload.agent_id)
    return await KuaiaiChatSession.create(
        tenant_id=tenant_id,
        user_id=user.id,
        title=(payload.title or "").strip(),
        agent_id=payload.agent_id,
        model=(payload.model or "").strip() or None,
        created_by=user.id,
        created_by_name=(user.full_name or user.username),
    )


async def update_session(
    tenant_id: int,
    user: User,
    session_id: int,
    payload: ChatSessionUpdate,
) -> KuaiaiChatSession:
    session = await get_owned_session(tenant_id, session_id, user.id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("agent_id") is not None:
        # S2：挂接档案前复核本租户归属（跨租户 404）
        from apps.kuaiai.services.agent_service import get_profile

        await get_profile(tenant_id, data["agent_id"])
    if "title" in data and data["title"] is not None:
        data["title"] = data["title"].strip()
    if "model" in data and data["model"] is not None:
        data["model"] = data["model"].strip() or None
    data["updated_by"] = user.id
    data["updated_by_name"] = user.full_name or user.username
    await session.update_from_dict(data).save()
    return session


async def delete_session(tenant_id: int, user_id: int, session_id: int) -> None:
    """软删会话及其消息（同事务）。"""
    from tortoise import transactions

    session = await get_owned_session(tenant_id, session_id, user_id)
    now = now_utc()
    async with transactions.in_transaction():
        await KuaiaiChatMessage.filter(
            tenant_id=tenant_id, session_id=session.id, deleted_at__isnull=True
        ).update(deleted_at=now)
        session.deleted_at = now
        await session.save()


async def list_messages(
    tenant_id: int,
    session: KuaiaiChatSession,
) -> List[KuaiaiChatMessage]:
    return await KuaiaiChatMessage.filter(
        tenant_id=tenant_id, session_id=session.id, deleted_at__isnull=True
    ).order_by("seq")
