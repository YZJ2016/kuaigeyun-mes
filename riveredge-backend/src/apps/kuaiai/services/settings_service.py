"""KU-AI 模型与能力设置聚合服务（spec 185 / 设计 §10、§11.6）。

- GET：chat/vision 角色候选连接（本租户、启用、config.model_role 匹配）+
  OCR 脱敏视图 + 六模板总开关 + 能力项 + 乐观版本；不返回任何密钥/cipher；
- PUT：候选连接复用 ``select_llm_connection_role`` 的校验语义（不走其立即
  保存分支）；事务内 ``select_for_update`` 锁定站点行、锁内重算版本比对
  （不一致 409），全部校验后把角色 UUID / agent_switches / 能力字段一次
  深合并写回 ``settings.integrations.kuaiai`` 并单次 save，提交后失效模型
  缓存；连接 ``config`` 与 kuaiai 槽外其他键一律不动；
- 保存审计只记操作者 + 旧/新角色 UUID + 变更字段名，不记密钥与
  ``custom_system_prompt`` 全文。
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any, Dict, List, Optional

from loguru import logger
from tortoise.transactions import in_transaction

from apps.kuaiai.services.agent_scene_service import SCENE_TEMPLATES
from core.utils.integration_settings import (
    AGENT_SWITCHES_SETTING_KEY,
    LLM_PROVIDER_SPECS,
    _connection_config,
    _is_masked_api_key,
    get_kuaiai_integration,
    mask_connection_base_url,
    merge_kuaiai_capability_fields,
    normalize_rag_backend,
    read_agent_switches,
    role_connection_setting_key,
    validate_agent_switches_payload,
    validate_llm_role_candidate,
)
from infra.exceptions.exceptions import ConflictError, NotFoundError

# 六模板 key 按 SCENE_TEMPLATES 声明顺序输出
_ORDERED_TEMPLATE_KEYS: tuple = tuple(t.key for t in SCENE_TEMPLATES)


def _version_of(site: Any) -> str:
    """乐观版本：由站点行身份 + updated_at 派生的不透明字符串。"""
    updated = getattr(site, "updated_at", None)
    stamp = updated.isoformat() if updated is not None else "0"
    raw = f"{getattr(site, 'uuid', '')}|{getattr(site, 'id', '')}|{stamp}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _capabilities_view(kuaiai: Dict[str, Any]) -> Dict[str, Any]:
    """能力项读视图：缺省值与运行时 _merge_kuaiai_capabilities 一致。"""
    return {
        "tools_enabled": kuaiai.get("tools_enabled", True) is not False,
        "rag_enabled": kuaiai.get("rag_enabled", True) is not False,
        "rag_use_embedding": kuaiai.get("rag_use_embedding", True) is not False,
        "rag_backend": normalize_rag_backend(kuaiai.get("rag_backend")),
        "rag_top_k": int(kuaiai.get("rag_top_k") or 5),
        "stream_enabled": kuaiai.get("stream_enabled", True) is not False,
        "custom_system_prompt": kuaiai.get("custom_system_prompt") or "",
    }


def _option_view(connection: Any, role: str, selected_uuid: str) -> Dict[str, Any]:
    cfg = _connection_config(connection)
    uuid_str = str(connection.uuid)
    return {
        "uuid": uuid_str,
        "name": str(getattr(connection, "name", "") or ""),
        "provider": str(getattr(connection, "type", "") or ""),
        "model": str(cfg.get("model") or "") or None,
        "model_role": role,
        "is_active": getattr(connection, "is_active", None) is True,
        "is_selected": uuid_str == selected_uuid,
    }


async def _list_role_options(
    tenant_id: int, role: str, selected_uuid: str
) -> List[Dict[str, Any]]:
    """候选连接：本租户、未软删、启用、config.model_role 匹配；不含密钥。"""
    from core.models.integration_config import IntegrationConfig

    rows = await IntegrationConfig.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        is_active=True,
        type__in=list(LLM_PROVIDER_SPECS),
    ).order_by("created_at", "id").all()
    options: List[Dict[str, Any]] = []
    for connection in rows:
        cfg = _connection_config(connection)
        if str(cfg.get("model_role") or "").strip() != role:
            continue
        options.append(_option_view(connection, role, selected_uuid))
    return options


def _ocr_view(connection: Optional[Any]) -> Dict[str, Any]:
    """OCR 脱敏视图：只回 configured / base_url 脱敏 / 模型名。"""
    if connection is None:
        return {"configured": False, "base_url_masked": "", "model": None}
    cfg = _connection_config(connection)
    base_url = str(cfg.get("base_url") or "").strip()
    model = str(cfg.get("model") or "").strip()
    api_key = str(cfg.get("api_key") or "").strip()
    configured = bool(
        getattr(connection, "is_active", None) is True
        and base_url
        and model
        and api_key
        and not _is_masked_api_key(api_key)
    )
    return {
        "configured": configured,
        "base_url_masked": mask_connection_base_url(base_url),
        "model": model or None,
    }


async def _load_connection_for_role(
    tenant_id: int, conn_uuid: str, role: str
) -> Any:
    """事务内锁定 PUT 候选连接并复核角色、启用状态和凭据。"""
    from core.models.integration_config import IntegrationConfig

    connection = await IntegrationConfig.filter(
        tenant_id=tenant_id,
        uuid=str(conn_uuid or "").strip(),
        deleted_at__isnull=True,
    ).select_for_update().first()
    if connection is None:
        raise NotFoundError("应用连接不存在")
    validate_llm_role_candidate(connection, role)
    return connection


async def get_settings(tenant_id: int) -> Dict[str, Any]:
    """GET /operations/settings 聚合（缺省值与运行时读取语义一致）。"""
    from core.services.system.site_setting_service import SiteSettingService
    from core.utils.integration_settings import _load_llm_connection

    site = await SiteSettingService.get_settings(tenant_id)
    kuaiai = get_kuaiai_integration(site.settings or {})
    chat_uuid = str(
        kuaiai.get(role_connection_setting_key("chat")) or ""
    ).strip()
    vision_uuid = str(
        kuaiai.get(role_connection_setting_key("vision")) or ""
    ).strip()

    chat_options = await _list_role_options(tenant_id, "chat", chat_uuid)
    vision_options = await _list_role_options(tenant_id, "vision", vision_uuid)
    vision_connection = await _load_llm_connection(tenant_id, vision_uuid)

    return {
        "chat_connection_uuid": chat_uuid or None,
        "vision_connection_uuid": vision_uuid or None,
        "chat_options": chat_options,
        "vision_options": vision_options,
        "ocr": _ocr_view(vision_connection),
        "agent_switches": read_agent_switches(kuaiai, _ORDERED_TEMPLATE_KEYS),
        "capabilities": _capabilities_view(kuaiai),
        "version": _version_of(site),
    }


async def update_settings(tenant_id: int, user: Any, payload: Any) -> Dict[str, Any]:
    """PUT /operations/settings：版本校验 + 单事务原子深合并保存。

    顺序：agent_switches 闭集校验 → 初始化站点行 → 事务内按 UUID 排序
    锁定 chat/vision 候选连接并校验 → 锁站点行重算版本比对 → 深合并
    白名单字段一次 save → 提交后失效模型缓存；任一失败整体回滚。
    """
    from core.models.site_setting import SiteSetting
    from core.services.system.site_setting_service import SiteSettingService

    switches = validate_agent_switches_payload(
        payload.agent_switches, _ORDERED_TEMPLATE_KEYS
    )
    vision_uuid = str(payload.vision_connection_uuid or "").strip()

    # 站点行缺失先经既有服务初始化（含遗留迁移），再在事务内锁定
    await SiteSettingService.get_settings(tenant_id)

    changed_fields: List[str] = []
    old_chat_uuid = ""
    old_vision_uuid = ""
    new_chat_uuid = ""
    new_vision_uuid = ""

    async with in_transaction():
        requested_roles = {
            "chat": str(payload.chat_connection_uuid).strip(),
        }
        if vision_uuid:
            requested_roles["vision"] = vision_uuid

        locked_connections: Dict[str, Any] = {}
        for connection_uuid in sorted(set(requested_roles.values())):
            roles = [
                role
                for role, requested_uuid in requested_roles.items()
                if requested_uuid == connection_uuid
            ]
            connection = await _load_connection_for_role(
                tenant_id, connection_uuid, roles[0]
            )
            for role in roles[1:]:
                validate_llm_role_candidate(connection, role)
            locked_connections[connection_uuid] = connection

        new_chat_uuid = str(
            locked_connections[requested_roles["chat"]].uuid
        )
        new_vision_uuid = (
            str(locked_connections[vision_uuid].uuid) if vision_uuid else ""
        )

        locked = await SiteSetting.filter(
            tenant_id=tenant_id, deleted_at__isnull=True
        ).order_by("id").select_for_update().first()
        if locked is None:
            raise NotFoundError("站点设置")
        if payload.version != _version_of(locked):
            raise ConflictError("设置已被他人修改，请刷新后重试")

        settings = deepcopy(locked.settings or {})
        integrations = settings.get("integrations")
        if not isinstance(integrations, dict):
            integrations = {}
            settings["integrations"] = integrations
        kuaiai = integrations.get("kuaiai")
        if not isinstance(kuaiai, dict):
            kuaiai = {}
            integrations["kuaiai"] = kuaiai

        old_chat_uuid = str(
            kuaiai.get(role_connection_setting_key("chat")) or ""
        ).strip()
        old_vision_uuid = str(
            kuaiai.get(role_connection_setting_key("vision")) or ""
        ).strip()

        if new_chat_uuid != old_chat_uuid:
            kuaiai[role_connection_setting_key("chat")] = new_chat_uuid
            changed_fields.append("chat_connection_uuid")
        if new_vision_uuid != old_vision_uuid:
            kuaiai[role_connection_setting_key("vision")] = new_vision_uuid
            changed_fields.append("vision_connection_uuid")
        if kuaiai.get(AGENT_SWITCHES_SETTING_KEY) != switches:
            changed_fields.append("agent_switches")
        kuaiai[AGENT_SWITCHES_SETTING_KEY] = switches

        changed_fields.extend(
            merge_kuaiai_capability_fields(
                kuaiai, payload.capabilities.model_dump()
            )
        )

        locked.settings = settings
        await locked.save(update_fields=["settings", "updated_at"])

    from core.ai.runtime.model_factory import evict_model_cache

    evict_model_cache(tenant_id)

    operator = getattr(user, "id", None)
    logger.info(
        "kuaiai 设置已保存 tenant_id={} operator={} chat={}->{} vision={}->{} changed={}",
        tenant_id,
        operator,
        old_chat_uuid or "-",
        new_chat_uuid or "-",
        old_vision_uuid or "-",
        new_vision_uuid or "-",
        ",".join(changed_fields) if changed_fields else "-",
    )

    return await get_settings(tenant_id)
