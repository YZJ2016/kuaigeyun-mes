"""KU-AI Agent 档案使用授权（KR-D9）。

固定入口（下游 agent_assembler / options 消费，签名钉死不得改名）：

- ``check_use_grant(tenant_id, profile, user) -> bool``
  ROLE：命中 user 任一角色 id；USER：target_id == user.id；
  悬挂 role/user id 不产生授权；未知/空 grant_mode 一律 False（失败关闭）。
- ``usable_profile_ids(tenant_id, user) -> set[int]``
  供 agents/options 过滤：仅启用档案 + 当前用户名单命中。

模式切换同事务清空对侧名单的逻辑在 agent_service 档案保存处
（_clear_opposite_grants），本模块只管名单读写与命中判定。
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

from tortoise import transactions

from apps.kuaiai.constants import (
    GRANT_MODE_ROLE,
    GRANT_MODE_USER,
    GRANT_TARGET_TYPE_ROLE,
    GRANT_TARGET_TYPE_USER,
    STATUS_ENABLED,
)
from apps.kuaiai.models.agent import KuaiaiAgentGrant, KuaiaiAgentProfile
from core.utils.timezone_utils import now_utc
from infra.exceptions.exceptions import BusinessLogicError
from infra.models.user import User


async def _user_role_ids(user: Any) -> Set[int]:
    """当前用户角色 id 集（经 core_user_roles；空上下文 → 空集，失败关闭）。"""
    uid = getattr(user, "id", None)
    if not uid:
        return set()
    from core.models.user_role import UserRole

    rows = await UserRole.filter(user_id=uid).values_list("role_id", flat=True)
    return {int(r) for r in rows}


def _target_type_for_mode(grant_mode: str) -> str:
    return (
        GRANT_TARGET_TYPE_ROLE
        if grant_mode == GRANT_MODE_ROLE
        else GRANT_TARGET_TYPE_USER
    )


async def check_use_grant(
    tenant_id: int, profile: KuaiaiAgentProfile, user: Any
) -> bool:
    """单档案使用权判定（KR-D9：悬挂 id 不产生授权，失败关闭）。"""
    uid = getattr(user, "id", None)
    if not uid or not getattr(profile, "id", None):
        return False
    mode = (profile.grant_mode or "").strip().upper()
    if mode == GRANT_MODE_USER:
        return await KuaiaiAgentGrant.filter(
            tenant_id=tenant_id,
            agent_id=profile.id,
            target_type=GRANT_TARGET_TYPE_USER,
            target_id=uid,
            deleted_at__isnull=True,
        ).exists()
    if mode == GRANT_MODE_ROLE:
        role_ids = await _user_role_ids(user)
        if not role_ids:
            return False
        return await KuaiaiAgentGrant.filter(
            tenant_id=tenant_id,
            agent_id=profile.id,
            target_type=GRANT_TARGET_TYPE_ROLE,
            target_id__in=list(role_ids),
            deleted_at__isnull=True,
        ).exists()
    return False


async def usable_profile_ids(tenant_id: int, user: Any) -> Set[int]:
    """当前用户有使用权的启用档案 id 集（供 agents/options 过滤）。"""
    uid = getattr(user, "id", None)
    if not uid:
        return set()
    profiles = await KuaiaiAgentProfile.filter(
        tenant_id=tenant_id, status=STATUS_ENABLED, deleted_at__isnull=True
    ).all()
    if not profiles:
        return set()
    grants = await KuaiaiAgentGrant.filter(
        tenant_id=tenant_id,
        agent_id__in=[p.id for p in profiles],
        deleted_at__isnull=True,
    ).all()
    by_agent: Dict[int, List[KuaiaiAgentGrant]] = {}
    for g in grants:
        by_agent.setdefault(g.agent_id, []).append(g)
    role_ids = await _user_role_ids(user)
    usable: Set[int] = set()
    for p in profiles:
        rows = by_agent.get(p.id, [])
        mode = (p.grant_mode or "").strip().upper()
        if mode == GRANT_MODE_USER:
            if any(
                g.target_type == GRANT_TARGET_TYPE_USER and g.target_id == uid
                for g in rows
            ):
                usable.add(p.id)
        elif mode == GRANT_MODE_ROLE:
            if any(
                g.target_type == GRANT_TARGET_TYPE_ROLE
                and g.target_id in role_ids
                for g in rows
            ):
                usable.add(p.id)
    return usable


async def list_grants(
    tenant_id: int, profile: KuaiaiAgentProfile
) -> Dict[str, Any]:
    """档案当前模式的授权名单（GET /agents/{id}/grants 响应）。"""
    rows = await KuaiaiAgentGrant.filter(
        tenant_id=tenant_id,
        agent_id=profile.id,
        target_type=_target_type_for_mode(
            (profile.grant_mode or "").strip().upper()
        ),
        deleted_at__isnull=True,
    ).order_by("id").all()
    return {
        "agent_id": profile.id,
        "grant_mode": (profile.grant_mode or "").strip().upper(),
        "target_ids": [g.target_id for g in rows],
    }


async def replace_grants(
    tenant_id: int,
    profile: KuaiaiAgentProfile,
    target_ids: List[int],
    user: User,
) -> Dict[str, Any]:
    """整体替换当前模式的授权名单（同事务软删旧行 + 写新行）。

    启用档案名单不得为空（KR-D9 → 400）；停用允许清空。
    """
    mode = (profile.grant_mode or "").strip().upper()
    target_type = _target_type_for_mode(mode)
    ids = sorted({int(i) for i in target_ids if isinstance(i, int) and i > 0})
    if profile.status == STATUS_ENABLED and not ids:
        raise BusinessLogicError("启用档案的授权名单不得为空，请先停用档案")

    name = getattr(user, "full_name", None) or getattr(user, "username", None)
    now = now_utc()
    async with transactions.in_transaction():
        await KuaiaiAgentGrant.filter(
            tenant_id=tenant_id,
            agent_id=profile.id,
            target_type=target_type,
            deleted_at__isnull=True,
        ).update(deleted_at=now, updated_by=user.id, updated_by_name=name)
        for tid in ids:
            await KuaiaiAgentGrant.create(
                tenant_id=tenant_id,
                agent_id=profile.id,
                target_type=target_type,
                target_id=tid,
                created_by=user.id,
                created_by_name=name,
                updated_by=user.id,
                updated_by_name=name,
            )
    return {"agent_id": profile.id, "grant_mode": mode, "target_ids": ids}
