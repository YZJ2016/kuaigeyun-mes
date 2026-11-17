"""取单（上拉）来源单据日期筛选 — 站点日历日口径。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal, Optional

from core.utils.timezone_utils import site_day_bounds_utc

PullQueryDateFieldKind = Literal["date", "datetime"]


def apply_pull_query_document_date_filter(
    query: Any,
    *,
    field: str,
    kind: PullQueryDateFieldKind = "date",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> Any:
    """在 Tortoise QuerySet 上按来源单据业务日期收窄候选头表。"""
    if date_from is None and date_to is None:
        return query
    if kind == "date":
        if date_from is not None:
            query = query.filter(**{f"{field}__gte": date_from})
        if date_to is not None:
            query = query.filter(**{f"{field}__lte": date_to})
        return query
    if date_from is not None:
        start_utc, _ = site_day_bounds_utc(date_from)
        query = query.filter(**{f"{field}__gte": start_utc})
    if date_to is not None:
        _, end_exclusive = site_day_bounds_utc(date_to + timedelta(days=1))
        query = query.filter(**{f"{field}__lt": end_exclusive})
    return query
