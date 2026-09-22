from apps.kuaizhizao.utils.issue_method_resolver import (
    is_pick_list_material,
    resolve_issue_method,
)


def test_resolve_issue_method_honors_explicit_pick_on_buy():
    assert resolve_issue_method("pick", "Buy") == "pick"


def test_resolve_issue_method_honors_explicit_backflush_on_buy():
    assert resolve_issue_method("backflush", "Buy") == "backflush"
    assert is_pick_list_material("backflush", "Buy") is False


def test_resolve_issue_method_defaults_buy_without_bom_line_to_pick():
    assert resolve_issue_method(None, "Buy") == "pick"
    assert resolve_issue_method("", "Buy") == "pick"


def test_resolve_issue_method_phantom_service_default_none():
    assert resolve_issue_method(None, "Phantom") == "none"
    assert resolve_issue_method(None, "Service") == "none"


def test_is_pick_list_material_for_buy_without_explicit_issue_method():
    assert is_pick_list_material(None, "Buy") is True
