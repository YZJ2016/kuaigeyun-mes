"""R-06 生产文件/OA 上线清单行业预置（真源 研发电子/OA系统模版.xls Sheet2）。"""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional

from loguru import logger

from apps.ind_electronics.seeds.phase2_templates import (
    ELECTRONICS_PRODUCTION_FILE_CHECKLIST_ITEMS,
    PRODUCTION_FILE_CHECKLIST_CONFIG_KEY,
)
from infra.models.tenant_config import TenantConfig
from infra.services.tenant_service import TenantService


async def get_production_file_checklist(tenant_id: int) -> Optional[Dict[str, Any]]:
    row = await TenantService().get_tenant_config(tenant_id, PRODUCTION_FILE_CHECKLIST_CONFIG_KEY)
    if not row or not isinstance(row.config_value, dict):
        return None
    if not row.config_value.get("enabled"):
        return None
    return copy.deepcopy(row.config_value)


async def ensure_electronics_production_file_checklist(tenant_id: int) -> int:
    existing = await TenantConfig.filter(
        tenant_id=tenant_id, config_key=PRODUCTION_FILE_CHECKLIST_CONFIG_KEY
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
        "extension_id": "electronics.production_file_checklist",
        "module_app_code": "ind-electronics",
        "items": copy.deepcopy(ELECTRONICS_PRODUCTION_FILE_CHECKLIST_ITEMS),
        "source_note": "真源 研发电子/OA系统模版.xls Sheet2（清单对照，不含客户人名）",
    }
    await TenantService().set_tenant_config(
        tenant_id,
        PRODUCTION_FILE_CHECKLIST_CONFIG_KEY,
        payload,
        description="行业扩展：电子制造 OA 上线资料清单",
    )
    logger.info("electronics_production_file_checklist_seeded tenant={}", tenant_id)
    return 1


async def deactivate_electronics_production_file_checklist(tenant_id: int) -> int:
    row = await TenantConfig.filter(
        tenant_id=tenant_id, config_key=PRODUCTION_FILE_CHECKLIST_CONFIG_KEY
    ).first()
    if not row:
        return 0
    await row.delete()
    logger.info("electronics_production_file_checklist_deactivated tenant={}", tenant_id)
    return 1


async def get_production_file_checklist_summary(tenant_id: int) -> Dict[str, Any]:
    cfg = await get_production_file_checklist(tenant_id)
    if not cfg:
        return {"enabled": False, "items": []}
    items = cfg.get("items") or []
    production_file_items = [
        x
        for x in items
        if isinstance(x, dict)
        and (
            x.get("host_module") == "kuaiplm.production_file"
            or x.get("catalog_kind") in {"pe_production", "rd_tool"}
        )
    ]
    return {
        "enabled": True,
        "item_count": len(items) if isinstance(items, list) else 0,
        "production_file_item_count": len(production_file_items),
        "items": items if isinstance(items, list) else [],
        "production_file_items": production_file_items,
        "source_note": cfg.get("source_note"),
    }
