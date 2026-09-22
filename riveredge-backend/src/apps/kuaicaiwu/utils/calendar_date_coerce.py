"""API 日历日字段归一化（date 型入参，禁止带非零时刻的 datetime）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def coerce_api_calendar_date(value: Any) -> Any:
    if value is None or value == "":
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return value
        if "T" in text:
            text = text.split("T", 1)[0]
        elif " " in text:
            text = text.split(" ", 1)[0]
        return date.fromisoformat(text[:10])
    return value
