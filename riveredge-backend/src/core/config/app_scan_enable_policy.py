"""应用扫描 / 菜单同步时，基础应用是否默认启用的集中策略。"""

from __future__ import annotations


def should_auto_enable_base_app_after_scan(*, newly_installed: bool) -> bool:
    """
    扫描插件或右下角「同步菜单」触发的 scan：是否应对基础应用调用自动启用。

    - 本轮新安装（含库内已有行但首次自动安装）：True，默认打开。
    - 已安装、仅刷新清单/菜单：False，不得改动用户关闭的启用状态。
    """
    return bool(newly_installed)


__all__ = ["should_auto_enable_base_app_after_scan"]
