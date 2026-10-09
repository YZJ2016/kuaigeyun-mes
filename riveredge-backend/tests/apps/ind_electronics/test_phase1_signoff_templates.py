"""Phase1 通用会签 seed 与 L47 5M 字段契约。"""

from __future__ import annotations

from apps.ind_electronics.seeds.phase1_signoff_templates import (
    FUNIDE_PHASE1_SIGNOFF_TEMPLATES,
    FUNIDE_PHASE1_SIGNOFF_TEMPLATE_CODES,
)
from apps.ind_electronics.services.signoff_template_seed_service import (
    PROJECT_SIGNOFF_TEMPLATE_CODES,
)


def test_phase1_signoff_template_codes_cover_all_presets():
    codes = {t["template_code"] for t in FUNIDE_PHASE1_SIGNOFF_TEMPLATES}
    assert codes == FUNIDE_PHASE1_SIGNOFF_TEMPLATE_CODES
    assert PROJECT_SIGNOFF_TEMPLATE_CODES == FUNIDE_PHASE1_SIGNOFF_TEMPLATE_CODES
    assert "funide_five_m_change" in codes


def test_funide_five_m_change_has_version_compare_file_field():
    by_code = {t["template_code"]: t for t in FUNIDE_PHASE1_SIGNOFF_TEMPLATES}
    schema = by_code["funide_five_m_change"]["fields_schema"]
    by_name = {f["name"]: f for f in schema}
    assert by_name["version_compare_file"]["type"] == "file"
    assert by_name["version_compare_file"]["required"] is True
    assert by_name["trial_report_file"]["type"] == "file"


def test_funide_material_request_has_code_and_attachment_fields():
    by_code = {t["template_code"]: t for t in FUNIDE_PHASE1_SIGNOFF_TEMPLATES}
    schema = by_code["funide_material_request"]["fields_schema"]
    by_name = {f["name"]: f for f in schema}
    assert by_name["material_code"]["type"] == "text"
    assert by_name["material_code"]["required"] is True
    assert by_name["application_form_file"]["type"] == "file"
    assert by_name["application_form_file"]["required"] is False


def test_funide_sample_inspection_has_form_attachment_field():
    by_code = {t["template_code"]: t for t in FUNIDE_PHASE1_SIGNOFF_TEMPLATES}
    schema = by_code["funide_sample_inspection"]["fields_schema"]
    by_name = {f["name"]: f for f in schema}
    assert by_name["inspection_form_file"]["type"] == "file"
    assert by_name["inspection_form_file"]["required"] is False
    assert by_name["material_code"]["required"] is True
