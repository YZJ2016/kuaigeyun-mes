"""定时任务调度器：Cron 按站点墙钟匹配。"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.workflows.functions.scheduled_task_scheduler import _should_execute_task


def _task(**kwargs):
    defaults = {
        "trigger_type": "cron",
        "trigger_config": {"cron": "0 8 * * *"},
        "is_running": False,
        "last_run_at": None,
    }
    defaults.update(kwargs)
    task = MagicMock()
    for key, value in defaults.items():
        setattr(task, key, value)
    return task


@pytest.mark.asyncio
async def test_cron_matches_site_wall_clock_not_utc():
    """配置 8:00 应按站点时区命中，而非 UTC 8:00。"""
    task = _task(trigger_config={"cron": "0 8 * * *"})
    # UTC 00:00 = 上海 08:00（假定站点 Asia/Shanghai）
    utc_morning = datetime(2026, 9, 13, 0, 0, 0, tzinfo=timezone.utc)
    with patch(
        "core.workflows.functions.scheduled_task_scheduler.to_site_timezone",
        return_value=datetime(2026, 9, 13, 8, 0, 0),
    ):
        assert await _should_execute_task(task, utc_morning) is True

    utc_eight = datetime(2026, 9, 13, 8, 0, 0, tzinfo=timezone.utc)
    with patch(
        "core.workflows.functions.scheduled_task_scheduler.to_site_timezone",
        return_value=datetime(2026, 9, 13, 16, 0, 0),
    ):
        assert await _should_execute_task(task, utc_eight) is False


@pytest.mark.asyncio
async def test_cron_skips_same_site_minute_as_last_run():
    task = _task(
        trigger_config={"cron": "0 8 * * *"},
        last_run_at=datetime(2026, 9, 13, 0, 0, 0, tzinfo=timezone.utc),
    )
    utc_now = datetime(2026, 9, 13, 0, 0, 0, tzinfo=timezone.utc)
    site_eight = datetime(2026, 9, 13, 8, 0, 0)

    with patch(
        "core.workflows.functions.scheduled_task_scheduler.to_site_timezone",
        side_effect=[site_eight, site_eight, site_eight],
    ):
        assert await _should_execute_task(task, utc_now) is False
