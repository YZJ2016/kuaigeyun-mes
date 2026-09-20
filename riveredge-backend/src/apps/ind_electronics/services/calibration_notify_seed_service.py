"""R-09 外校提醒行业预置：站内信、暂不开短信（真源 生产/外校提醒接收人.txt）。"""

from __future__ import annotations

from loguru import logger

from apps.kuaizhizao.services.equipment_calibration_settings_service import (
    merge_calibration_reminder_settings,
)
from apps.kuaizhizao.services.kuaizhizao_notification_rule_presets import (
    CALIBRATION_NOTIFICATION_PRESET_IDS,
    ensure_kuaizhizao_notification_rules_for_preset_ids,
)


async def ensure_electronics_calibration_notify(tenant_id: int) -> dict[str, int]:
    """启用电子包：外校到期前 30 天 + 过期 1 天站内提醒规则。"""
    await merge_calibration_reminder_settings(
        tenant_id,
        advance_days=30,
        notify_channels=["internal"],
        description="行业包：外校提醒仅站内信（用户提供模板暂不用短信）",
    )
    rules = await ensure_kuaizhizao_notification_rules_for_preset_ids(
        tenant_id,
        preset_ids=CALIBRATION_NOTIFICATION_PRESET_IDS,
        enabled=True,
    )
    logger.info(
        "electronics_calibration_notify_seeded tenant={} rules={}",
        tenant_id,
        rules,
    )
    return rules


async def deactivate_electronics_calibration_notify(tenant_id: int) -> dict[str, int]:
    """停用行业包：关闭外校提醒规则（不删模板与历史消息）。"""
    rules = await ensure_kuaizhizao_notification_rules_for_preset_ids(
        tenant_id,
        preset_ids=CALIBRATION_NOTIFICATION_PRESET_IDS,
        enabled=False,
    )
    logger.info(
        "electronics_calibration_notify_deactivated tenant={} rules={}",
        tenant_id,
        rules,
    )
    return rules
