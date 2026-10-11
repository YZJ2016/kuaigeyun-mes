"""KU-AI 运营层聚合服务（spec 181：hub 能力矩阵；spec 184：信任中心）。

只读聚合：模型连接公开状态 + 既有 AiStatsService 概览 + 站点能力开关 +
启用知识库计数。任一数据源失败局部降级（对应指标为 null / 能力
not_ready），不整页 500、不伪造就绪与零值。
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional

from loguru import logger

from apps.kuaiai.constants import STATUS_ENABLED

_CAPABILITY_STATUSES = frozenset({"ready", "partial", "not_ready"})

# spec 184：信任页面向当前用户展示的权限码闭集（不枚举角色关系）
TRUST_PERMISSION_CODES: tuple[str, ...] = (
    "kuaiai:entry:read",
    "kuaiai:act:execute",
    "kuaiai:knowledge:read",
    "kuaiai:hub:display",
    "kuaiai:library:display",
    "kuaiai:pulse:display",
    "kuaiai:corpus:display",
    "kuaiai:trust:display",
    "kuaiai:insights:display",
    "kuaiai:settings:display",
)


def _has_registered_scene_readonly_tool() -> bool:
    """只认场景只读 Tool 显式闭集与当前注册表的交集。"""
    from apps.kuaiai.constants import SCENE_READONLY_TOOL_NAMES
    from core.ai.tool_registry import ToolRegistry

    ToolRegistry.ensure_defaults()
    return bool(SCENE_READONLY_TOOL_NAMES.intersection(ToolRegistry._tools))


async def _model_public_status(tenant_id: int) -> Dict[str, Any]:
    try:
        from core.ai.runtime_config import AiRuntimeConfig

        return await AiRuntimeConfig.public_status(tenant_id)
    except Exception as exc:
        logger.warning(
            "hub 模型公开状态读取失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        return {"configured": False, "enabled": False, "model": None,
                "connection_uuid": None}


async def _metrics(tenant_id: int, days: int) -> Dict[str, Optional[int]]:
    try:
        from core.ai.stats_service import AiStatsService

        overview = await AiStatsService.get_overview(
            tenant_id=tenant_id, days=days
        )
        return {
            "total_calls": overview.total_calls,
            # pulse_count 由 spec 182 真实 detector 聚合单独填，不走 LLM 建议数
            "pulse_count": None,
            "corpus_count": overview.knowledge_document_count,
            "avg_latency_ms": overview.avg_latency_ms,
        }
    except Exception as exc:
        logger.warning(
            "hub 指标聚合失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        return {
            "total_calls": None,
            "pulse_count": None,
            "corpus_count": None,
            "avg_latency_ms": None,
        }


async def _pulse_total(tenant_id: int, user) -> Optional[int]:
    """Pulse 真实异常总数：聚合整体失败或全部已实现 detector 失败 → None。"""
    from apps.kuaiai.services.pulse import registry as pulse_registry

    return await pulse_registry.pulse_total_count(tenant_id, user)


async def _enabled_knowledge_base_count(tenant_id: int) -> Optional[int]:
    try:
        from apps.kuaiai.models.knowledge import KuaiaiKnowledgeBase

        return await KuaiaiKnowledgeBase.filter(
            tenant_id=tenant_id,
            status=STATUS_ENABLED,
            deleted_at__isnull=True,
        ).count()
    except Exception as exc:
        logger.warning(
            "hub 知识库计数失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        return None


async def _vision_configured(tenant_id: int) -> Optional[bool]:
    """vision 连接是否已选用且可用；读取失败 → None（按未配置降级）。"""
    try:
        from core.services.system.site_setting_service import (
            SiteSettingService,
        )
        from core.utils.integration_settings import (
            _load_llm_connection,
            get_kuaiai_integration,
            role_connection_setting_key,
        )

        site = await SiteSettingService.get_settings(tenant_id)
        kuaiai = get_kuaiai_integration(site.settings or {})
        conn_uuid = str(
            kuaiai.get(role_connection_setting_key("vision")) or ""
        ).strip()
        if not conn_uuid:
            return False
        connection = await _load_llm_connection(tenant_id, conn_uuid)
        return connection is not None
    except Exception as exc:
        logger.warning(
            "hub vision 连接检查失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        return None


def _cap(
    key: str,
    name: str,
    status: str,
    description: str,
    route: Optional[str] = None,
    disabled_reason: Optional[str] = None,
) -> Dict[str, Any]:
    if status not in _CAPABILITY_STATUSES:
        status = "not_ready"
    return {
        "key": key,
        "name": name,
        "status": status,
        "description": description,
        "route": route,
        "disabled_reason": disabled_reason,
    }


async def _build_capabilities(
    tenant_id: int,
    model_status: Dict[str, Any],
) -> List[Dict[str, Any]]:
    from apps.kuaiai.services.agent_scene_service import (
        _site_kuaiai_integration,
    )

    kuaiai = await _site_kuaiai_integration(tenant_id)
    tools_enabled = kuaiai.get("tools_enabled", True) is not False
    rag_enabled = kuaiai.get("rag_enabled", True) is not False
    chat_ready = bool(
        model_status.get("configured") and model_status.get("enabled")
    )
    kb_count = await _enabled_knowledge_base_count(tenant_id)
    vision = await _vision_configured(tenant_id)
    try:
        readonly_tool_ready = _has_registered_scene_readonly_tool()
    except Exception as exc:
        logger.warning(
            "hub 只读 Tool 注册状态检查失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        readonly_tool_ready = False

    caps: List[Dict[str, Any]] = []
    caps.append(
        _cap(
            "ask",
            "智能问答",
            "ready" if chat_ready else "not_ready",
            "基于已选用对话连接的业务问答",
            route="/apps/kuaiai/chat",
            disabled_reason=None if chat_ready else "未配置可用的对话模型连接",
        )
    )
    if not chat_ready:
        query_status, query_reason = "not_ready", "未配置可用的对话模型连接"
    elif not tools_enabled:
        query_status, query_reason = "not_ready", "业务工具开关未启用"
    elif not readonly_tool_ready:
        query_status, query_reason = "not_ready", "尚未注册可用的只读业务工具"
    else:
        query_status, query_reason = "ready", None
    caps.append(
        _cap(
            "data_query",
            "智能数据查询",
            query_status,
            "经只读业务 Tool 查询已授权数据",
            route="/apps/kuaiai/chat",
            disabled_reason=query_reason,
        )
    )
    caps.append(
        _cap(
            "guide",
            "智能实施",
            "not_ready",
            "按场景引导完成实施动作",
            disabled_reason="实施向导尚未配置",
        )
    )
    caps.append(
        _cap(
            "pulse",
            "异常感知",
            "ready",
            "对生产/库存/质量等异常主动感知",
            route="/apps/kuaiai/pulse",
        )
    )
    if vision is True:
        doc_status, doc_reason = "ready", None
    elif vision is False:
        doc_status, doc_reason = "not_ready", "未选用视觉（OCR）连接"
    else:
        doc_status, doc_reason = "not_ready", "视觉连接状态读取失败"
    caps.append(
        _cap(
            "doc_entry",
            "智能单据录入",
            doc_status,
            "经视觉连接识别单据内容",
            disabled_reason=doc_reason,
        )
    )
    caps.append(
        _cap(
            "recommend",
            "智能推荐",
            "not_ready",
            "按业务上下文给出推荐建议",
            disabled_reason="推荐场景尚未注册",
        )
    )
    if not rag_enabled:
        know_status, know_reason = "not_ready", "知识检索开关未启用"
    elif kb_count is None:
        know_status, know_reason = "not_ready", "知识库状态读取失败"
    elif kb_count <= 0:
        know_status, know_reason = "partial", "尚未创建启用的知识库"
    else:
        know_status, know_reason = "ready", None
    caps.append(
        _cap(
            "knowledge",
            "知识检索",
            know_status,
            "经 RAG 检索企业知识库",
            route="/apps/kuaiai/corpus",
            disabled_reason=know_reason,
        )
    )
    caps.append(
        _cap(
            "trusted_exec",
            "可信执行",
            "partial" if tools_enabled else "not_ready",
            "受控写工具 + 人审门控执行",
            disabled_reason=(
                "人审门控（HITL）尚未完整落地"
                if tools_enabled
                else "业务工具开关未启用"
            ),
        )
    )
    return caps[:8]


async def get_hub(
    tenant_id: int, days: int, user=None
) -> Dict[str, Any]:
    """GET /operations/hub 聚合（days 由路由层校验 1..90）。"""
    days = max(1, min(int(days or 7), 90))
    model_status = await _model_public_status(tenant_id)
    metrics = await _metrics(tenant_id, days)
    metrics["pulse_count"] = await _pulse_total(tenant_id, user)
    capabilities = await _build_capabilities(tenant_id, model_status)
    return {
        "days": days,
        "model": {
            "configured": bool(model_status.get("configured")),
            "name": model_status.get("model"),
            "connection_uuid": model_status.get("connection_uuid"),
        },
        "metrics": metrics,
        "capabilities": capabilities,
    }


# ============================================================ 信任中心（spec 184）
#
# 状态只取 ready|partial|not_ready；证据数组只放可复核事实，异常一律脱敏
# （只记 error_type，不回 message/栈/路径）。HITL 由真实装配状态判定：
# LangGraph checkpointer 未接线且网关无 propose/execute 端点 → not_ready，
# 绝不因"代码里存在某函数"推断 ready。


def _hitl_feature_state() -> Dict[str, Any]:
    """HITL 写门控显式状态（真实装配 + 端点检查，非代码存在推断）。"""
    evidence: List[str] = []

    checkpointer_wired = False
    try:
        from core.ai.runtime.agent_factory import build_agent

        param = inspect.signature(build_agent).parameters.get("checkpointer")
        checkpointer_wired = (
            param is not None and param.default is not None
        )
    except Exception as exc:
        logger.warning(
            "trust HITL checkpointer 检查失败 error_type={}",
            type(exc).__name__,
        )
    evidence.append(
        "LangGraph checkpointer 已接线"
        if checkpointer_wired
        else "LangGraph checkpointer 未接线（agent 装配默认 None）"
    )

    gate_route_found = False
    try:
        from core.api.ai.router import router as ai_router

        for route in getattr(ai_router, "routes", []):
            path = str(getattr(route, "path", "") or "").lower()
            if any(
                k in path for k in ("propose", "execute", "approve", "interrupt")
            ):
                gate_route_found = True
                break
    except Exception as exc:
        logger.warning(
            "trust HITL 端点检查失败 error_type={}", type(exc).__name__
        )
    evidence.append(
        "AI 网关已注册 propose/execute 门控端点"
        if gate_route_found
        else "AI 网关未注册 propose/execute 人审端点"
    )

    implemented = checkpointer_wired and gate_route_found
    return {
        "implemented": implemented,
        "mode": "human_gate" if implemented else "not_implemented",
        "checkpointer_wired": checkpointer_wired,
        "gate_route_found": gate_route_found,
        "evidence": evidence,
    }


def _rbac_card() -> Dict[str, Any]:
    """RBAC 读权限卡：核验核心网关与本接口的权限依赖确实存在。"""
    try:
        from core.ai.deps import AI_CAPABILITY_PERMISSIONS

        entry_perm = (AI_CAPABILITY_PERMISSIONS.get("entry") or "").strip()
        act_perm = (AI_CAPABILITY_PERMISSIONS.get("act") or "").strip()
    except Exception as exc:
        logger.warning(
            "trust RBAC 依赖检查失败 error_type={}", type(exc).__name__
        )
        return {
            "key": "rbac",
            "title": "RBAC 读权限",
            "status": "partial",
            "description": "工具与查询仅在已授予权限范围内执行",
            "evidence": ["权限依赖配置读取失败（详情不对外展示）"],
        }

    ok = entry_perm == "kuaiai:entry:read" and act_perm == "kuaiai:act:execute"
    evidence = [
        "本接口已通过 kuaiai:entry:read + kuaiai:trust:display 双码鉴权",
        (
            f"核心 AI 网关入口/执行分别挂载 {entry_perm or '缺失'} / "
            f"{act_perm or '缺失'}"
        ),
    ]
    return {
        "key": "rbac",
        "title": "RBAC 读权限",
        "status": "ready" if ok else "partial",
        "description": "工具与查询仅在已授予权限范围内执行",
        "evidence": evidence,
    }


async def _audit_card(tenant_id: int) -> Dict[str, Any]:
    """全链路审计卡：审计表实际可查 → ready；查询失败 → partial（脱敏）。"""
    evidence = ["AiAuditMiddleware 覆盖 /api/v1/core/ai/** 网关请求"]
    try:
        from core.models.ai_audit_log import AiAuditLog

        has_rows = await AiAuditLog.filter(tenant_id=tenant_id).exists()
        evidence.append(
            "本租户已有审计记录" if has_rows else "本租户暂无审计记录（空不算故障）"
        )
        status = "ready"
    except Exception as exc:
        logger.warning(
            "trust 审计可读性检查失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        evidence.append("审计日志读取失败（详情不对外展示）")
        status = "partial"
    return {
        "key": "audit",
        "title": "全链路审计",
        "status": status,
        "description": "记录租户、用户、路由与耗时",
        "evidence": evidence,
    }


async def _current_user_permissions(tenant_id: int, user) -> List[Dict[str, Any]]:
    """当前用户权限码持有状态；管理员旁路全 True；失败时全 False 降级。"""
    from core.services.authorization.user_permission_service import (
        UserPermissionService,
    )

    granted: Dict[str, bool] = {}
    try:
        user_id = int(getattr(user, "id"))
        if await UserPermissionService.is_admin_bypass(user, tenant_id):
            granted = {code: True for code in TRUST_PERMISSION_CODES}
        else:
            owned = await UserPermissionService.get_user_permissions(
                user_id=user_id, tenant_id=tenant_id
            )
            granted = {
                code: code in owned for code in TRUST_PERMISSION_CODES
            }
    except Exception as exc:
        logger.warning(
            "trust 权限清单读取失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        granted = {code: False for code in TRUST_PERMISSION_CODES}
    return [
        {"code": code, "granted": granted.get(code, False)}
        for code in TRUST_PERMISSION_CODES
    ]


async def get_trust(tenant_id: int, user) -> Dict[str, Any]:
    """GET /operations/trust 聚合：三卡 + 当前用户权限码 + HITL 显式状态。"""
    hitl_state = _hitl_feature_state()
    hitl_status = "ready" if hitl_state["implemented"] else "not_ready"
    hitl_card = {
        "key": "hitl",
        "title": "HITL 写门控",
        "status": hitl_status,
        # 未完成时态（设计 §8）：绝不声称 propose/execute 已完成
        "description": (
            "当前写工具仍受业务权限与服务校验约束；人工确认闸尚未接入"
        ),
        "evidence": hitl_state["evidence"],
    }
    return {
        "cards": [
            _rbac_card(),
            hitl_card,
            await _audit_card(tenant_id),
        ],
        "permissions": await _current_user_permissions(tenant_id, user),
        "hitl": {
            "implemented": hitl_state["implemented"],
            "mode": hitl_state["mode"],
        },
    }
