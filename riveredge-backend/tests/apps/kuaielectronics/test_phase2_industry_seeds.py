"""第二阶段行业包种子：通用/行业分离。"""

from __future__ import annotations

import json

from apps.kuaielectronics.seeds.annual_supplier_audit_clauses import (
    ELECTRONICS_SUPPLIER_EVAL_ANNUAL_ONSITE_CLAUSE_COUNT,
)
from apps.kuaielectronics.seeds.phase2_templates import (
    ELECTRONICS_ANNUAL_TRAINING_PLAN_PROFILE,
    ELECTRONICS_LICENSE_CATALOG_ITEMS,
    ELECTRONICS_PRODUCTION_DAILY_TEMPLATES,
    ELECTRONICS_PRODUCTION_FILE_CHECKLIST_ITEMS,
    ELECTRONICS_SUPPLIER_AUDIT_PLAN_PROFILE,
    ELECTRONICS_SUPPLIER_EVAL_ANNUAL_ONSITE_TEMPLATE,
    ELECTRONICS_SUPPLIER_EVAL_QUARTERLY_TEMPLATE,
    ELECTRONICS_SUPPLIER_EVAL_TEMPLATE_CODES,
    ELECTRONICS_TRAINING_TEMPLATES,
)
from apps.kuaizhizao.services.production_daily_service import DEFAULT_TEMPLATES


def test_generic_production_daily_has_only_neutral_template():
    codes = {t["template_code"] for t in DEFAULT_TEMPLATES}
    assert codes == {"general_shift"}
    assert "line_daily" not in codes


def test_electronics_production_daily_templates_from_user_xlsx_schema():
    by_code = {t["template_code"]: t for t in ELECTRONICS_PRODUCTION_DAILY_TEMPLATES}
    assert set(by_code) == {"line_daily", "dadp_daily", "exception_daily"}
    line_keys = {f["key"] for f in by_code["line_daily"]["field_schema"]}
    assert "product_model" in line_keys
    assert "daily_completed_qty" in line_keys
    dadp_keys = {f["key"] for f in by_code["dadp_daily"]["field_schema"]}
    assert "da_defect" in dadp_keys and "dp_defect" in dadp_keys


def test_electronics_supplier_eval_quarterly_has_ten_clauses():
    clauses = ELECTRONICS_SUPPLIER_EVAL_QUARTERLY_TEMPLATE["clauses"]
    assert len(clauses) == 10
    assert ELECTRONICS_SUPPLIER_EVAL_QUARTERLY_TEMPLATE["period_type"] == "quarterly"
    joined = " ".join(c["clause_name"] for c in clauses)
    assert "福尼特" not in joined


def test_electronics_supplier_eval_annual_onsite_has_eighty_seven_clauses():
    assert ELECTRONICS_SUPPLIER_EVAL_ANNUAL_ONSITE_CLAUSE_COUNT == 87
    tpl = ELECTRONICS_SUPPLIER_EVAL_ANNUAL_ONSITE_TEMPLATE
    assert tpl["period_type"] == "annual"
    assert len(tpl["clauses"]) == 87
    assert tpl["clauses"][0]["max_score"] == 3
    joined = " ".join(c["clause_name"] for c in tpl["clauses"])
    assert "福尼特" not in joined
    assert "FUNIDE" not in joined


def test_electronics_supplier_eval_template_codes():
    assert ELECTRONICS_SUPPLIER_EVAL_TEMPLATE_CODES == frozenset(
        {"electronics_quarterly_review", "electronics_annual_onsite_audit"}
    )


def test_electronics_production_file_checklist_has_thirteen_items():
    assert len(ELECTRONICS_PRODUCTION_FILE_CHECKLIST_ITEMS) == 13
    joined = json.dumps(ELECTRONICS_PRODUCTION_FILE_CHECKLIST_ITEMS, ensure_ascii=False)
    assert "王益鹏" not in joined
    assert "陈明军" not in joined
    rd_items = [
        x for x in ELECTRONICS_PRODUCTION_FILE_CHECKLIST_ITEMS if x.get("catalog_kind") == "rd_tool"
    ]
    assert len(rd_items) == 1
    assert "rd_burn_tool" in rd_items[0]["file_types"]


def test_electronics_license_catalog_has_fifteen_items():
    assert len(ELECTRONICS_LICENSE_CATALOG_ITEMS) == 15
    codes = {x["license_type"] for x in ELECTRONICS_LICENSE_CATALOG_ITEMS}
    assert "hygiene_permit" in codes
    joined = " ".join(x["item_name"] for x in ELECTRONICS_LICENSE_CATALOG_ITEMS)
    assert "包洁敏" not in joined


def test_electronics_training_templates_json_valid():
    by_code = {t["template_code"]: t for t in ELECTRONICS_TRAINING_TEMPLATES}
    assert set(by_code) == {
        "electronics_work_license",
        "electronics_esd_exam_initial",
        "electronics_esd_exam_periodic",
    }
    for tpl in ELECTRONICS_TRAINING_TEMPLATES:
        json.loads(tpl["content_body"])


def test_calibration_notify_preset_ids():
    from apps.kuaizhizao.services.kuaizhizao_notification_rule_presets import (
        CALIBRATION_NOTIFICATION_PRESET_IDS,
    )

    assert CALIBRATION_NOTIFICATION_PRESET_IDS == frozenset(
        {
            "kz_preset_equipment_calibration_due_soon",
            "kz_preset_equipment_calibration_due_overdue",
        }
    )


def test_electronics_annual_training_plan_profile_from_pdf_header():
    schema = ELECTRONICS_ANNUAL_TRAINING_PLAN_PROFILE["line_field_schema"]
    keys = {f["key"] for f in schema}
    assert ELECTRONICS_ANNUAL_TRAINING_PLAN_PROFILE["document_code"] == "FND/R-04-01"
    assert ELECTRONICS_ANNUAL_TRAINING_PLAN_PROFILE["retention_years"] == 3
    assert keys == {
        "line_no",
        "trainee_target",
        "training_content",
        "training_department",
        "owner_name",
        "due_date",
        "training_method",
        "evaluation_method",
        "remarks",
    }


def test_electronics_supplier_audit_plan_profile_schedule():
    profile = ELECTRONICS_SUPPLIER_AUDIT_PLAN_PROFILE
    assert profile["default_audit_mode"] == "onsite"
    assert profile["default_template_code"] == "electronics_annual_onsite_audit"
    assert len(profile["month_tracking"]["months"]) == 12
    assert len(profile["line_fields"]) == 6
    assert profile["quarterly_review_summary"]["title"] == "年供应商季度评审汇总表"


def test_calibration_default_notify_channels_internal_only():
    from apps.kuaizhizao.constants.equipment_calibration_settings import (
        DEFAULT_CALIBRATION_NOTIFY_CHANNELS,
    )

    assert DEFAULT_CALIBRATION_NOTIFY_CHANNELS == ("internal",)
