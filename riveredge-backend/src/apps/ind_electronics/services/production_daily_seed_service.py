"""R-13 生产日报行业预置：启用电子包时写入三类日报模板。"""

from __future__ import annotations

from typing import Any, Optional

from loguru import logger

from apps.common.audit_actor import apply_create_audit
from apps.ind_electronics.seeds.phase2_templates import (
    ELECTRONICS_PRODUCTION_DAILY_TEMPLATE_CODES,
    ELECTRONICS_PRODUCTION_DAILY_TEMPLATES,
)
from apps.kuaizhizao.models.production_daily import ProductionDailyTemplate
from apps.kuaizhizao.services.production_daily_service import _normalize_field_schema
from core.utils.timezone_utils import resolve_business_datetime
from infra.models.user import User


async def ensure_electronics_production_daily_templates(
    tenant_id: int, *, user: Optional[User] = None
) -> int:
    created = 0
    for preset in ELECTRONICS_PRODUCTION_DAILY_TEMPLATES:
        code = str(preset["template_code"])
        existing = await ProductionDailyTemplate.filter(
            tenant_id=tenant_id,
            template_code=code,
            deleted_at__isnull=True,
        ).first()
        if existing:
            if not existing.is_active and existing.is_system:
                existing.is_active = True
                await existing.save()
            continue
        payload: dict[str, Any] = {
            "tenant_id": tenant_id,
            "template_code": code,
            "template_name": preset["template_name"],
            "description": preset.get("description"),
            "field_schema": _normalize_field_schema(preset.get("field_schema") or []),
            "sort_order": int(preset.get("sort_order") or 0),
            "is_active": True,
            "is_system": True,
        }
        if user is not None:
            apply_create_audit(payload, user)
        await ProductionDailyTemplate.create(**payload)
        created += 1
    logger.info(
        "electronics_production_daily_seeded tenant={} created={}",
        tenant_id,
        created,
    )
    return created


async def deactivate_electronics_production_daily_templates(tenant_id: int) -> int:
    """停用行业包：停用预置模板，不删历史日报。"""
    now = resolve_business_datetime()
    rows = await ProductionDailyTemplate.filter(
        tenant_id=tenant_id,
        template_code__in=list(ELECTRONICS_PRODUCTION_DAILY_TEMPLATE_CODES),
        deleted_at__isnull=True,
        is_system=True,
    ).all()
    updated = 0
    for row in rows:
        if row.is_active:
            row.is_active = False
            row.updated_at = now
            await row.save()
            updated += 1
    logger.info(
        "electronics_production_daily_deactivated tenant={} updated={}",
        tenant_id,
        updated,
    )
    return updated
