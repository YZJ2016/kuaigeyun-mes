"""R-14 证照合规清单行业预置：15 类事项对照（不含人名与具体有效期）。"""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional

from loguru import logger

from apps.ind_electronics.seeds.phase2_templates import (
    ELECTRONICS_LICENSE_CATALOG_ITEMS,
    LICENSE_CATALOG_CONFIG_KEY,
)
from infra.exceptions.exceptions import ValidationError
from infra.models.tenant_config import TenantConfig
from infra.services.tenant_service import TenantService


async def get_license_catalog(tenant_id: int) -> Optional[Dict[str, Any]]:
    row = await TenantService().get_tenant_config(tenant_id, LICENSE_CATALOG_CONFIG_KEY)
    if not row or not isinstance(row.config_value, dict):
        return None
    if not row.config_value.get("enabled"):
        return None
    return copy.deepcopy(row.config_value)


async def ensure_electronics_license_catalog(tenant_id: int) -> int:
    existing = await TenantConfig.filter(
        tenant_id=tenant_id, config_key=LICENSE_CATALOG_CONFIG_KEY
    ).first()
    if existing:
        cfg = existing.config_value if isinstance(existing.config_value, dict) else {}
        if cfg.get("enabled"):
            return 0
        cfg["enabled"] = True
        existing.config_value = cfg
        await existing.save()
        return 0

    payload = {
        "enabled": True,
        "extension_id": "electronics.license_catalog",
        "module_app_code": "ind-electronics",
        "default_reminder_days": 30,
        "items": copy.deepcopy(ELECTRONICS_LICENSE_CATALOG_ITEMS),
        "source_note": "真源 IT及设备/证照/(2026年)公司证件类工作事项跟踪表_V3.xls",
    }
    await TenantService().set_tenant_config(
        tenant_id,
        LICENSE_CATALOG_CONFIG_KEY,
        payload,
        description="行业扩展：证照合规 15 类事项清单",
    )
    logger.info("electronics_license_catalog_seeded tenant={}", tenant_id)
    return 1


async def deactivate_electronics_license_catalog(tenant_id: int) -> int:
    row = await TenantConfig.filter(
        tenant_id=tenant_id, config_key=LICENSE_CATALOG_CONFIG_KEY
    ).first()
    if not row:
        return 0
    await row.delete()
    logger.info("electronics_license_catalog_deactivated tenant={}", tenant_id)
    return 1


async def apply_license_catalog_stubs(tenant_id: int, user_id: int) -> Dict[str, int]:
    """按行业清单创建缺失的证照台账占位（不含有效期，须人工补录）。"""
    cfg = await get_license_catalog(tenant_id)
    if not cfg:
        raise ValidationError("行业证照清单未启用")

    from apps.kuaioa.models.license import KuaioaLicense
    from apps.kuaioa.schemas.license import LicenseCreate
    from apps.kuaioa.services.license_service import LicenseRegistryService

    items = cfg.get("items") or []
    if not isinstance(items, list):
        raise ValidationError("行业证照清单损坏")

    default_days = int(cfg.get("default_reminder_days") or 30)
    svc = LicenseRegistryService()
    created = 0
    skipped = 0
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item_name = str(raw.get("item_name") or "").strip()
        license_type = str(raw.get("license_type") or "").strip()
        item_code = str(raw.get("item_code") or "").strip()
        if not item_name or not license_type:
            continue
        exists = await KuaioaLicense.filter(
            tenant_id=tenant_id,
            license_name=item_name,
            license_type=license_type,
            deleted_at__isnull=True,
        ).exists()
        if exists:
            skipped += 1
            continue
        notes = f"catalog_item={item_code}" if item_code else None
        renewal = str(raw.get("renewal_frequency") or "").strip()
        if renewal:
            notes = (notes + f"; renewal={renewal}") if notes else f"renewal={renewal}"
        await svc.create_license(
            tenant_id,
            LicenseCreate(
                license_name=item_name,
                license_type=license_type,
                reminder_days=int(raw.get("default_reminder_days") or default_days),
                notify_enabled=True,
                notify_channels=["internal"],
                notes=notes,
            ),
            user_id,
        )
        created += 1

    logger.info(
        "electronics_license_catalog_applied tenant={} created={} skipped={}",
        tenant_id,
        created,
        skipped,
    )
    return {"created": created, "skipped": skipped}


async def get_license_catalog_summary(tenant_id: int) -> Dict[str, Any]:
    cfg = await get_license_catalog(tenant_id)
    if not cfg:
        return {"enabled": False, "items": []}
    items = cfg.get("items") or []
    return {
        "enabled": True,
        "default_reminder_days": cfg.get("default_reminder_days", 30),
        "item_count": len(items) if isinstance(items, list) else 0,
        "items": items if isinstance(items, list) else [],
        "source_note": cfg.get("source_note"),
    }
