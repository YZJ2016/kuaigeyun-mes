"""KU-AI 租户场景实例服务（spec 181）

职责：
- 六个后端出厂场景模板（稳定 key / 卡片元数据 / 场景提示词 / 最小只读 Tool）；
- ``seed_kuaiai_agent_scenes_on_lifecycle``：install/enable/扫描同步幂等预置
  六份停用、空授权档案 + 六条绑定实例（同事务，失败全回滚，不写 grant）；
- 智能体库聚合视图：模板元数据 + 实例覆盖字段合并、总/单项开关、档案/使用权/
  chat 就绪计算状态与 disabled_reason、档案 ID 脱敏、路由白名单可用性；
- 实例定制/改绑/按需克隆（本租户校验 + 白名单 + 同事务原子提交）；
- ``guard_scene_agent_key``：chat 请求携带 ``extra.agent_key`` 时的场景守卫。

安全约定：模板 key / 插画 key / 业务路由 / 覆盖字段一律服务端闭集白名单；
所有查询带 tenant_id；跨租户/软删档案按不存在处理；生命周期种子行审计字段
写 ``created_by=0, created_by_name="系统"``，不冒名任一用户。
"""

from __future__ import annotations

import uuid as uuid_module
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from loguru import logger
from tortoise.transactions import in_transaction

from apps.kuaiai.constants import (
    GRANT_MODE_ROLE,
    STATUS_DISABLED,
    STATUS_ENABLED,
)
from apps.kuaiai.models.agent import KuaiaiAgentProfile
from apps.kuaiai.models.agent_scene import (
    SCENE_ORIGIN_COPY,
    SCENE_ORIGIN_SYSTEM_SEED,
    KuaiaiAgentScene,
)
from apps.kuaiai.schemas.agent import AgentProfileCreate
from apps.kuaiai.services import agent_service, grant_service
from infra.exceptions.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    NotFoundError,
    ValidationError,
)
from infra.models.user import User


@dataclass(frozen=True)
class SceneTemplate:
    """后端出厂场景模板（不可变定义；首期六键稳定，实例可扩）。"""

    key: str
    name: str
    description: str
    image_key: str
    capability_tags: tuple
    sample_prompt: str
    scene_route: Optional[str]
    system_prompt: str
    readonly_tools: tuple


# ============================================================ 六个出厂模板
# 只读 Tool / 业务路由 / 权限锚点逐一对照设计 §5.3 与当前业务 manifest，
# 路由不可用即 scene_available=false，不凭文案猜测。

