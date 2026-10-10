"""快数采 — 业务配置「消息提醒」规则预设。"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple
from uuid import UUID

from loguru import logger

from core.models.message_template import MessageTemplate
from core.services.messaging.message_template_service import MessageTemplateService
from infra.services.business_config_service import BusinessConfigService

DOC_IOT_ALERT = "iot_alert"
ACTION_THRESHOLD_BREACHED = "threshold_breached"
ACTION_DEVICE_OFFLINE = "device_offline"
BUILTIN_IN_APP_CHANNEL_UUID = "__builtin_internal_channel__"

KUAIIOT_NOTIFICATION_RULE_PRESETS: List[Dict[str, Any]] = [
    {
        "id": "iot_preset_alert_threshold",
        "scene_name": "设备点位告警",
        "trigger_document": DOC_IOT_ALERT,
        "trigger_action": ACTION_THRESHOLD_BREACHED,
        "template_code": "IOT_ALERT_THRESHOLD",
        "recipient_scopes": ["user_specified"],
        "enabled": False,
    },
    {
        "id": "iot_preset_device_offline",
        "scene_name": "设备离线告警",
        "trigger_document": DOC_IOT_ALERT,
        "trigger_action": ACTION_DEVICE_OFFLINE,
        "template_code": "IOT_DEVICE_OFFLINE",
        "recipient_scopes": ["user_specified"],
        "enabled": False,
    },
]

_IOT_TEMPLATE_CODES: Set[str] = {
    str(p.get("template_code") or "").strip()
    for p in KUAIIOT_NOTIFICATION_RULE_PRESETS
    if str(p.get("template_code") or "").strip()
}


def _normalize_rules(raw: Any) -> List[dict]:
    if isinstance(raw, dict) and isinstance(raw.get("rules"), list):
        return [r for r in raw["rules"] if isinstance(r, dict)]
    if isinstance(raw, dict) and raw.get("trigger_document"):
        return [raw]
    return []


def _rule_identity(rule: dict) -> Tuple[str, str]:
    return (
        str(rule.get("trigger_document") or "").strip(),
        str(rule.get("trigger_action") or "").strip(),
    )


def _preset_by_document_action() -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for preset in KUAIIOT_NOTIFICATION_RULE_PRESETS:
        key = _rule_identity(preset)
        if key[0] and key[1]:
            out[key] = preset
    return out


def _merge_recipient_scopes_from_preset(
    existing_scopes: Any, preset_scopes: List[str]
) -> Tuple[List[str], bool]:
    current = [str(s).strip() for s in (existing_scopes or []) if str(s).strip()]
    want = [str(s).strip() for s in preset_scopes if str(s).strip()]
    merged = list(current)
    changed = False
    for scope in want:
        if scope not in merged:
            merged.append(scope)
            changed = True
    return merged, changed


async def _template_uuid_by_code(tenant_id: int, code: str) -> str | None:
    row = await MessageTemplate.filter(
        tenant_id=tenant_id,
        code=code,
        deleted_at__isnull=True,
    ).first()
    if not row:
        return None
    return str(row.uuid)


async def _rule_template_ref_invalid(tenant_id: int, rule: dict) -> bool:
    ref = str(rule.get("template_uuid") or rule.get("template") or "").strip()
    if not ref:
        return True
    try:
        template_uuid = UUID(ref)
    except ValueError:
        return True
    return not await MessageTemplate.filter(
        tenant_id=tenant_id,
        uuid=str(template_uuid),
        deleted_at__isnull=True,
    ).exists()


async def load_kuaiiot_notification_rule_presets(tenant_id: int) -> Dict[str, int]:
    templates_created = await MessageTemplateService.load_preset_sme(
        tenant_id,
        only_codes=_IOT_TEMPLATE_CODES,
    )

    cfg = await BusinessConfigService().get_business_config(tenant_id)
    existing = _normalize_rules((cfg.get("parameters") or {}).get("notifications"))
    existing_keys: Set[Tuple[str, str]] = {_rule_identity(r) for r in existing}
    existing_ids = {str(r.get("id") or "") for r in existing if r.get("id")}
    preset_index = _preset_by_document_action()

    updated = 0
    repaired_templates = 0
    for rule in existing:
        current_scene = str(rule.get("scene_name") or "").strip()
        if "·" in current_scene or "・" in current_scene or "•" in current_scene:
            cleaned = current_scene.replace("·", "").replace("・", "").replace("•", "")
            if cleaned != current_scene:
                rule["scene_name"] = cleaned
                updated += 1
                current_scene = cleaned

        preset = preset_index.get(_rule_identity(rule))
        if not preset:
            continue
        merged_scopes, changed = _merge_recipient_scopes_from_preset(
            rule.get("recipient_scopes"),
            list(preset.get("recipient_scopes") or []),
        )
        if changed:
            rule["recipient_scopes"] = merged_scopes
            updated += 1
        preset_scene = str(preset.get("scene_name") or "").strip()
        if preset_scene and current_scene != preset_scene:
            rule["scene_name"] = preset_scene
            updated += 1
        template_code = str(preset.get("template_code") or "").strip()
        if template_code:
            rule["template_code"] = template_code
        if template_code and await _rule_template_ref_invalid(tenant_id, rule):
            template_uuid = await _template_uuid_by_code(tenant_id, template_code)
            if template_uuid:
                rule["template_uuid"] = template_uuid
                rule["template"] = template_uuid
                repaired_templates += 1

    created = 0
    skipped_missing_template = 0
    skipped_duplicate = 0

    for preset in KUAIIOT_NOTIFICATION_RULE_PRESETS:
        doc, action = _rule_identity(preset)
        if (doc, action) in existing_keys:
            skipped_duplicate += 1
            continue
        preset_id = str(preset.get("id") or "").strip()
        if preset_id and preset_id in existing_ids:
            skipped_duplicate += 1
            continue

        template_code = str(preset.get("template_code") or "").strip()
        template_uuid = await _template_uuid_by_code(tenant_id, template_code)
        if not template_uuid:
            logger.warning(
                "快数采消息提醒预设跳过：未找到消息模板 tenant={} code={}",
                tenant_id,
                template_code,
            )
            skipped_missing_template += 1
            continue

        existing.append(
            {
                "id": preset_id or f"iot_preset_{doc}_{action}",
                "scene_name": preset.get("scene_name") or f"{doc} {action}",
                "enabled": bool(preset.get("enabled", False)),
                "trigger_document": doc,
                "trigger_action": action,
                "channel_uuids": [BUILTIN_IN_APP_CHANNEL_UUID],
                "channels": [BUILTIN_IN_APP_CHANNEL_UUID],
                "recipient_scopes": list(preset.get("recipient_scopes") or []),
                "recipient_user_ids": [],
                "form_notify_default_user_ids": [],
                "template_uuid": template_uuid,
                "template": template_uuid,
                "template_code": template_code,
            }
        )
        existing_keys.add((doc, action))
        if preset_id:
            existing_ids.add(preset_id)
        created += 1

    if created > 0 or updated > 0 or repaired_templates > 0:
        await BusinessConfigService().batch_update_process_parameters(
            tenant_id,
            {"notifications": {"rules": existing}},
        )

    return {
        "created": created,
        "updated": updated,
        "repaired_templates": repaired_templates,
        "templates_created": templates_created,
        "skipped_duplicate": skipped_duplicate,
        "skipped_missing_template": skipped_missing_template,
        "total_rules": len(existing),
    }
