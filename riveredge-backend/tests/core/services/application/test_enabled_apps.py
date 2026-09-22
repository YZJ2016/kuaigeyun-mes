"""enabled_apps 契约测试。"""

from core.services.application.enabled_apps import (
    expand_requires_apps,
    hidden_app_codes_for_dedicated_shell,
    read_requires_apps_from_manifest,
    union_dedicated_shell_hide_codes,
)


def test_expand_requires_apps_includes_master_data_for_kuaizhizao():
    expanded = expand_requires_apps({"kuaizhizao"})
    assert "master-data" in expanded
    assert "kuaizhizao" in expanded


def test_kuaizhizao_manifest_declares_requires_apps():
    assert "master-data" in read_requires_apps_from_manifest("kuaizhizao")


def test_dedicated_shell_hidden_codes_includes_industry_pack():
    codes = hidden_app_codes_for_dedicated_shell(
        hide=True,
        requires=["kuaiplm", "ind-electronics"],
        consumer_code="funide-oa",
    )
    assert "kuaiplm" in codes
    assert "ind-electronics" in codes
    assert "industry-pack" in codes
    assert "funide-oa" not in codes


def test_dedicated_shell_hidden_codes_off():
    assert (
        hidden_app_codes_for_dedicated_shell(
            hide=False,
            requires=["kuaiplm"],
            consumer_code="funide-oa",
        )
        == []
    )


def test_union_hide_codes_includes_installed_peers():
    codes = union_dedicated_shell_hide_codes(
        required_hidden=["kuaiplm"],
        installed_codes=["kuaiplm", "kuaipd", "kuaicaiwu", "funide-oa"],
        consumer_code="funide-oa",
        system_codes=set(),
    )
    assert "kuaipd" in codes
    assert "kuaicaiwu" in codes
    assert "kuaiplm" in codes
    assert "funide-oa" not in codes


def test_funide_oa_manifest_hides_required_apps_when_composed():
    from core.services.application.enabled_apps import (
        dedicated_shell_hidden_app_codes,
        manifest_hides_required_app_menus,
        read_manifest_data,
    )

    if read_manifest_data("funide-oa") is None:
        return
    assert manifest_hides_required_app_menus("funide-oa")
    hidden = dedicated_shell_hidden_app_codes("funide-oa")
    for code in (
        "kuaiplm",
        "kuaizhizao",
        "kuaiqms",
        "kuaiems",
        "kuaioa",
        "master-data",
        "ind-electronics",
        "industry-pack",
    ):
        assert code in hidden
    assert "funide-oa" not in hidden


def test_haoligo_manifest_hides_required_apps_when_composed():
    from core.services.application.enabled_apps import (
        dedicated_shell_hidden_app_codes,
        manifest_hides_required_app_menus,
        read_manifest_data,
        union_dedicated_shell_hide_codes,
    )

    if read_manifest_data("haoligo") is None:
        return
    assert manifest_hides_required_app_menus("haoligo")
    hidden = dedicated_shell_hidden_app_codes("haoligo")
    for code in ("kuaioa", "kuaizhizao", "master-data"):
        assert code in hidden
    assert "haoligo" not in hidden
    union = union_dedicated_shell_hide_codes(
        required_hidden=hidden,
        installed_codes=["kuaizhizao", "kuaioa", "master-data", "kuaipd", "kuaicaiwu", "haoligo"],
        consumer_code="haoligo",
        system_codes=set(),
    )
    assert "kuaipd" in union
    assert "kuaicaiwu" in union
    assert "haoligo" not in union