SCENE_TEMPLATES: tuple = (
    SceneTemplate(
        key="inventory-insight",
        name="库存洞察助手",
        description="查询缺料与即时库存余额，支持跨仓检索",
        image_key="inventory-insight",
        capability_tags=("KU-Ask",),
        sample_prompt="查询缺料相关的物料即时库存",
        scene_route="/apps/kuaizhizao/warehouse-management/inventory",
        system_prompt=(
            "你是库存洞察助手，只回答与本租户即时库存相关的问题。"
            "库存事实一律来自 query_inventory_balance 工具返回的真实数据；"
            "查不到数据就如实说明，不要编造库存数量、仓位或批次信息。"
        ),
        readonly_tools=("query_inventory_balance",),
    ),
    SceneTemplate(
        key="planner-advisor",
        name="计划员顾问",
        description="分析近期工单延期风险并给出处理顺序",
        image_key="planner-advisor",
        capability_tags=("KU-Ask", "KU-Pulse"),
        sample_prompt="分析近期工单延期风险并给出处理顺序",
        scene_route="/apps/kuaizhizao/production-execution/work-orders",
        system_prompt=(
            "你是计划员顾问，解读工单交期风险与排产冲突，给出可执行的处理顺序建议。"
            "工单与延期事实一律来自 query_workorder、list_workorder_tasks、"
            "query_delivery_risk 工具返回的真实数据；查不到就如实说明，不要编造工单或日期。"
        ),
        readonly_tools=(
            "query_workorder",
            "list_workorder_tasks",
            "query_delivery_risk",
        ),
    ),
    SceneTemplate(
        key="purchase-followup",
        name="采购跟单助手",
        description="跟进采购交期与供应商回复，汇总近期采购交期风险",
        image_key="purchase-followup",
        capability_tags=("KU-Draft", "KU-Act"),
        sample_prompt="汇总近期采购交期风险",
        scene_route="/apps/kuaizhizao/purchase-management/purchase-orders",
        system_prompt=(
            "你是采购跟单助手，汇总采购订单的交期与到货风险，辅助跟单说明。"
            "采购事实一律来自 query_purchase_followup 工具返回的真实数据；"
            "查不到就如实说明，不要编造订单、供应商或交期。"
        ),
        readonly_tools=("query_purchase_followup",),
    ),
    SceneTemplate(
        key="schedule-explainer",
        name="排程解读助手",
        description="解释当前排程冲突与调整依据",
        image_key="schedule-explainer",
        capability_tags=("KU-Suggest",),
        sample_prompt="解释当前排程冲突与调整依据",
        scene_route="/apps/kuaizhizao/plan-management/rolling-scheduling",
        system_prompt=(
            "你是排程解读助手，解释已发布滚动排程的冲突与调整依据。"
            "排程事实一律来自 query_published_schedule 工具返回的真实数据；"
            "查不到已发布计划就如实说明，不要编造排程结果或产能数据。"
        ),
        readonly_tools=("query_published_schedule",),
    ),
    SceneTemplate(
        key="quality-analysis",
        name="质量异常分析",
        description="汇总近期质量异常并分析可能原因",
        image_key="quality-analysis",
        capability_tags=("KU-Pulse", "KU-Know"),
        sample_prompt="汇总近期质量异常并分析可能原因",
        scene_route="/apps/kuaizhizao/production-execution/quality-exceptions",
        system_prompt=(
            "你是质量异常分析助手，汇总近期不合格检验记录并分析可能原因。"
            "质量异常事实一律来自 query_quality_anomalies 工具返回的真实数据；"
            "查不到异常就如实说明，不要编造不合格原因或检验数据。"
        ),
        readonly_tools=("query_quality_anomalies",),
    ),
    SceneTemplate(
        key="supplier-collaboration",
        name="供应商协同 Agent",
        description="汇总待协同供应商事项，辅助跟进说明",
        image_key="supplier-collaboration",
        capability_tags=("KU-Act",),
        sample_prompt="汇总待协同供应商事项",
        scene_route="/apps/kuaizhizao/purchase-management/reports/supplier-delivery-summary",
        system_prompt=(
            "你是供应商协同助手，汇总指定供应商的采购订单与待协同事项，辅助跟进说明。"
            "供应商与订单事实一律来自 query_supplier_orders 工具返回的真实数据；"
            "查不到就如实说明，不要编造供应商或订单信息。"
        ),
        readonly_tools=("query_supplier_orders",),
    ),
)

_TEMPLATE_MAP: Dict[str, SceneTemplate] = {t.key: t for t in SCENE_TEMPLATES}
_TEMPLATE_ORDER: Dict[str, int] = {t.key: i for i, t in enumerate(SCENE_TEMPLATES)}
TEMPLATE_KEYS: frozenset = frozenset(_TEMPLATE_MAP.keys())

# ============================================================ 服务端白名单
# 「查看场景」目标路由 → 页面读权限码。值取自当前业务 manifest 已注册菜单，
# 找不到/无权限即 scene_available=false；实例自定义路由也只能从这里选。

SCENE_ROUTE_PERMISSIONS: Dict[str, str] = {
    "/apps/kuaizhizao/warehouse-management/inventory": (
        "kuaizhizao:warehouse-management-inventory:read"
    ),
    "/apps/kuaizhizao/production-execution/work-orders": (
        "kuaizhizao:work-order:read"
    ),
    "/apps/kuaizhizao/purchase-management/purchase-orders": (
        "kuaizhizao:purchase-order:read"
    ),
    "/apps/kuaizhizao/plan-management/rolling-scheduling": (
        "kuaizhizao:plan-management-rolling-scheduling:read"
    ),
    "/apps/kuaizhizao/production-execution/quality-exceptions": (
        "kuaizhizao:production-execution-quality-exceptions:read"
    ),
    "/apps/kuaizhizao/purchase-management/reports/supplier-delivery-summary": (
        "kuaizhizao:purchase-management-reports-supplier-delivery-summary:read"
    ),
}

