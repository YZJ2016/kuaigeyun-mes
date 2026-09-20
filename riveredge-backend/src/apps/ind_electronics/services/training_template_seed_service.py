"""R-12 培训模板行业预置：上岗证版式与 ESD 考核试卷。"""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional

from loguru import logger

from apps.ind_electronics.seeds.phase2_templates import (
    ANNUAL_TRAINING_PLAN_CONFIG_KEY,
    ELECTRONICS_ANNUAL_TRAINING_PLAN_PROFILE,
    ELECTRONICS_TRAINING_TEMPLATE_CODES,
    ELECTRONICS_TRAINING_TEMPLATES,
)
from apps.kuaioa.models.training import KuaioaTrainingTemplate
from core.utils.timezone_utils import resolve_business_datetime
from infra.models.tenant_config import TenantConfig
from infra.models.user import User
from infra.services.tenant_service import TenantService


async def _ensure_annual_training_plan_profile(tenant_id: int) -> int:
    existing = await TenantConfig.filter(
        tenant_id=tenant_id, config_key=ANNUAL_TRAINING_PLAN_CONFIG_KEY
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
        "extension_id": "electronics.training_templates",
        "module_app_code": "ind-electronics",
        **copy.deepcopy(ELECTRONICS_ANNUAL_TRAINING_PLAN_PROFILE),
        "source_note": "真源 人事/04-01年度培训计划.pdf（表头字段，无样例行）",
    }
    await TenantService().set_tenant_config(
        tenant_id,
        ANNUAL_TRAINING_PLAN_CONFIG_KEY,
        payload,
        description="行业扩展：年度培训计划行字段对照",
    )
    return 1


async def _deactivate_annual_training_plan_profile(tenant_id: int) -> int:
    row = await TenantConfig.filter(
        tenant_id=tenant_id, config_key=ANNUAL_TRAINING_PLAN_CONFIG_KEY
    ).first()
    if not row:
        return 0
    await row.delete()
    return 1


async def get_annual_training_plan_schema_summary(tenant_id: int) -> Dict[str, Any]:
    row = await TenantService().get_tenant_config(tenant_id, ANNUAL_TRAINING_PLAN_CONFIG_KEY)
    if not row or not isinstance(row.config_value, dict) or not row.config_value.get("enabled"):
        return {"enabled": False, "line_field_schema": []}
    cfg = copy.deepcopy(row.config_value)
    return {
        "enabled": True,
        "document_code": cfg.get("document_code"),
        "document_title": cfg.get("document_title"),
        "retention_years": cfg.get("retention_years"),
        "approval_slots": cfg.get("approval_slots") or [],
        "line_field_schema": cfg.get("line_field_schema") or [],
        "source_note": cfg.get("source_note"),
    }


async def ensure_electronics_training_templates(
    tenant_id: int, *, user: Optional[User] = None
) -> int:
    created = await _ensure_annual_training_plan_profile(tenant_id)
    for preset in ELECTRONICS_TRAINING_TEMPLATES:
        code = str(preset["template_code"])
        existing = await KuaioaTrainingTemplate.filter(
            tenant_id=tenant_id,
            template_code=code,
            deleted_at__isnull=True,
        ).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                await existing.save()
            continue
        await KuaioaTrainingTemplate.create(
            tenant_id=tenant_id,
            template_code=code,
            template_name=preset["template_name"],
            template_kind=preset["template_kind"],
            content_body=preset.get("content_body"),
            is_active=True,
            notes=preset.get("notes"),
        )
        created += 1
    logger.info(
        "electronics_training_templates_seeded tenant={} created={}",
        tenant_id,
        created,
    )
    return created


async def deactivate_electronics_training_templates(tenant_id: int) -> int:
    await _deactivate_annual_training_plan_profile(tenant_id)
    now = resolve_business_datetime()
    rows = await KuaioaTrainingTemplate.filter(
        tenant_id=tenant_id,
        template_code__in=list(ELECTRONICS_TRAINING_TEMPLATE_CODES),
        deleted_at__isnull=True,
    ).all()
    updated = 0
    for row in rows:
        if row.is_active:
            row.is_active = False
            row.updated_at = now
            await row.save()
            updated += 1
    logger.info(
        "electronics_training_templates_deactivated tenant={} updated={}",
        tenant_id,
        updated,
    )
    return updated
