"""仿真模式：真实验收 vs 快速填数（配置隔离，禁止互殴）。"""

from __future__ import annotations

from typing import Literal

SimMode = Literal["real", "fill"]


def normalize_sim_mode(raw: str | None) -> SimMode:
    text = (raw or "real").strip().lower()
    if text in ("fill", "fast", "demo", "填数", "快速填数"):
        return "fill"
    return "real"


def is_budget_time_allowed(mode: SimMode) -> bool:
    """仅填数模式允许 flow_end_at 时间窗压缩。"""
    return mode == "fill"


def is_force_simple_allowed(mode: SimMode) -> bool:
    """强制简易质检：真实/填数均默认禁止（与调用点 force_simple_when_unset=False 一致）。

    填数若将来要开简易，须另加显式请求字段，禁止靠 mode 暗示。
    """
    _ = mode
    return False


def is_allow_skip_iqc_effective(mode: SimMode, requested: bool) -> bool:
    """真实模式忽略 allow_skip_iqc。"""
    if mode == "real":
        return False
    return bool(requested)
