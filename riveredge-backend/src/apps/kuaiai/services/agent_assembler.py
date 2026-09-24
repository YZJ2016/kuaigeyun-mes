"""KU-AI Agent 档案装配（KR-D8/D9，设计 §7 三步流第 3 步：发送时装配）。

每请求 ``create_agent``（图构造毫秒级，不缓存编译产物）：

1. 查档案：tenant + 未删除 + ``status=启用``；跨租户/不存在 → 404，
   停用 → 403（档案存在但不可用，不静默降级）；
2. ``grant_service.check_use_grant`` 使用权校验 → 不过 403
   （配置权 ≠ 使用权；悬挂 role/user id 不产生授权）；
3. 装配：``build_chat_model(tenant_id, profile.default_model_id)`` +
   ``registry_to_lc_tools(profile.enabled_tools ∩ ENABLED_TOOL_NAMES)`` +
   ``build_tool_guard_middleware()`` → ``build_agent``。

``knowledge_ids`` 不进 tools 装配：``search_knowledge`` handler 调用时经
``ctx.agent_id`` 回查档案取库列表（S3 已落地）；``mcp_server_ids``（S4
已落地）经 ``load_agent_mcp_tools`` 建连装配为 MCP tools，守卫由
``build_mcp_aware_tool_guard`` 组合（MCP 名集合放行，闭集名走 core
guard）。档案勾选仅经闭集校验存 JSONB。

默认档案（KR-D8）：仅当未传 ``agent_id`` 且调用方判定本次走 agent 路径时
按名称 ``DEFAULT_AGENT_PROFILE_NAME``（「默认助手」，对齐 ktg-ai A31）解析，
并做同一 status / 使用权校验；无该档案 → ``None``（不自动种子、不编造）。
未选档案的纯对话（不走 agent 路径）不自动挂默认档案。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from loguru import logger

from apps.kuaiai.constants import (
    DEFAULT_AGENT_PROFILE_NAME,
    ENABLED_TOOL_NAMES,
    STATUS_ENABLED,
)
from apps.kuaiai.models.agent import KuaiaiAgentProfile
from apps.kuaiai.services import grant_service
from apps.kuaiai.services.mcp_client_service import (
    build_mcp_aware_tool_guard,
    load_agent_mcp_tools,
)
from core.ai.runtime.agent_factory import build_agent
from core.ai.runtime.model_factory import build_chat_model
from core.ai.runtime.tool_bridge import registry_to_lc_tools
from infra.exceptions.exceptions import AuthorizationError, NotFoundError
from infra.models.user import User


@dataclass(frozen=True)
class AssembledAgent:
    """一次发送所需的装配产物视图。"""

    profile: KuaiaiAgentProfile
    agent: Any
    model_name: str


async def _resolve_default_profile(
    tenant_id: int,
) -> Optional[KuaiaiAgentProfile]:
    """本租户默认档案（仅 agent 路径未传 agent_id 时调用）。

    按固定名 ``DEFAULT_AGENT_PROFILE_NAME`` 查本租户未删除行；不存在 → None
    （KR-D8：种子非强制，不编造）。停用行仍返回，由 ``assemble`` 与显式
    agent_id 路径同一套 status 校验（403）。
    """
    return await KuaiaiAgentProfile.get_or_none(
        tenant_id=tenant_id,
        name=DEFAULT_AGENT_PROFILE_NAME,
        deleted_at__isnull=True,
    )


async def assemble(
    tenant_id: int,
    user: Optional[User],
    is_infra_admin: bool,
    is_tenant_admin: bool,
    agent_id: Optional[int],
    *,
    agent_path: bool,
) -> Optional[AssembledAgent]:
    """档案装配：显式 ``agent_id`` 或 agent 路径默认档案 → AssembledAgent。

    - ``agent_id`` 非空：查本租户启用档案（跨租户/不存在 404，停用 403），
      再过 ``check_use_grant``（不过 403，不静默降级、不构造 agent）；
    - ``agent_id`` 空且 ``agent_path=True``：解析默认档案并做同一使用权校验；
      无默认档案 → ``None``（纯对话，未选档案绝不自动挂档案）；
    - ``agent_id`` 空且不走 agent 路径 → ``None``。

    ``is_infra_admin`` / ``is_tenant_admin`` 保留在签名内（使用权判定当前
    不区分管理员，名单命中才算授权；KR-D9 不开管理员后门）。
    """
    if agent_id is not None:
        profile = await KuaiaiAgentProfile.get_or_none(
            tenant_id=tenant_id, id=agent_id, deleted_at__isnull=True
        )
        if profile is None:
            raise NotFoundError("Agent 档案", str(agent_id))
    else:
        if not agent_path:
            return None
        profile = await _resolve_default_profile(tenant_id)
        if profile is None:
            return None

    if profile.status != STATUS_ENABLED:
        raise AuthorizationError("该 Agent 档案已停用")

    # 授权先于装配：无使用权不构造模型/agent、不触达上游（KR-D9）
    if not await grant_service.check_use_grant(tenant_id, profile, user):
        raise AuthorizationError("无该 Agent 档案使用权")

    model = await build_chat_model(tenant_id, profile.default_model_id)
    tool_names = [
        name
        for name in (profile.enabled_tools or [])
        if name in ENABLED_TOOL_NAMES
    ]
    tools = registry_to_lc_tools(tool_names)
    # S4：档案勾选的 MCP 白名单建连装配（未解析 id 静默过滤、单 server
    # 失败跳过，均在 load_agent_mcp_tools 内）；外层异常（如行解析 DB
    # 故障）此处降级按无 MCP 工具继续，不炸整次发送。MCP 工具不在注册表，
    # 守卫须放行其名（权限/审计/超时由连接级 interceptor 承担）
    mcp_names: set = set()
    mcp_ids = getattr(profile, "mcp_server_ids", None) or []
    if mcp_ids:
        try:
            mcp_tools, mcp_names = await load_agent_mcp_tools(
                tenant_id, list(mcp_ids)
            )
            tools = tools + mcp_tools
        except Exception as exc:
            logger.warning(
                "MCP 工具装配失败，按无 MCP 工具继续 agent_id={} "
                "error_type={}",
                getattr(profile, "id", None),
                type(exc).__name__,
            )
    agent = build_agent(
        model,
        tools,
        system_prompt=(profile.system_prompt or None),
        middleware=[build_mcp_aware_tool_guard(mcp_names)],
        checkpointer=None,
    )
    model_name = str(
        getattr(model, "model_name", None) or getattr(model, "model", "") or ""
    )
    return AssembledAgent(profile=profile, agent=agent, model_name=model_name)
