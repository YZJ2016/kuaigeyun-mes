from datetime import datetime, timezone

from apps.kuaizhizao.utils.inbound_confirm_helper import resolve_stock_restore_ledger_production_date


def test_resolve_stock_restore_ledger_production_date_prefers_line_time():
    line = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
    header = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    got = resolve_stock_restore_ledger_production_date(line_time=line, header_time=header)
    assert got.year == 2026 and got.month == 3 and got.day == 15


def test_resolve_stock_restore_ledger_production_date_fallback_when_all_empty():
    got = resolve_stock_restore_ledger_production_date()
    assert got is not None