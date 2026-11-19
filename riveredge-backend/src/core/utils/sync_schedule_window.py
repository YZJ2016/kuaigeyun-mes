"""入站定时同步允许时段（站点墙钟 HH:mm）。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional, Tuple

from infra.exceptions.exceptions import ValidationError

from core.utils.timezone_utils import resolve_business_datetime, to_site_timezone

_TIME_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _schedule_window_minutes(hhmm: str) -> int:
    text = (hhmm or "").strip()
    matched = _TIME_HHMM_RE.match(text)
    if not matched:
        raise ValidationError("允许同步时段须为 HH:mm 格式（00:00～23:59）")
    return int(matched.group(1)) * 60 + int(matched.group(2))


def normalize_schedule_window(
    start: Optional[str],
    end: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    start_s = (start or "").strip() or None
    end_s = (end or "").strip() or None
    if not start_s and not end_s:
        return None, None
    if not start_s or not end_s:
        raise ValidationError("允许同步时段须同时设置开始与结束，或留空表示全天")
    _schedule_window_minutes(start_s)
    _schedule_window_minutes(end_s)
    if start_s == end_s:
        raise ValidationError("允许同步时段开始与结束不能相同")
    return start_s, end_s


def resolve_schedule_window_for_upsert(
    body: Any,
    existing: Optional[Any],
) -> Tuple[Optional[str], Optional[str]]:
    fields_set = getattr(body, "model_fields_set", None) or set()
    if "schedule_window_start" in fields_set or "schedule_window_end" in fields_set:
        return normalize_schedule_window(
            getattr(body, "schedule_window_start", None),
            getattr(body, "schedule_window_end", None),
        )
    if existing:
        return (
            getattr(existing, "schedule_window_start", None),
            getattr(existing, "schedule_window_end", None),
        )
    return None, None


def resolve_schedule_window_for_sync_request(
    req: Any,
    binding: Optional[Any],
) -> Tuple[Optional[str], Optional[str]]:
    fields_set = getattr(req, "model_fields_set", None) or set()
    if "schedule_window_start" in fields_set or "schedule_window_end" in fields_set:
        return normalize_schedule_window(
            getattr(req, "schedule_window_start", None),
            getattr(req, "schedule_window_end", None),
        )
    if binding:
        return (
            getattr(binding, "schedule_window_start", None),
            getattr(binding, "schedule_window_end", None),
        )
    return None, None


def is_within_schedule_window(
    binding: Any,
    *,
    now: Optional[datetime] = None,
) -> bool:
    start_s = (getattr(binding, "schedule_window_start", None) or "").strip() or None
    end_s = (getattr(binding, "schedule_window_end", None) or "").strip() or None
    if not start_s and not end_s:
        return True
    if not start_s or not end_s:
        return True

    dt = now or resolve_business_datetime()
    site = to_site_timezone(dt)
    current = site.hour * 60 + site.minute
    start_m = _schedule_window_minutes(start_s)
    end_m = _schedule_window_minutes(end_s)
    if start_m < end_m:
        return start_m <= current < end_m
    return current >= start_m or current < end_m
