"""设备校准到期提醒租户配置读写。"""

from __future__ import annotations

from typing import Optional

from apps.kuaizhizao.constants.equipment_calibration_settings import (
    ALLOWED_CALIBRATION_NOTIFY_CHANNELS,
    DEFAULT_CALIBRATION_NOTIFY_CHANNELS,
    DEFAULT_CALIBRATION_REMINDER_ADVANCE_DAYS,
    EQUIPMENT_CALIBRATION_REMINDER_SETTINGS_KEY,
    MAX_CALIBRATION_REMINDER_ADVANCE_DAYS,
    MIN_CALIBRATION_REMINDER_ADVANCE_DAYS,
)
from infra.exceptions.exceptions import ValidationError
from infra.services.tenant_service import TenantService


def validate_calibration_reminder_advance_days(raw: object) -> int:
    """校验并规范化提前提醒天数。"""
    if raw is None:
        return DEFAULT_CALIBRATION_REMINDER_ADVANCE_DAYS
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"advance_days 必须为 {MIN_CALIBRATION_REMINDER_ADVANCE_DAYS}"
            f"–{MAX_CALIBRATION_REMINDER_ADVANCE_DAYS} 之间的整数"
        ) from exc
    if value < MIN_CALIBRATION_REMINDER_ADVANCE_DAYS or value > MAX_CALIBRATION_REMINDER_ADVANCE_DAYS:
        raise ValidationError(
            f"advance_days 须在 {MIN_CALIBRATION_REMINDER_ADVANCE_DAYS}"
            f"–{MAX_CALIBRATION_REMINDER_ADVANCE_DAYS} 之间"
        )
    return value


async def get_calibration_reminder_advance_days(tenant_id: int) -> int:
    """读取租户级校准到期提前提醒天数。"""
    svc = TenantService()
    row = await svc.get_tenant_config(tenant_id, EQUIPMENT_CALIBRATION_REMINDER_SETTINGS_KEY)
    if row and isinstance(row.config_value, dict) and "advance_days" in row.config_value:
        return validate_calibration_reminder_advance_days(row.config_value["advance_days"])
    return DEFAULT_CALIBRATION_REMINDER_ADVANCE_DAYS


def validate_calibration_notify_channels(raw: object) -> list[str]:
    if raw is None:
        return list(DEFAULT_CALIBRATION_NOTIFY_CHANNELS)
    if not isinstance(raw, list):
        raise ValidationError("notify_channels 必须为数组")
    out: list[str] = []
    for item in raw:
        ch = str(item or "").strip().lower()
        if ch not in ALLOWED_CALIBRATION_NOTIFY_CHANNELS:
            raise ValidationError(f"不支持的外校提醒渠道: {item}")
        if ch not in out:
            out.append(ch)
    if not out:
        raise ValidationError("notify_channels 至少包含一种渠道")
    return out


async def get_calibration_reminder_notify_channels(tenant_id: int) -> list[str]:
    svc = TenantService()
    row = await svc.get_tenant_config(tenant_id, EQUIPMENT_CALIBRATION_REMINDER_SETTINGS_KEY)
    if row and isinstance(row.config_value, dict) and "notify_channels" in row.config_value:
        return validate_calibration_notify_channels(row.config_value["notify_channels"])
    return list(DEFAULT_CALIBRATION_NOTIFY_CHANNELS)


async def get_calibration_reminder_settings(tenant_id: int) -> dict[str, object]:
    advance_days = await get_calibration_reminder_advance_days(tenant_id)
    notify_channels = await get_calibration_reminder_notify_channels(tenant_id)
    return {"advance_days": advance_days, "notify_channels": notify_channels}


async def set_calibration_reminder_settings(
    tenant_id: int,
    *,
    advance_days: int,
    notify_channels: Optional[list[str]] = None,
    description: Optional[str] = None,
) -> dict[str, object]:
    validated = validate_calibration_reminder_advance_days(advance_days)
    svc = TenantService()
    row = await svc.get_tenant_config(tenant_id, EQUIPMENT_CALIBRATION_REMINDER_SETTINGS_KEY)
    existing = row.config_value if row and isinstance(row.config_value, dict) else {}
    channels = (
        validate_calibration_notify_channels(notify_channels)
        if notify_channels is not None
        else validate_calibration_notify_channels(existing.get("notify_channels"))
    )
    payload = {"advance_days": validated, "notify_channels": channels}
    await svc.set_tenant_config(
        tenant_id,
        EQUIPMENT_CALIBRATION_REMINDER_SETTINGS_KEY,
        payload,
        description=description or "设备外校到期提醒配置",
    )
    return payload


async def merge_calibration_reminder_settings(
    tenant_id: int,
    *,
    advance_days: Optional[int] = None,
    notify_channels: Optional[list[str]] = None,
    description: Optional[str] = None,
) -> dict[str, object]:
    """合并写入：未传字段保留租户已有配置。"""
    current = await get_calibration_reminder_settings(tenant_id)
    days = (
        validate_calibration_reminder_advance_days(advance_days)
        if advance_days is not None
        else int(current["advance_days"])
    )
    channels = (
        validate_calibration_notify_channels(notify_channels)
        if notify_channels is not None
        else list(current["notify_channels"])
    )
    return await set_calibration_reminder_settings(
        tenant_id,
        advance_days=days,
        notify_channels=channels,
        description=description,
    )
