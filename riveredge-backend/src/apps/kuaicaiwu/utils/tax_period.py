"""业财宿主：税务属期字符串（不依赖轻财务 Pro tax 包）。"""

from __future__ import annotations

from datetime import date


def tax_period_from_date(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"
