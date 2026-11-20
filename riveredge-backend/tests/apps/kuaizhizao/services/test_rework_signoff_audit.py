from apps.kuaizhizao.constants.rework_signoff_audit import (
    SIGNOFF_AUDIT_SKIP_DEPT_CODES,
    signoff_audit_manifest_business_type,
    signoff_audit_node_key,
)


def test_signoff_audit_node_keys():
    assert signoff_audit_node_key("quality") == "rework_signoff_quality"
    assert signoff_audit_manifest_business_type("leader") == "signoff_node_leader"
    assert "sales" in SIGNOFF_AUDIT_SKIP_DEPT_CODES