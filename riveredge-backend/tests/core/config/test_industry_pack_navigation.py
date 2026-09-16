from core.config.industry_pack import (
    INDUSTRY_PACK_APP_CODE,
    _collect_extension_pack_menu_children,
    is_industry_module_app_code,
    is_industry_pack_shell_code,
    manifest_to_industry_pack_menu_item,
    resolve_industry_pack_navigation_visible,
)


def test_resolve_industry_pack_navigation_visible_requires_active_modules() -> None:
    assert resolve_industry_pack_navigation_visible(
        is_installed=True,
        active_module_count=0,
    ) is False
    assert resolve_industry_pack_navigation_visible(
        is_installed=True,
        active_module_count=1,
    ) is True
    assert resolve_industry_pack_navigation_visible(
        is_installed=False,
        active_module_count=1,
    ) is False


def test_manifest_module_group_has_no_path_when_children_exist() -> None:
    item = manifest_to_industry_pack_menu_item(
        {
            "code": "kuaielectronics",
            "route_path": "/apps/kuaielectronics",
            "icon": "cpu",
            "sort_order": 310,
            "industry_pack_menu": {
                "children": [
                    {
                        "title": "app.kuaielectronics.menu.esdDashboard",
                        "path": "/apps/kuaielectronics/esd/dashboard",
                        "permission": "kuaielectronics:esd:read",
                        "sort_order": 1,
                    }
                ]
            },
        }
    )
    assert item is not None
    assert item["path"] is None
    assert item["icon"] == "cpu"
    assert item["title"] == "app.kuaielectronics.name"
    assert item["children"][0]["path"] == "/apps/kuaielectronics/esd/dashboard"


def test_extension_pack_menu_children_from_replace_declarations():
    manifest = {
        "code": "kuaielectronics",
        "industry_extensions": [
            {
                "id": "electronics.sample_process",
                "kind": "replace",
                "strategy": "profile",
                "host_app": "kuaiplm",
                "menu_path": "/apps/kuaiplm/sample-process-applications",
                "resource": "kuaiplm:sample-process",
                "profile_key": "kuaiplm.sample_process",
                "menu_sort_order": 10,
                "pack_menu": False,
            },
            {
                "id": "electronics.label_oem",
                "kind": "replace",
                "strategy": "document",
                "host_app": "kuaizhizao",
                "menu_path": "/apps/kuaizhizao/production-execution/label-station",
                "resource": "kuaizhizao:label-station",
                "replacement_app": "kuaielectronics",
                "replacement_path": "/apps/kuaielectronics/label-oem",
                "menu_title": "app.kuaielectronics.menu.labelOem",
                "menu_sort_order": 60,
            },
            {"id": "electronics.esd", "kind": "standalone"},
        ],
    }
    children = _collect_extension_pack_menu_children(manifest)
    assert len(children) == 1
    assert children[0]["path"] == "/apps/kuaielectronics/label-oem"
    assert children[0]["title"] == "app.kuaielectronics.menu.labelOem"


def test_manifest_merges_extension_and_manual_pack_menu():
    item = manifest_to_industry_pack_menu_item(
        {
            "code": "kuaielectronics",
            "route_path": "/apps/kuaielectronics",
            "icon": "cpu",
            "sort_order": 310,
            "industry_pack_menu": {
                "children": [
                    {
                        "title": "app.kuaielectronics.menu.esdDashboard",
                        "path": "/apps/kuaielectronics/esd/dashboard",
                        "permission": "kuaielectronics:esd:read",
                        "sort_order": 70,
                    }
                ]
            },
            "industry_extensions": [
                {
                    "id": "electronics.trial_flow_steps",
                    "kind": "replace",
                    "strategy": "profile",
                    "host_app": "kuaiplm",
                    "menu_path": "/apps/kuaiplm/trial-flows",
                    "resource": "kuaiplm:trial-flow",
                    "profile_key": "kuaiplm.trial_flow",
                    "menu_sort_order": 40,
                    "pack_menu": False,
                },
                {
                    "id": "electronics.label_oem",
                    "kind": "replace",
                    "strategy": "document",
                    "host_app": "kuaizhizao",
                    "menu_path": "/apps/kuaizhizao/production-execution/label-station",
                    "resource": "kuaizhizao:label-station",
                    "replacement_app": "kuaielectronics",
                    "replacement_path": "/apps/kuaielectronics/label-oem",
                    "menu_title": "app.kuaielectronics.menu.labelOem",
                    "menu_sort_order": 60,
                },
            ],
        }
    )
    assert item is not None
    paths = [child["path"] for child in item["children"]]
    assert "/apps/kuaiplm/trial-flows" not in paths
    assert "/apps/kuaielectronics/esd/dashboard" in paths
    assert "/apps/kuaielectronics/label-oem" in paths
    assert paths.index("/apps/kuaielectronics/label-oem") < paths.index(
        "/apps/kuaielectronics/esd/dashboard"
    )
