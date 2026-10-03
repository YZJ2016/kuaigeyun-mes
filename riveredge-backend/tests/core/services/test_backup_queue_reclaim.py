from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.tasks import data_backup_handlers as worker


@pytest.mark.asyncio
async def test_backup_lock_busy_stays_pending(monkeypatch):
    backup = SimpleNamespace(
        uuid="u1",
        name="n",
        tenant_id=1,
        include_files=True,
        status="pending",
        created_at=None,
        updated_at=None,
        error_message="old",
        progress_message=None,
        completed_at=None,
        started_at=None,
        inngest_run_id=None,
        save=AsyncMock(),
    )
    monkeypatch.setattr(worker, "_LOCK_WAIT_MAX", timedelta(0))
    monkeypatch.setattr(worker, "is_backup_advisory_lock_held", AsyncMock(return_value=False))
    monkeypatch.setattr(worker.DataBackup, "get", AsyncMock(return_value=backup))
    monkeypatch.setattr(worker, "_try_acquire_backup_lock", AsyncMock(return_value=None))
    ctx = SimpleNamespace(
        event=SimpleNamespace(data={"backup_uuid": "u1", "tenant_id": 1}),
        run_id="r1",
    )
    await worker.handle_database_backup_requested(ctx, SimpleNamespace())
    assert backup.status == "pending"
    assert backup.progress_message == "排队中：等待其它备份完成"
    assert backup.save.await_count == 1


@pytest.mark.asyncio
async def test_queue_lookup_failure_skips_redispatch(monkeypatch):
    import asyncpg

    from core.services.system.data_backup_service import DataBackupService

    monkeypatch.setattr(asyncpg, "connect", AsyncMock(side_effect=RuntimeError("down")))
    assert await DataBackupService._queue_has_backup_message("u1") is True
