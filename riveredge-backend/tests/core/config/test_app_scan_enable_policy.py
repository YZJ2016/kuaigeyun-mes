"""应用扫描时基础应用自动启用策略。"""

from core.config.app_scan_enable_policy import should_auto_enable_base_app_after_scan


def test_should_auto_enable_only_when_newly_installed():
    assert should_auto_enable_base_app_after_scan(newly_installed=True) is True
    assert should_auto_enable_base_app_after_scan(newly_installed=False) is False
