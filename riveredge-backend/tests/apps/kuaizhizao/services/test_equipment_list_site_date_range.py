"""列表筛选：站点日历日边界须与 site_day_bounds_utc 对齐。"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from apps.kuaizhizao.services.equipment_list_core import _apply_site_calendar_day_range
from core.utils.timezone_utils import site_day_bounds_utc, site_timezone_name, to_naive_utc
from zoneinfo import ZoneInfo


class _FakeQuery:
    def __init__(self) -> None:
        self.filters: list[tuple] = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self


def test_apply_site_calendar_day_range_uses_site_bounds_utc():
  start_day = date(2025, 11, 26)
  end_day = date(2025, 11, 27)
  q = _FakeQuery()
  _apply_site_calendar_day_range(
      q, field="created_at", start=start_day, end=end_day
  )
  from datetime import timedelta

  start_utc, _ = site_day_bounds_utc(start_day)
  _, end_plus = site_day_bounds_utc(end_day + timedelta(days=1))
  assert q.filters == [
      {"created_at__gte": to_naive_utc(start_utc)},
      {"created_at__lt": to_naive_utc(end_plus)},
  ]
  tz = ZoneInfo(site_timezone_name())
  assert start_utc.astimezone(tz).date() == start_day


@pytest.mark.parametrize(
    "field",
    ["receipt_time", "created_at", "updated_at"],
)
def test_apply_site_calendar_end_includes_full_last_day(field: str):
  day = date(2025, 11, 20)
  q = _FakeQuery()
  _apply_site_calendar_day_range(q, field=field, start=day, end=day)
  from datetime import timedelta

  _, end_plus = site_day_bounds_utc(day + timedelta(days=1))
  assert q.filters[-1] == {f"{field}__lt": to_naive_utc(end_plus)}
  # 站点当日 23:59 应落在区间内
  tz = ZoneInfo(site_timezone_name())
  late = datetime(day.year, day.month, day.day, 23, 59, 0, tzinfo=tz).astimezone(
      timezone.utc
  )
  assert to_naive_utc(end_plus) > to_naive_utc(late)