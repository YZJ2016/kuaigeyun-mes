"""R-03 供应商评价行业预置：供方季度复审 + 年度现场审核模板。"""

from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any, Dict, Optional

from loguru import logger

from apps.common.audit_actor import apply_create_audit
from apps.kuaielectronics.seeds.phase2_templates import (
    ELECTRONICS_SUPPLIER_AUDIT_PLAN_PROFILE,
    ELECTRONICS_SUPPLIER_EVAL_ANNUAL_ONSITE_TEMPLATE,
    ELECTRONICS_SUPPLIER_EVAL_QUARTERLY_TEMPLATE,
    ELECTRONICS_SUPPLIER_EVAL_TEMPLATE_CODES,
    SUPPLIER_AUDIT_PLAN_CONFIG_KEY,
)
from apps.kuaizhizao.models.supplier_evaluation import (
    SupplierEvalTemplate,
    SupplierEvalTemplateClause,
)
from core.utils.timezone_utils import resolve_business_datetime
from infra.models.tenant_config import TenantConfig
from infra.models.user import User
from infra.services.tenant_service import TenantService

_SEED_REMARKS = {
    ELECTRONICS_SUPPLIER_EVAL_QUARTERLY_TEMPLATE["code"]: (
        "电子制造行业包预置（真源 质量部/供方季度评价表.xlsx）"
    ),
    ELECTRONICS_SUPPLIER_EVAL_ANNUAL_ONSITE_TEMPLATE["code"]: (
        "电子制造行业包预置（真源 质量部/供方年度评价表.xls 审核项目，0-3 分）"
    ),
}


async def _ensure_one_supplier_eval_template(
    tenant_id: int, seed: dict[str, Any], *, user: Optional[User] = None
) -> int:
    code = str(seed["code"])
    existing = await SupplierEvalTemplate.filter(
        tenant_id=tenant_id,
        code=code,
        deleted_at__isnull=True,
    ).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            await existing.save()
        return 0

    payload = {
        "tenant_id": tenant_id,
        "code": code,
        "name": seed["name"],
        "version": seed.get("version") or "v1",
        "grade_version": seed.get("grade_version") or "v1",
        "grade_bands": seed.get("grade_bands") or [],
        "period_type": seed.get("period_type"),
        "is_active": True,
        "remarks": _SEED_REMARKS.get(code, "电子制造行业包预置"),
    }
    if user is not None:
        apply_create_audit(payload, user)
    row = await SupplierEvalTemplate.create(**payload)

    for raw in seed.get("clauses") or []:
        clause = SupplierEvalTemplateClause(
            tenant_id=tenant_id,
            template_id=row.id,
            line_no=int(raw.get("line_no") or 1),
            clause_code=str(raw["clause_code"]),
            clause_name=str(raw["clause_name"]),
            weight=Decimal(str(raw.get("weight") or 1)),
            max_score=Decimal(str(raw.get("max_score") or 10)),
            remarks=(raw.get("remarks") or None),
        )
        if user is not None:
            apply_create_audit(clause, user)
        await clause.save()

    logger.info("electronics_supplier_eval_seeded tenant={} template_id={} code={}", tenant_id, row.id, code)
    return 1


async def _ensure_supplier_audit_plan_profile(tenant_id: int) -> int:
    existing = await TenantConfig.filter(
        tenant_id=tenant_id, config_key=SUPPLIER_AUDIT_PLAN_CONFIG_KEY
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
        "extension_id": "electronics.supplier_eval",
        "module_app_code": "kuaielectronics",
        **copy.deepcopy(ELECTRONICS_SUPPLIER_AUDIT_PLAN_PROFILE),
        "source_note": "真源 质量部/供方年度审核计划.xls 供应商监督审核计划",
    }
    await TenantService().set_tenant_config(
        tenant_id,
        SUPPLIER_AUDIT_PLAN_CONFIG_KEY,
        payload,
        description="行业扩展：供方年度监督审核计划排程对照",
    )
    return 1


async def _deactivate_supplier_audit_plan_profile(tenant_id: int) -> int:
    row = await TenantConfig.filter(
        tenant_id=tenant_id, config_key=SUPPLIER_AUDIT_PLAN_CONFIG_KEY
    ).first()
    if not row:
        return 0
    await row.delete()
    return 1


async def get_supplier_audit_plan_guide_summary(tenant_id: int) -> Dict[str, Any]:
    row = await TenantService().get_tenant_config(tenant_id, SUPPLIER_AUDIT_PLAN_CONFIG_KEY)
    if not row or not isinstance(row.config_value, dict) or not row.config_value.get("enabled"):
        return {"enabled": False}
    cfg = copy.deepcopy(row.config_value)
    return {
        "enabled": True,
        "plan_name_pattern": cfg.get("plan_name_pattern"),
        "period_type": cfg.get("period_type"),
        "default_audit_mode": cfg.get("default_audit_mode"),
        "default_template_code": cfg.get("default_template_code"),
        "line_fields": cfg.get("line_fields") or [],
        "month_tracking": cfg.get("month_tracking"),
        "quarterly_review_summary": cfg.get("quarterly_review_summary"),
        "source_note": cfg.get("source_note"),
    }


async def ensure_electronics_supplier_eval_templates(
    tenant_id: int, *, user: Optional[User] = None
) -> int:
    created = await _ensure_supplier_audit_plan_profile(tenant_id)
    for seed in (
        ELECTRONICS_SUPPLIER_EVAL_QUARTERLY_TEMPLATE,
        ELECTRONICS_SUPPLIER_EVAL_ANNUAL_ONSITE_TEMPLATE,
    ):
        created += await _ensure_one_supplier_eval_template(tenant_id, seed, user=user)
    return created


async def deactivate_electronics_supplier_eval_templates(tenant_id: int) -> int:
    await _deactivate_supplier_audit_plan_profile(tenant_id)
    now = resolve_business_datetime()
    rows = await SupplierEvalTemplate.filter(
        tenant_id=tenant_id,
        code__in=list(ELECTRONICS_SUPPLIER_EVAL_TEMPLATE_CODES),
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
        "electronics_supplier_eval_deactivated tenant={} updated={}",
        tenant_id,
        updated,
    )
    return updated
