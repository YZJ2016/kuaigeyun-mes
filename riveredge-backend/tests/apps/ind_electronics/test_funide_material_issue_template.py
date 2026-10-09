"""L60 funide_material_issue 预置模板字段契约。"""

from __future__ import annotations

from apps.ind_electronics.seeds.phase1_signoff_templates import FUNIDE_PHASE1_SIGNOFF_TEMPLATES


def test_funide_material_issue_in_phase1_presets():
    by_code = {t["template_code"]: t for t in FUNIDE_PHASE1_SIGNOFF_TEMPLATES}
    assert "funide_material_issue" in by_code
    tpl = by_code["funide_material_issue"]
    assert tpl["business_type"] == "material_issue"
    assert tpl["show_in_menu"] is True
    by_name = {f["name"]: f for f in tpl["fields_schema"]}
    assert by_name["issue_lines"]["type"] == "textarea"
    assert by_name["countersign_user_ids"]["type"] == "user_ids"
    assert by_name["issue_attachment"]["type"] == "file"