SCENE_IMAGE_KEYS: frozenset = frozenset(t.image_key for t in SCENE_TEMPLATES)

SCENE_CAPABILITY_TAGS: frozenset = frozenset(
    tag for t in SCENE_TEMPLATES for tag in t.capability_tags
)

# overrides JSON 允许写入的字段闭集（agent_profile_id/enabled 走实例列，不进 overrides）
SCENE_OVERRIDE_KEYS: frozenset = frozenset(
    {
        "name",
        "description",
        "image_key",
        "sample_prompt",
        "capability_tags",
        "scene_route",
    }
)

_SEED_AUDIT = {
    "created_by": 0,
    "created_by_name": "系统",
    "updated_by": 0,
    "updated_by_name": "系统",
}

# ============================================================ 开关与就绪


def _audit_update(user: Optional[User]) -> Dict[str, Any]:
    if user is None or getattr(user, "id", None) is None:
        return {}
    name = getattr(user, "full_name", None) or getattr(user, "username", None)
    return {"updated_by": user.id, "updated_by_name": name}


async def _site_kuaiai_integration(tenant_id: int) -> Dict[str, Any]:
    """读取站点设置 integrations.kuaiai；失败一律返回空 dict（开关回落默认）。"""
    try:
        from core.services.system.site_setting_service import SiteSettingService
        from core.utils.integration_settings import get_kuaiai_integration

        site = await SiteSettingService.get_settings(tenant_id)
        return get_kuaiai_integration(site.settings or {})
    except Exception as exc:
        logger.warning(
            "读取站点 KU-AI 集成设置失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        return {}


async def agent_switches(tenant_id: int) -> Dict[str, bool]:
    """模板总开关：``integrations.kuaiai.agent_switches``，缺键默认 True。"""
    from core.utils.integration_settings import read_agent_switches

    kuaiai = await _site_kuaiai_integration(tenant_id)
    return read_agent_switches(kuaiai, _TEMPLATE_MAP.keys())


async def _capabilities(tenant_id: int) -> Dict[str, Any]:
    """tools_enabled / rag_enabled 等站点能力开关（供 hub 能力矩阵）。"""
    kuaiai = await _site_kuaiai_integration(tenant_id)
    return kuaiai


async def is_chat_ready(tenant_id: int) -> bool:
    """chat 就绪只认当前应用连接运行时；目录行不是执行真源。"""
    try:
        from core.ai.runtime_config import AiRuntimeConfig

        status = await AiRuntimeConfig.public_status(tenant_id)
        return bool(status.get("configured") and status.get("enabled"))
    except Exception as exc:
        logger.warning(
            "chat 连接器就绪检查失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        return False


async def _has_permission(user: Optional[User], tenant_id: int, code: str) -> bool:
    """当前用户权限判定：管理员身份由 has_permission 内部处理，失败关闭。"""
    uid = getattr(user, "id", None)
    if not uid or not tenant_id:
        return False
    try:
        from core.services.authorization.user_permission_service import (
            UserPermissionService,
        )

        return bool(
            await UserPermissionService.has_permission(uid, tenant_id, code)
        )
    except Exception as exc:
        logger.warning(
            "权限判定失败 tenant_id={} code={} error_type={}",
            tenant_id,
            code,
            type(exc).__name__,
        )
        return False


async def _require_permission(user: Optional[User], tenant_id: int, code: str) -> None:
    if not await _has_permission(user, tenant_id, code):
        raise AuthorizationError("权限不足")


# ============================================================ 生命周期种子


async def _unique_seed_profile_name(tenant_id: int, base: str) -> str:
    """种子档案名：模板中文名；重名追加（预置）及递增序号，绝不覆盖。"""
    name = base.strip()[:100]
    for suffix in ("", "（预置）") + tuple(f"（预置{i}）" for i in range(2, 50)):
        candidate = name if not suffix else f"{name[:100 - len(suffix)]}{suffix}"
        dup = await KuaiaiAgentProfile.get_or_none(
            tenant_id=tenant_id, name=candidate, deleted_at__isnull=True
        )
        if dup is None:
            return candidate
    raise BusinessLogicError(f"无法为预置档案 {base} 分配唯一名称")


async def _create_seed_profile(
    tenant_id: int, template: SceneTemplate
) -> KuaiaiAgentProfile:
    """按模板建档：停用 / grant_mode=ROLE / 空名单 / 空模型 / 只读 Tool。

    复用 agent_service.create_profile 的闭集/重名校验链；生命周期无用户
    上下文，审计字段按系统创建约定补写 created_by=0「系统」。
    """
    name = await _unique_seed_profile_name(tenant_id, template.name)
    payload = AgentProfileCreate(
        name=name,
        description=template.description,
        system_prompt=template.system_prompt,
        default_model_id=None,
        knowledge_ids=[],
        enabled_tools=list(template.readonly_tools),
        mcp_server_ids=[],
        status=STATUS_DISABLED,
        grant_mode=GRANT_MODE_ROLE,
    )
    profile = await agent_service.create_profile(tenant_id, None, payload)
    profile.created_by = 0
    profile.created_by_name = "系统"
    profile.updated_by = 0
    profile.updated_by_name = "系统"
    await profile.save(
        update_fields=[
            "created_by",
            "created_by_name",
            "updated_by",
            "updated_by_name",
        ]
    )
    return profile


async def seed_kuaiai_agent_scenes_on_lifecycle(tenant_id: int) -> Dict[str, Any]:
    """install/enable/扫描同步幂等预置：缺几补几，同事务提交。

    - 只为 instance_key=template_key 完全缺失的模板建档+建行；已存在实例
      （含手动解绑/改绑/停用/定制）与已软删痕迹一律尊重，不重建不覆盖；
    - 六组创建在同一 Tortoise 事务内提交，任一失败全部回滚，可安全重试；
    - 不写任何 grant 行、不启用档案；返回 created/complete 供调用方与
      provisioning 判定。
    """
    result = {"created": 0, "profiles": 0, "complete": False}
    if not tenant_id:
        return result

    existing_keys = set(
        await KuaiaiAgentScene.filter(
            tenant_id=tenant_id, instance_key__in=list(TEMPLATE_KEYS)
        ).values_list("instance_key", flat=True)
    )
    missing = [t for t in SCENE_TEMPLATES if t.key not in existing_keys]
    if not missing:
        result["complete"] = True
        return result

    async with in_transaction():
        for template in missing:
            # 事务内复核一次（并发 seed 下另一事务可能已建行）
            row = await KuaiaiAgentScene.get_or_none(
                tenant_id=tenant_id, instance_key=template.key
            )
            if row is not None:
                continue
            profile = await _create_seed_profile(tenant_id, template)
            await KuaiaiAgentScene.create(
                tenant_id=tenant_id,
                instance_key=template.key,
                template_key=template.key,
                origin=SCENE_ORIGIN_SYSTEM_SEED,
                agent_profile_id=profile.id,
                overrides={},
                enabled=True,
                **_SEED_AUDIT,
            )
            result["profiles"] += 1

    result["created"] = result["profiles"]
    remaining = await KuaiaiAgentScene.filter(
        tenant_id=tenant_id,
        instance_key__in=list(TEMPLATE_KEYS),
        deleted_at__isnull=True,
    ).count()
    result["complete"] = remaining == len(SCENE_TEMPLATES)
    logger.info(
        "KU-AI 场景预置完成 tenant_id={} created={} complete={}",
        tenant_id,
        result["created"],
        result["complete"],
    )
    return result


# ============================================================ 聚合视图


def _merged_fields(scene: Optional[KuaiaiAgentScene], template: SceneTemplate) -> Dict[str, Any]:
    """模板元数据 + overrides 白名单合并（未知覆盖键忽略）。"""
    overrides = (scene.overrides or {}) if scene is not None else {}
    if not isinstance(overrides, dict):
        overrides = {}
    out = {
        "name": template.name,
        "description": template.description,
        "image_key": template.image_key,
        "sample_prompt": template.sample_prompt,
        "capability_tags": list(template.capability_tags),
        "scene_route": template.scene_route,
    }
    for key in SCENE_OVERRIDE_KEYS:
        value = overrides.get(key)
        if value is None:
            continue
        if key == "capability_tags":
            if isinstance(value, list) and all(
                str(v) in SCENE_CAPABILITY_TAGS for v in value
            ):
                out[key] = [str(v) for v in value]
            continue
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()
    return out


def _route_available(
    route: Optional[str], granted: Dict[str, bool]
) -> bool:
    """路由白名单内 + 当前用户持有页面读权限。"""
    if not route:
        return False
    permission = SCENE_ROUTE_PERMISSIONS.get(route)
    if not permission:
        return False
    return bool(granted.get(permission))


async def _route_permissions_for_user(
    tenant_id: int, user: Optional[User]
) -> Dict[str, bool]:
    out: Dict[str, bool] = {}
    for route, code in SCENE_ROUTE_PERMISSIONS.items():
        out[code] = await _has_permission(user, tenant_id, code)
    return out


async def _build_item(
    tenant_id: int,
    user: Optional[User],
    template: SceneTemplate,
    scene: Optional[KuaiaiAgentScene],
    *,
    switches: Dict[str, bool],
    usable_profile_ids: set,
    has_agent_read: bool,
    chat_ready: bool,
    route_grants: Dict[str, bool],
    profiles_by_id: Dict[int, KuaiaiAgentProfile],
) -> Dict[str, Any]:
    merged = _merged_fields(scene, template)
    route = merged["scene_route"]
    scene_available = _route_available(route, route_grants)

    if scene is None:
        # 预置缺失占位卡：明确 not_ready，可重试，不伪装已绑定
        return {
            "key": template.key,
            "template_key": template.key,
            "name": merged["name"],
            "description": merged["description"],
            "image_key": merged["image_key"],
            "enabled": False,
            "status": "not_ready",
            "capability_tags": merged["capability_tags"],
            "sample_prompt": merged["sample_prompt"],
            "agent_profile_id": None,
            "scene_route": route,
            "scene_available": scene_available,
            "disabled_reason": "场景预置未完成，请重新同步应用后重试",
        }

    profile = profiles_by_id.get(scene.agent_profile_id)
    bound = profile is not None
    profile_enabled = bool(bound and profile.status == STATUS_ENABLED)
    has_use = bool(bound and int(profile.id) in usable_profile_ids)

    status = "ready"
    reason: Optional[str] = None
    if not switches.get(scene.template_key, True):
        status, reason = "not_ready", "场景总开关已停用"
    elif not scene.enabled:
        status, reason = "not_ready", "场景实例已停用"
    elif scene.agent_profile_id is None:
        status, reason = "not_ready", "未绑定 Agent 档案"
    elif not bound:
        status, reason = "not_ready", "绑定的 Agent 档案不存在或已删除"
    elif not profile_enabled:
        status, reason = "not_ready", "Agent 档案未启用"
    elif not chat_ready:
        status, reason = "partial", "未配置可用的对话模型连接"
    elif not has_use:
        status, reason = "partial", "当前用户无该 Agent 档案使用权"

    # 档案 ID 脱敏：无使用权且无管理读权限的用户不下发真实 id
    profile_id_out: Optional[int] = None
    if bound and (has_use or has_agent_read):
        profile_id_out = int(profile.id)

    return {
        "key": scene.instance_key,
        "template_key": scene.template_key,
        "name": merged["name"],
        "description": merged["description"],
        "image_key": merged["image_key"],
        "enabled": bool(scene.enabled),
        "status": status,
        "capability_tags": merged["capability_tags"],
        "sample_prompt": merged["sample_prompt"],
        "agent_profile_id": profile_id_out,
        "scene_route": route,
        "scene_available": scene_available,
        "disabled_reason": reason,
    }


async def list_agent_library(tenant_id: int, user: Optional[User]) -> Dict[str, Any]:
    """智能体库聚合：六预置项 + 租户复制项 + provisioning 状态。"""
    scenes = await KuaiaiAgentScene.filter(
        tenant_id=tenant_id, deleted_at__isnull=True
    ).order_by("id").all()
    scene_by_key = {s.instance_key: s for s in scenes}

    profile_ids = [s.agent_profile_id for s in scenes if s.agent_profile_id]
    profiles_by_id: Dict[int, KuaiaiAgentProfile] = {}
    if profile_ids:
        rows = await KuaiaiAgentProfile.filter(
            tenant_id=tenant_id,
            id__in=profile_ids,
            deleted_at__isnull=True,
        ).all()
        profiles_by_id = {p.id: p for p in rows}

    switches = await agent_switches(tenant_id)
    usable = await grant_service.usable_profile_ids(tenant_id, user)
    has_agent_read = await _has_permission(user, tenant_id, "kuaiai:agent:read")
    chat_ready = await is_chat_ready(tenant_id)
    route_grants = await _route_permissions_for_user(tenant_id, user)

    common = dict(
        switches=switches,
        usable_profile_ids=usable,
        has_agent_read=has_agent_read,
        chat_ready=chat_ready,
        route_grants=route_grants,
        profiles_by_id=profiles_by_id,
    )

    items: List[Dict[str, Any]] = []
    for template in SCENE_TEMPLATES:
        scene = scene_by_key.get(template.key)
        items.append(
            await _build_item(tenant_id, user, template, scene, **common)
        )

    # 租户复制实例：非预置 instance_key，按创建顺序稳定排序
    copies = [s for s in scenes if s.instance_key not in TEMPLATE_KEYS]
    copies.sort(key=lambda s: (_TEMPLATE_ORDER.get(s.template_key, 999), s.id))
    for scene in copies:
        template = _TEMPLATE_MAP.get(scene.template_key)
        if template is None:
            # 孤儿复制项（模板已下线）：仍以最小模板视图返回，key/template_key 保留
            template = SceneTemplate(
                key=scene.template_key,
                name=scene.instance_key,
                description="",
                image_key="",
                capability_tags=(),
                sample_prompt="",
                scene_route=None,
                system_prompt="",
                readonly_tools=(),
            )
        items.append(
            await _build_item(tenant_id, user, template, scene, **common)
        )

    missing_keys = [t.key for t in SCENE_TEMPLATES if t.key not in scene_by_key]
    return {
        "provisioning": {
            "complete": not missing_keys,
            "missing_template_keys": missing_keys,
            "retryable": True,
        },
        "items": items,
    }


# ============================================================ 定制/改绑/克隆


def _validate_override_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """PUT/克隆的覆盖字段白名单校验：返回归一后的 overrides 增量。

    显式传 None 表示清除该覆盖（回落模板值）；未知键由 schema extra=forbid
    拦截，这里再做一层防御性白名单。
    """
    out: Dict[str, Any] = {}
    if "name" in data:
        value = data["name"]
        if value is not None:
            name = str(value).strip()
            if not name or len(name) > 100:
                raise BusinessLogicError("name 长度须为 1-100 字符")
            out["name"] = name
        else:
            out["name"] = None
    if "description" in data:
        value = data["description"]
        if value is not None:
            desc = str(value).strip()
            if len(desc) > 2000:
                raise BusinessLogicError("description 长度不得超过 2000")
            out["description"] = desc or None
        else:
            out["description"] = None
    if "image_key" in data:
        value = data["image_key"]
        if value is not None:
            key = str(value).strip()
            if key not in SCENE_IMAGE_KEYS:
                raise BusinessLogicError("image_key 不在已登记资源白名单")
            out["image_key"] = key
        else:
            out["image_key"] = None
    if "sample_prompt" in data:
        value = data["sample_prompt"]
        if value is not None:
            prompt = str(value).strip()
            if len(prompt) > 500:
                raise BusinessLogicError("sample_prompt 长度不得超过 500")
            out["sample_prompt"] = prompt or None
        else:
            out["sample_prompt"] = None
    if "capability_tags" in data:
        value = data["capability_tags"]
        if value is not None:
            if not isinstance(value, list):
                raise BusinessLogicError("capability_tags 必须为字符串列表")
            tags = [str(v).strip() for v in value if str(v).strip()]
            unknown = [t for t in tags if t not in SCENE_CAPABILITY_TAGS]
            if unknown:
                raise BusinessLogicError(
                    f"capability_tags 含未登记标签: {', '.join(unknown)}"
                )
            out["capability_tags"] = tags
        else:
            out["capability_tags"] = None
    if "scene_route" in data:
        value = data["scene_route"]
        if value is not None:
            route = str(value).strip()
            if route not in SCENE_ROUTE_PERMISSIONS:
                raise BusinessLogicError("scene_route 不在服务端路由白名单")
            out["scene_route"] = route
        else:
            out["scene_route"] = None
    return out


async def update_instance(
    tenant_id: int,
    user: Optional[User],
    instance_key: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """实例定制/改绑/单项开关：仅本租户实例，覆盖字段白名单，同事务写。"""
    key = (instance_key or "").strip()
    if not key or len(key) > 80:
        raise NotFoundError("场景实例", instance_key)
    scene = await KuaiaiAgentScene.get_or_none(
        tenant_id=tenant_id, instance_key=key, deleted_at__isnull=True
    )
    if scene is None and key in TEMPLATE_KEYS:
        # 预置实例缺失：先走幂等补齐，仍缺则显式报错（不造匿名虚拟实例）
        await seed_kuaiai_agent_scenes_on_lifecycle(tenant_id)
        scene = await KuaiaiAgentScene.get_or_none(
            tenant_id=tenant_id, instance_key=key, deleted_at__isnull=True
        )
    if scene is None:
        raise NotFoundError("场景实例", instance_key)

    profile: Optional[KuaiaiAgentProfile] = None
    if "agent_profile_id" in data:
        # 改绑需要档案管理读权限（路由层已校验 entry+display+manage）
        await _require_permission(user, tenant_id, "kuaiai:agent:read")
        pid = data["agent_profile_id"]
        if pid is not None:
            profile = await agent_service.get_profile(tenant_id, int(pid))

    override_patch = _validate_override_fields(data)

    async with in_transaction():
        locked = await KuaiaiAgentScene.filter(
            tenant_id=tenant_id, id=scene.id, deleted_at__isnull=True
        ).select_for_update().first()
        if locked is None:
            raise NotFoundError("场景实例", instance_key)
        if "agent_profile_id" in data:
            locked.agent_profile_id = profile.id if profile else None
        # enabled 显式 null 视为未传（不解绑语义不适用布尔开关，防止 null 误停用）
        if "enabled" in data and data["enabled"] is not None:
            locked.enabled = bool(data["enabled"])
        if override_patch:
            overrides = dict(locked.overrides or {})
            for field, value in override_patch.items():
                if value is None:
                    overrides.pop(field, None)
                else:
                    overrides[field] = value
            locked.overrides = overrides
        locked.update_from_dict(_audit_update(user))
        await locked.save()
        scene = locked

    view = await list_agent_library(tenant_id, user)
    for item in view["items"]:
        if item["key"] == scene.instance_key:
            return item
    raise NotFoundError("场景实例", instance_key)


async def _unique_clone_profile_name(tenant_id: int, source_name: str) -> str:
    """克隆档案名：源名截断 +（副本）后缀，冲突递增序号（仅名称重试）。"""
    base = source_name.strip()[:96]
    for i in range(1, 50):
        suffix = "（副本）" if i == 1 else f"（副本{i}）"
        candidate = f"{base[:100 - len(suffix)]}{suffix}"
        dup = await KuaiaiAgentProfile.get_or_none(
            tenant_id=tenant_id, name=candidate, deleted_at__isnull=True
        )
        if dup is None:
            return candidate
    raise BusinessLogicError("无法为克隆档案分配唯一名称")


async def _new_copy_instance_key(tenant_id: int, template_key: str) -> str:
    """复制实例 key：服务端生成，不与既有/软删 key 冲突。"""
    for _ in range(10):
        candidate = f"{template_key}-copy-{uuid_module.uuid4().hex[:8]}"
        exists = await KuaiaiAgentScene.filter(
            tenant_id=tenant_id, instance_key=candidate
        ).exists()
        if not exists:
            return candidate
    raise BusinessLogicError("无法为复制场景分配唯一 key")


async def clone_instance(
    tenant_id: int,
    user: User,
    template_key: str,
    source_agent_id: int,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """按需克隆：本租户源档案 → 新停用无授权档案 + 复制实例（同事务原子）。

    - 源档案跨租户/不存在 → 404；不复制 grants/密钥/租户身份；
    - 源档案 default_model_id 存在时按本租户启用 chat 目录行复核后在事务内
      写入；复核失败整个克隆回滚（不静默复制/丢弃）；
    - 新实例 key 服务端生成，不触碰六个预置实例。
    """
    template = _TEMPLATE_MAP.get((template_key or "").strip())
    if template is None:
        raise ValidationError("未知场景模板 key")
    source = await agent_service.get_profile(tenant_id, int(source_agent_id))
    source_model_id = getattr(source, "default_model_id", None)

    override_values: Dict[str, Any] = {}
    if overrides:
        override_values = {
            k: v
            for k, v in _validate_override_fields(dict(overrides)).items()
            if v is not None
        }

    audit = {
        "created_by": user.id,
        "created_by_name": getattr(user, "full_name", None)
        or getattr(user, "username", None),
        "updated_by": user.id,
        "updated_by_name": getattr(user, "full_name", None)
        or getattr(user, "username", None),
    }

    async with in_transaction():
        if source_model_id is not None:
            # spec 181：default_model_id 沿用 agent_service 同租户 chat 模型复核，
            # 校验与档案写入同事务——非法（停用/删除/非 chat/跨租户）即整体回滚
            await agent_service._require_chat_model(
                tenant_id, int(source_model_id)
            )
        name = await _unique_clone_profile_name(tenant_id, source.name)
        payload = AgentProfileCreate(
            name=name,
            description=source.description,
            system_prompt=source.system_prompt,
            default_model_id=None,
            knowledge_ids=list(source.knowledge_ids or []),
            enabled_tools=list(source.enabled_tools or []),
            mcp_server_ids=list(source.mcp_server_ids or []),
            status=STATUS_DISABLED,
            grant_mode=(source.grant_mode or GRANT_MODE_ROLE),
        )
        profile = await agent_service.create_profile(tenant_id, user, payload)
        if source_model_id is not None:
            profile.default_model_id = int(source_model_id)
            await profile.save(update_fields=["default_model_id"])

        instance_key = await _new_copy_instance_key(tenant_id, template.key)
        scene = await KuaiaiAgentScene.create(
            tenant_id=tenant_id,
            instance_key=instance_key,
            template_key=template.key,
            origin=SCENE_ORIGIN_COPY,
            agent_profile_id=profile.id,
            overrides=override_values,
            enabled=True,
            **audit,
        )

    view = await list_agent_library(tenant_id, user)
    for item in view["items"]:
        if item["key"] == scene.instance_key:
            return item
    raise NotFoundError("场景实例", scene.instance_key)


# ============================================================ chat 场景守卫


async def guard_scene_agent_key(
    tenant_id: int,
    agent_key: str,
    agent_id: Optional[int],
    user: Optional[User],
) -> None:
    """``extra.agent_key`` 场景守卫（T9）：拒绝先于档案装配与落库。

    校验链：同租户实例存在 → 模板总开关 → 实例 enabled → 请求 agent_id
    与绑定一致 → 档案存在/启用 → 当前用户使用权 → chat 就绪。
    不携带 agent_key 的普通对话不进入本守卫。
    """
    key = (agent_key or "").strip()
    if not key:
        raise ValidationError("agent_key 不能为空")
    scene = await KuaiaiAgentScene.get_or_none(
        tenant_id=tenant_id, instance_key=key, deleted_at__isnull=True
    )
    if scene is None:
        raise NotFoundError("场景", key)

    switches = await agent_switches(tenant_id)
    if not switches.get(scene.template_key, True):
        raise BusinessLogicError("该场景已被总开关停用")
    if not scene.enabled:
        raise BusinessLogicError("该场景实例已停用")
    if scene.agent_profile_id is None:
        raise BusinessLogicError("该场景未绑定 Agent 档案")
    if agent_id is None or int(agent_id) != int(scene.agent_profile_id):
        raise BusinessLogicError("agent_id 与场景绑定档案不一致")

    profile = await KuaiaiAgentProfile.get_or_none(
        tenant_id=tenant_id,
        id=scene.agent_profile_id,
        deleted_at__isnull=True,
    )
    if profile is None:
        raise NotFoundError("Agent 档案", str(scene.agent_profile_id))
    if profile.status != STATUS_ENABLED:
        raise AuthorizationError("该 Agent 档案已停用")
    if not await grant_service.check_use_grant(tenant_id, profile, user):
        raise AuthorizationError("无该 Agent 档案使用权")
    if not await is_chat_ready(tenant_id):
        raise BusinessLogicError("未配置可用的对话模型，请先完成 AI 连接器设置")
