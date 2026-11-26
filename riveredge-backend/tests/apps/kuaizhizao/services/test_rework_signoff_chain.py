from apps.kuaizhizao.constants.rework_signoff_chain import (
    SIGNOFF_CHAIN_VERSION_V2,
    chain_for_path,
    chain_version_from_flow,
    node_label,
)


def test_aa_chain_v2_matches_whiteboard():
    keys = [code for code, _name in chain_for_path("aa", chain_version=SIGNOFF_CHAIN_VERSION_V2)]
    assert keys == [
        "sales",
        "quality",
        "ie_engineering",
        "position_review",
        "purchasing",
        "leader",
        "planning",
        "rework_exec",
        "manufacturing_exec",
        "finance",
    ]


def test_ab_chain_v2_inserts_rd_after_sales():
    keys = [code for code, _name in chain_for_path("ab", chain_version=SIGNOFF_CHAIN_VERSION_V2)]
    assert keys[0:3] == ["sales", "rd", "quality"]
    assert "ie_engineering" in keys
    assert "rework_exec" in keys
    assert "leader" in keys


def test_aa_chain_v1_legacy():
    keys = [code for code, _name in chain_for_path("aa", chain_version=1)]
    assert "manufacturing" in keys
    assert "warehouse" in keys
    assert "ie_engineering" not in keys


def test_chain_version_legacy_flow_defaults_v1():
    assert chain_version_from_flow({"current_node_key": "quality"}) == 1
    assert chain_version_from_flow({"chain_version": 2}) == 2


def test_v2_node_labels_match_whiteboard():
    assert node_label("aa", "quality", chain_version=SIGNOFF_CHAIN_VERSION_V2) == "返工需求提出"
    assert (
        node_label("aa", "ie_engineering", chain_version=SIGNOFF_CHAIN_VERSION_V2)
        == "返工排位策划"
    )
    assert node_label("aa", "planning", chain_version=SIGNOFF_CHAIN_VERSION_V2) == "计划排产"
    assert node_label("aa", "purchasing", chain_version=SIGNOFF_CHAIN_VERSION_V2) == "材料采购"