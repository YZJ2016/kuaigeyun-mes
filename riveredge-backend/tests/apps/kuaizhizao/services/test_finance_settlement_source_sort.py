from datetime import date

from apps.kuaicaiwu.services.finance_settlement_hierarchy import (
    _coerce_hierarchy_sort_date,
)
from apps.kuaizhizao.services.finance_settlement_source_query import (
    _in_date_range,
    _line_sort_key,
)


def test_line_sort_key_mixed_str_and_date():
    rows = [
        {"sort_date": date(2026, 11, 17), "doc_type": "采购入库", "doc_id": 1},
        {"date": "2026-11-15", "doc_type": "委外收货", "doc_id": 2},
        {"sort_date": "2026-11-16", "doc_type": "采购入库", "doc_id": 3},
    ]
    rows.sort(key=_line_sort_key)
    assert [r["doc_id"] for r in rows] == [2, 3, 1]


def test_in_date_range_accepts_str_bounds():
    assert _in_date_range(date(2026, 11, 17), "2026-11-01", "2026-11-30") is True
    assert _in_date_range("2026-11-17", date(2026, 11, 1), date(2026, 11, 30)) is True


def test_hierarchy_coerce_mixed():
    assert _coerce_hierarchy_sort_date(date(2026, 11, 1)) == date(2026, 11, 1)
    assert _coerce_hierarchy_sort_date("2026-11-01") == date(2026, 11, 1)
