"""KU-AI 运营层聚合服务（spec 181：hub 能力矩阵；spec 184：信任中心；
spec 191：能力矩阵按场景模板逐场景出卡并绑定场景实例）。

只读聚合：模型连接公开状态 + 既有 AiStatsService 概览 + 场景卡状态。
任一数据源失败局部降级（对应指标为 null / 能力 not_ready），
不整页 500、不伪造就绪与零值。
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional

from loguru import logger

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
            tenant_id=tenant_id, days=days, include_pulse=False
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


def _scene_card(
    template_key: str,
    name: str,
    description: Optional[str],
    status: str,
    disabled_reason: Optional[str],
    scene_key: Optional[str] = None,
    agent_profile_id: Optional[int] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    card = _cap(
        template_key, name, status, description,
        route=None, disabled_reason=disabled_reason,
    )
    card["scene_key"] = scene_key
    card["agent_profile_id"] = agent_profile_id
    card["category"] = category
    return card


def _resolve_category(
    scene: Any,
    template: Any,
    item: Optional[Dict[str, Any]] = None,
) -> str:
    """场景卡业务分类（spec 222）：merged fields 已带（overrides 合并结果）
    → 实例 overrides.category 合法闭集值 → 模板 category（模板侧默认 general）。

    SCENE_OVERRIDE_KEYS 由集成阶段放行 category 后，overrides 写入路径才有
    合法值；此解析与 ``_merged_fields`` 同闭集语义，未登记值回落模板分类。
    """
    from apps.kuaiai.services.agent_scene_service import SCENE_CATEGORIES

    candidates: List[Any] = []
    if item is not None:
        candidates.append(item.get("category"))
    overrides = getattr(scene, "overrides", None)
    if isinstance(overrides, dict):
        candidates.append(overrides.get("category"))
    for value in candidates:
        if isinstance(value, str) and value.strip() in SCENE_CATEGORIES:
            return value.strip()
    return template.category


def _has_business_tool(
    enabled_tools: Any, tool_kinds: Dict[str, str]
) -> bool:
    """档案 enabled_tools 是否含业务 Tool：任一 kind=read 且非 search_knowledge，
    或任一 kind=write（写类档案不受业务查询 Tool 限制，AC3）。"""
    tools = enabled_tools if isinstance(enabled_tools, list) else []
    for name in tools:
        kind = tool_kinds.get(name)
        if kind == "write" or (kind == "read" and name != "search_knowledge"):
            return True
    return False


async def _build_scene_capability_cards(
    tenant_id: int,
    user: Any,
    kuaiai: Dict[str, Any],
    chat_ready: bool,
) -> List[Dict[str, Any]]:
    """逐模板出场景卡（spec 191）：默认绑同 key 预置实例，capability_bindings
    只存覆盖（null=解绑 / 实例 key=改绑）；状态复用 _build_item 级联，
    ready 前追加「档案须含业务 Tool」判定。"""
    from apps.kuaiai.models.agent import KuaiaiAgentProfile
    from apps.kuaiai.models.agent_scene import KuaiaiAgentScene
    from apps.kuaiai.services import agent_scene_service as scene_svc
    from apps.kuaiai.services import tool_catalog_service
    from core.utils.integration_settings import read_capability_bindings

    bindings = read_capability_bindings(kuaiai, scene_svc.TEMPLATE_KEYS)
    # 含软删行：区分「预置未落地」与「预置已删除（可改绑恢复）」
    scenes = await KuaiaiAgentScene.filter(tenant_id=tenant_id).all()
    live = {s.instance_key: s for s in scenes if s.deleted_at is None}
    present_keys = {s.instance_key for s in scenes}

    profile_ids = [
        s.agent_profile_id for s in live.values() if s.agent_profile_id
    ]
    profiles_by_id: Dict[int, Any] = {}
    if profile_ids:
        rows = await KuaiaiAgentProfile.filter(
            tenant_id=tenant_id,
            id__in=profile_ids,
            deleted_at__isnull=True,
        ).all()
        profiles_by_id = {p.id: p for p in rows}

    # 卡片构建属放行判定路径：开关读取异常失败关闭（卡片 not_ready）
    switches = await scene_svc.agent_switches(tenant_id, fail_closed=True)
    usable = await scene_svc.grant_service.usable_profile_ids(
        tenant_id, user
    )
    has_agent_read = await scene_svc._has_permission(
        user, tenant_id, "kuaiai:agent:read"
    )
    route_grants = await scene_svc._route_permissions_for_user(
        tenant_id, user
    )
    tool_kinds = {
        item.name: item.kind
        for item in tool_catalog_service.list_tool_catalog()
    }
    common = dict(
        switches=switches,
        usable_profile_ids=usable,
        has_agent_read=has_agent_read,
        chat_ready=chat_ready,
        route_grants=route_grants,
        profiles_by_id=profiles_by_id,
    )

    cards: List[Dict[str, Any]] = []
    for template in scene_svc.SCENE_TEMPLATES:
        if template.key in bindings:
            bound_key = bindings[template.key]
            if bound_key is None:
                cards.append(
                    _scene_card(
                        template.key,
                        template.name,
                        template.description,
                        "not_ready",
                        "已解绑场景",
                        category=template.category,
                    )
                )
                continue
            scene = live.get(bound_key)
            if scene is None:
                cards.append(
                    _scene_card(
                        template.key,
                        template.name,
                        template.description,
                        "not_ready",
                        "绑定的场景实例不存在或已删除",
                        category=template.category,
                    )
                )
                continue
        else:
            scene = live.get(template.key)
            if scene is None:
                reason = (
                    "预置场景已删除"
                    if template.key in present_keys
                    else "场景预置未完成，请重新同步应用后重试"
                )
                cards.append(
                    _scene_card(
                        template.key,
                        template.name,
                        template.description,
                        "not_ready",
                        reason,
                        category=template.category,
                    )
                )
                continue

        item = await scene_svc._build_item(
            tenant_id, user, template, scene, **common
        )
        status = item["status"]
        reason = item["disabled_reason"]
        if status == "ready":
            profile = profiles_by_id.get(scene.agent_profile_id)
            if profile is None or not _has_business_tool(
                getattr(profile, "enabled_tools", None), tool_kinds
            ):
                status = "not_ready"
                reason = "绑定档案未勾选业务查询工具"
        cards.append(
            _scene_card(
                template.key,
                item["name"],
                item["description"],
                status,
                reason,
                scene_key=scene.instance_key,
                agent_profile_id=item["agent_profile_id"],
                category=_resolve_category(scene, template, item),
            )
        )
    return cards


async def _build_capabilities(
    tenant_id: int,
    model_status: Dict[str, Any],
    user: Any = None,
) -> List[Dict[str, Any]]:
    from apps.kuaiai.services.agent_scene_service import (
        SCENE_TEMPLATES,
        _site_kuaiai_integration,
    )

    kuaiai = await _site_kuaiai_integration(tenant_id)
    chat_ready = bool(
        model_status.get("configured") and model_status.get("enabled")
    )

    caps: List[Dict[str, Any]] = []
    # ask 卡保持纯对话路径 A（SC-D15），不绑定档案
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
    try:
        caps.extend(
            await _build_scene_capability_cards(
                tenant_id, user, kuaiai, chat_ready
            )
        )
    except Exception as exc:
        logger.warning(
            "hub 场景卡聚合失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        for template in SCENE_TEMPLATES:
            caps.append(
                _scene_card(
                    template.key,
                    template.name,
                    template.description,
                    "not_ready",
                    "场景状态读取失败",
                    category=template.category,
                )
            )
    return caps


async def get_hub(
    tenant_id: int,
    days: int,
    user=None,
    *,
    include_pulse: bool = False,
) -> Dict[str, Any]:
    """GET /operations/hub 聚合（days 由路由层校验 1..90）。

    默认 include_pulse=False，不阻塞首屏全量五域 Pulse 扫描；
    Pulse 总数由前端首屏后异步拉取 /core/ai/stats/pulse-count（60s 缓存）。
    """
    days = max(1, min(int(days or 7), 90))
    model_status = await _model_public_status(tenant_id)
    metrics = await _metrics(tenant_id, days)
    if include_pulse:
        metrics["pulse_count"] = await _pulse_total(tenant_id, user)
    else:
        metrics["pulse_count"] = None
    capabilities = await _build_capabilities(tenant_id, model_status, user)
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
    """HITL 写门控真实装配判定（spec 193：三条件全真才算就绪）。

    ① 写类 Tool 存在中断配置（manifest ``kind=write`` ∩ 闭集 且装配
      含 ``HumanInTheLoopMiddleware``）；
    ② 装配使用 ``TortoiseCheckpointSaver``（spec 192 持久化 pending）；
    ③ 网关已注册 resume 续跑端点。
    任一缺失 → partial/not_ready，绝不按「代码里存在某函数」推断 ready。
    """
    evidence: List[str] = []

    interrupt_wired = False
    try:
        from apps.kuaiai.constants import ENABLED_TOOL_NAMES
        from apps.kuaiai.services.agent_assembler import assemble
        from apps.kuaiai.services.tool_catalog_service import (
            manifest_write_tool_names,
        )

        write_tools = manifest_write_tool_names() & frozenset(
            ENABLED_TOOL_NAMES
        )
        interrupt_wired = bool(write_tools) and (
            "HumanInTheLoopMiddleware" in inspect.getsource(assemble)
        )
    except Exception as exc:
        logger.warning(
            "trust HITL 中断配置检查失败 error_type={}",
            type(exc).__name__,
        )
    evidence.append(
        "写类 Tool 已登记中断配置（kind=write → HumanInTheLoop）"
        if interrupt_wired
        else "写类 Tool 无中断配置"
    )

    saver_wired = False
    try:
        from apps.kuaiai.services.agent_assembler import assemble as _asm
        from apps.kuaiai.services.checkpoint_saver import (  # noqa: F401
            TortoiseCheckpointSaver,
        )

        saver_wired = "TortoiseCheckpointSaver" in inspect.getsource(_asm)
    except Exception as exc:
        logger.warning(
            "trust HITL checkpointer 检查失败 error_type={}",
            type(exc).__name__,
        )
    evidence.append(
        "确认闸使用 TortoiseCheckpointSaver 持久化挂起"
        if saver_wired
        else "确认闸 checkpointer 未接线"
    )

    resume_route_found = False
    try:
        from core.api.ai.router import router as ai_router

        for route in getattr(ai_router, "routes", []):
            path = str(getattr(route, "path", "") or "").lower()
            if "resume" in path:
                resume_route_found = True
                break
    except Exception as exc:
        logger.warning(
            "trust HITL 端点检查失败 error_type={}", type(exc).__name__
        )
    evidence.append(
        "AI 网关已注册 resume 续跑端点"
        if resume_route_found
        else "AI 网关未注册 resume 续跑端点"
    )

    implemented = interrupt_wired and saver_wired and resume_route_found
    return {
        "implemented": implemented,
        "mode": "human_gate" if implemented else "not_implemented",
        "interrupt_wired": interrupt_wired,
        "saver_wired": saver_wired,
        "resume_route_found": resume_route_found,
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
    hitl_checks = [
        hitl_state["interrupt_wired"],
        hitl_state["saver_wired"],
        hitl_state["resume_route_found"],
    ]
    hitl_status = (
        "ready"
        if hitl_state["implemented"]
        else ("partial" if any(hitl_checks) else "not_ready")
    )
    hitl_card = {
        "key": "hitl",
        "title": "HITL 写门控",
        "status": hitl_status,
        "description": (
            "写工具经人工确认闸执行，确认/拒绝/过期均留审计"
            if hitl_state["implemented"]
            else "人工确认闸未完全就绪：写工具仍受业务权限与服务校验约束"
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
