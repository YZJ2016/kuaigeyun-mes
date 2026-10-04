"""项目确认书、评审单行业预置写入轻办公表单模板。

真源：seeds/phase1_signoff_templates.py 中 funide_confirmation、funide_review_sheet。
导航挂出「自定义审批」前按模板编码写入或对齐字段，避免手填评审类型。
"""

from __future__ import annotations

from apps.ind_electronics.seeds.phase1_signoff_templates import FUNIDE_PHASE1_SIGNOFF_TEMPLATES
from apps.kuaioa.models.form_template import KuaioaFormTemplate
from apps.kuaioa.services.form_schema_validator import normalize_fields_schema

PROJECT_SIGNOFF_TEMPLATE_CODES = frozenset({"funide_confirmation", "funide_review_sheet"})


async def ensure_project_signoff_templates(tenant_id: int) -> None:
    presets = [
        item
        for item in FUNIDE_PHASE1_SIGNOFF_TEMPLATES
        if item.get("template_code") in PROJECT_SIGNOFF_TEMPLATE_CODES
    ]
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
