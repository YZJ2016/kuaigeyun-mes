"""KU-AI Agent 档案服务（KR-D8/D9）：profiles CRUD + options + 模式切换清对侧。

规则（spec 135 / KR-D8/D9）：
- grant_mode 仅 ROLE|USER 互斥；保存档案切换模式时同一事务清空对侧名单；
- 启用（status=启用）档案当前模式名单不得为空 → 400；停用允许空；
- 管理 list = 本租户全部档案；options 仅当前用户有使用权的启用档案；
- enabled_tools 仅五值闭集子集，未知名 400；写 Tool 默认不勾（由前端/默认值保证）；
- default_model_id 须指向本租户 model_type=chat 的启用行，跨租户/不存在 404，
  类型或状态不符 400；
- knowledge_ids / mcp_server_ids 存 JSONB（形态归一）；发送时归属复核在
  检索 facade / ``load_agent_mcp_tools``（本租户启用未删行；陈旧 id 静默过滤）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from tortoise import transactions

from apps.kuaiai.constants import (
    CATALOG_STATUSES,
    ENABLED_TOOL_NAMES,
    GRANT_MODES,
    GRANT_TARGET_TYPE_ROLE,
    GRANT_TARGET_TYPE_USER,
    MODEL_TYPE_CHAT,
    STATUS_ENABLED,
)
from apps.kuaiai.models.agent import KuaiaiAgentGrant, KuaiaiAgentProfile
from apps.kuaiai.models.catalog import KuaiaiLlmModel
from apps.kuaiai.schemas.agent import AgentProfileCreate, AgentProfileUpdate
from apps.kuaiai.services import grant_service
from core.utils.timezone_utils import now_utc
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError
from infra.models.user import User


def _audit_create(user: Optional[User]) -> Dict[str, Any]:
    if user is None or getattr(user, "id", None) is None:
        return {}
    name = getattr(user, "full_name", None) or getattr(user, "username", None)
    return {
        "created_by": user.id,
        "created_by_name": name,
        "updated_by": user.id,
        "updated_by_name": name,
    }


def _audit_update(user: Optional[User]) -> Dict[str, Any]:
    if user is None or getattr(user, "id", None) is None:
        return {}
    return {
        "updated_by": user.id,
        "updated_by_name": getattr(user, "full_name", None)
        or getattr(user, "username", None),
    }


def _normalize_id_list(raw: Optional[List[int]], field: str) -> List[int]:
    """JSONB id 列表形态归一：去重保序，仅接受正整数。"""
    if raw is None:
        return []
    out: List[int] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise BusinessLogicError(f"{field} 仅接受正整数 id 列表")
        if item not in out:
            out.append(item)
    return out


def _normalize_tools(raw: Optional[List[str]]) -> List[str]:
    """enabled_tools 闭集校验（KR-D10）：未知名 400；去重保序。"""
    if raw is None:
        return []
    out: List[str] = []
    unknown: List[str] = []
    for item in raw:
        name = str(item or "").strip()
        if not name:
            continue
        if name not in ENABLED_TOOL_NAMES:
            unknown.append(name)
            continue
        if name not in out:
            out.append(name)
    if unknown:
        raise BusinessLogicError(f"未知工具名: {', '.join(unknown)}")
    return out


def _require_grant_mode(value: Optional[str]) -> str:
    mode = (value or "").strip().upper()
    if mode not in GRANT_MODES:
        raise BusinessLogicError("grant_mode 仅允许 ROLE|USER")
    return mode


def _require_status(value: Optional[str]) -> str:
    status = (value or "").strip()
    if status not in CATALOG_STATUSES:
        raise BusinessLogicError("status 仅允许 启用|停用")
    return status


async def _require_chat_model(tenant_id: int, model_id: int) -> KuaiaiLlmModel:
    """default_model_id 归属复核：本租户行才接受（跨租户/不存在 404）。"""
    model = await KuaiaiLlmModel.get_or_none(
        tenant_id=tenant_id, id=model_id, deleted_at__isnull=True
    )
    if model is None:
        raise NotFoundError("LLM 模型", str(model_id))
    if model.model_type != MODEL_TYPE_CHAT or model.status != STATUS_ENABLED:
        raise BusinessLogicError("default_model_id 须指向本租户 chat 类型的启用模型行")
    return model


async def _grant_count(tenant_id: int, agent_id: int, grant_mode: str) -> int:
    target_type = (
        GRANT_TARGET_TYPE_ROLE
        if grant_mode == "ROLE"
        else GRANT_TARGET_TYPE_USER
    )
    return await KuaiaiAgentGrant.filter(
        tenant_id=tenant_id,
        agent_id=agent_id,
        target_type=target_type,
        deleted_at__isnull=True,
    ).count()


async def _clear_opposite_grants(
    tenant_id: int, agent_id: int, grant_mode: str, now
) -> int:
    """同事务清空对侧名单（KR-D9 模式切换语义）。须在事务内调用。"""
    opposite = (
        GRANT_TARGET_TYPE_USER
        if grant_mode == "ROLE"
        else GRANT_TARGET_TYPE_ROLE
    )
    return await KuaiaiAgentGrant.filter(
        tenant_id=tenant_id,
        agent_id=agent_id,
        target_type=opposite,
        deleted_at__isnull=True,
    ).update(deleted_at=now)


async def get_profile(tenant_id: int, agent_id: int) -> KuaiaiAgentProfile:
    """本租户档案查询：跨租户/软删/不存在一律 404（KR-I1）。"""
    profile = await KuaiaiAgentProfile.get_or_none(
        tenant_id=tenant_id, id=agent_id, deleted_at__isnull=True
    )
    if profile is None:
        raise NotFoundError("Agent 档案", str(agent_id))
    return profile


async def list_profiles(
    tenant_id: int, page: int = 1, page_size: int = 20
) -> Tuple[List[KuaiaiAgentProfile], int]:
    """管理 list：本租户全部档案（不按使用权过滤）。"""
    q = KuaiaiAgentProfile.filter(tenant_id=tenant_id, deleted_at__isnull=True)
    total = await q.count()
    items = await (
        q.order_by("id").offset((page - 1) * page_size).limit(page_size)
    )
    return items, total


async def profile_options(
    tenant_id: int, user: User
) -> List[KuaiaiAgentProfile]:
    """options：仅当前用户有使用权的启用档案（KR-D9）。"""
    usable = await grant_service.usable_profile_ids(tenant_id, user)
    if not usable:
        return []
    return await KuaiaiAgentProfile.filter(
        tenant_id=tenant_id,
        id__in=list(usable),
        status=STATUS_ENABLED,
        deleted_at__isnull=True,
    ).order_by("id").all()


async def create_profile(
    tenant_id: int, user: User, payload: AgentProfileCreate
) -> KuaiaiAgentProfile:
    # 先校验纯字段规则（不触库），再做归属/重名查询（KR-I3：失败先于 DB 写入）
    status = (
        _require_status(payload.status) if payload.status is not None else "停用"
    )
    grant_mode = _require_grant_mode(payload.grant_mode)
    enabled_tools = _normalize_tools(payload.enabled_tools)
    knowledge_ids = _normalize_id_list(payload.knowledge_ids, "knowledge_ids")
    mcp_server_ids = _normalize_id_list(payload.mcp_server_ids, "mcp_server_ids")
    name = payload.name.strip()
    dup = await KuaiaiAgentProfile.get_or_none(
        tenant_id=tenant_id, name=name, deleted_at__isnull=True
    )
    if dup is not None:
        raise BusinessLogicError(f"档案名称 {name} 已存在")
    if payload.default_model_id is not None:
        await _require_chat_model(tenant_id, payload.default_model_id)
    if status == STATUS_ENABLED:
        # 新建档案尚无名单，启用必为空名单 → 400（先停用建档，再配名单，再启用）
        raise BusinessLogicError("启用档案的授权名单不得为空，请先停用建档再配置名单")
    return await KuaiaiAgentProfile.create(
        tenant_id=tenant_id,
        name=name,
        description=payload.description,
        system_prompt=payload.system_prompt,
        default_model_id=payload.default_model_id,
        knowledge_ids=knowledge_ids,
        enabled_tools=enabled_tools,
        mcp_server_ids=mcp_server_ids,
        status=status,
        grant_mode=grant_mode,
        **_audit_create(user),
    )


async def update_profile(
    tenant_id: int, user: User, agent_id: int, payload: AgentProfileUpdate
) -> KuaiaiAgentProfile:
    profile = await get_profile(tenant_id, agent_id)
    data = payload.model_dump(exclude_unset=True)

    if "name" in data and data["name"] is not None:
        name = data["name"].strip()
        dup = await KuaiaiAgentProfile.get_or_none(
            tenant_id=tenant_id, name=name, deleted_at__isnull=True
        )
        if dup is not None and dup.id != profile.id:
            raise BusinessLogicError(f"档案名称 {name} 已存在")
        data["name"] = name
    # 非空列显式传 null 视为非法（避免写入 NULL）；可空列 null 表示清空
    if "name" in data and data["name"] is None:
        raise BusinessLogicError("name 不允许为空")
    if "status" in data:
        data["status"] = _require_status(data["status"])
    if "grant_mode" in data:
        data["grant_mode"] = _require_grant_mode(data["grant_mode"])
    if "enabled_tools" in data:
        data["enabled_tools"] = _normalize_tools(data["enabled_tools"])
    if "knowledge_ids" in data:
        data["knowledge_ids"] = _normalize_id_list(
            data["knowledge_ids"], "knowledge_ids"
        )
    if "mcp_server_ids" in data:
        data["mcp_server_ids"] = _normalize_id_list(
            data["mcp_server_ids"], "mcp_server_ids"
        )
    if "default_model_id" in data and data["default_model_id"] is not None:
        await _require_chat_model(tenant_id, data["default_model_id"])

    new_status = data.get("status", profile.status)
    new_mode = data.get("grant_mode", profile.grant_mode)
    data.update(_audit_update(user))

    async with transactions.in_transaction():
        # 模式切换：同一事务清空对侧名单（KR-D9）
        if "grant_mode" in data and data["grant_mode"] != profile.grant_mode:
            await _clear_opposite_grants(
                tenant_id, profile.id, data["grant_mode"], now_utc()
            )
        await profile.update_from_dict(data).save()
        if new_status == STATUS_ENABLED:
            count = await _grant_count(tenant_id, profile.id, new_mode)
            if count == 0:
                raise BusinessLogicError("启用档案的授权名单不得为空")
    return profile


async def delete_profile(tenant_id: int, user: User, agent_id: int) -> None:
    """软删档案及其授权名单（同事务）。"""
    profile = await get_profile(tenant_id, agent_id)
    now = now_utc()
    async with transactions.in_transaction():
        await KuaiaiAgentGrant.filter(
            tenant_id=tenant_id, agent_id=profile.id, deleted_at__isnull=True
        ).update(deleted_at=now, **_audit_update(user))
        profile.deleted_at = now
        profile.update_from_dict(_audit_update(user))
        await profile.save()
