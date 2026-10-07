from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from apps.kuaizhizao.services.oee_calculator import calculate_oee


def test_oee_uses_maintained_cycle_and_all_three_factors():
    start = datetime(2026, 10, 7, tzinfo=timezone.utc)
    rows = [SimpleNamespace(monitored_at=start + timedelta(seconds=s), status="运行中", id=s) for s in range(0, 3600, 60)]
    result = calculate_oee(rows, start, start + timedelta(hours=1), {"ideal_cycle_seconds": 30, "planned_windows": [{"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat()}]}, 60, 54)
    assert result["availability_rate"] == 1
    assert result["performance_rate"] == 0.5
    assert result["quality_rate"] == 0.9
    assert result["oee"] == 0.45


def test_missing_inputs_and_collection_gap_do_not_manufacture_oee():
    start = datetime(2026, 10, 7, tzinfo=timezone.utc)
    row = SimpleNamespace(monitored_at=start, status="运行中", id=1)
    result = calculate_oee([row], start, start + timedelta(hours=1), {}, 60, 54)
    assert result["oee"] is None
    assert result["reasons"]
    config = {"ideal_cycle_seconds": 30, "planned_windows": [{"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat()}]}
    result = calculate_oee([row], start, start + timedelta(hours=1), config, 60, 54)
    assert result["coverage_rate"] < 1 and result["oee"] is None


def test_reports_outside_plan_do_not_inflate_performance():
    from apps.kuaizhizao.services.oee_calculator import reports_in_plan
    start = datetime(2026, 10, 7, tzinfo=timezone.utc)
    inside = SimpleNamespace(reported_at=start + timedelta(minutes=30))
    after = SimpleNamespace(reported_at=start + timedelta(hours=2))
    config = {"planned_windows": [{"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat()}]}
    assert reports_in_plan([inside, after], config, start, start + timedelta(hours=3)) == [inside]
