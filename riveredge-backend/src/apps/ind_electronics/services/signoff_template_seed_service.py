"""Funide 通用会签表单预置写入轻办公表单模板。

真源：seeds/phase1_signoff_templates.py（5M 变更、物料申请、样品检验等）。
导航树挂「自定义审批」前 ensure，避免租户缺模板或字段落后于 seed。
"""

from __future__ import annotations

from apps.ind_electronics.seeds.phase1_signoff_templates import (
    FUNIDE_PHASE1_SIGNOFF_TEMPLATES,
    FUNIDE_PHASE1_SIGNOFF_TEMPLATE_CODES,
)
from apps.kuaioa.models.form_template import KuaioaFormTemplate
from apps.kuaioa.services.form_schema_validator import normalize_fields_schema

# 兼容旧引用：与 Phase1 全会签模板集合一致
PROJECT_SIGNOFF_TEMPLATE_CODES = FUNIDE_PHASE1_SIGNOFF_TEMPLATE_CODES


async def ensure_project_signoff_templates(tenant_id: int) -> None:
    presets = list(FUNIDE_PHASE1_SIGNOFF_TEMPLATES)
    for item in presets:
        code = str(item["template_code"])
        schema = normalize_fields_schema(item.get("fields_schema"))
        row = await KuaioaFormTemplate.filter(
            tenant_id=tenant_id,
            template_code=code,
            deleted_at__isnull=True,
        ).first()
        if row is None:
            await KuaioaFormTemplate.create(
                tenant_id=tenant_id,
                template_code=code,
                template_name=str(item["template_name"]),
                category=str(item.get("category") or "general_signoff"),
                business_type=str(item.get("business_type") or "") or None,
                description=item.get("description"),
                fields_schema=schema,
                is_active=True,
                show_in_menu=bool(item.get("show_in_menu")),
            )
            continue
        business_type = str(item.get("business_type") or "") or None
        show_in_menu = bool(item.get("show_in_menu"))
        unchanged = (
            row.template_name == str(item["template_name"])
            and row.business_type == business_type
            and row.fields_schema == schema
            and row.is_active is True
            and row.show_in_menu is show_in_menu
        )
        if unchanged:
            continue
        row.template_name = str(item["template_name"])
        row.category = str(item.get("category") or row.category)
        row.business_type = business_type
        row.description = item.get("description")
        row.fields_schema = schema
        row.is_active = True
        row.show_in_menu = show_in_menu
        await row.save()
