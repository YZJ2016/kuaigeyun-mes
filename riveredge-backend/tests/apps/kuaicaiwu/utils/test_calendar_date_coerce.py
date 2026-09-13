"""日历日 API 归一化。"""

from datetime import date, datetime

from apps.kuaicaiwu.utils.calendar_date_coerce import coerce_api_calendar_date


def test_coerce_from_datetime():
    assert coerce_api_calendar_date(datetime(2026, 9, 12, 15, 30, 0)) == date(2026, 9, 12)


def test_coerce_from_iso_string():
    assert coerce_api_calendar_date("2026-09-12T08:00:00") == date(2026, 9, 12)
    assert coerce_api_calendar_date("2026-09-18 00:00:00") == date(2026, 9, 18)
