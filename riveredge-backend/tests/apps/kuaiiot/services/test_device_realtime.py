from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiiot.services.device_lifecycle_service import DeviceLifecycleService
from apps.kuaiiot.services.ingest_service import IngestService


@pytest.mark.asyncio
async def test_schedule_device_update_publishes_tenant_event():
    device = SimpleNamespace(
        tenant_id=7,
        uuid="device-uuid",
        id=12,
        code="D-12",
        external_device_id="external-12",
        is_online=True,
        last_seen_at=None,
        equipment_uuid="equipment-uuid",
    )

    with patch(
        "apps.kuaiiot.services.ingest_service.schedule_tenant_realtime_event"
    ) as publish:
        IngestService.schedule_device_update(device, synced_to_mes=True)

    publish.assert_called_once()
    kwargs = publish.call_args.kwargs
    assert kwargs["tenant_id"] == 7
    assert kwargs["scope"] == "kuaiiot"
    assert kwargs["event"] == "kuaiiot.device.updated"
    assert kwargs["payload"]["device_uuid"] == "device-uuid"
    assert kwargs["payload"]["is_online"] is True
    assert kwargs["payload"]["synced_to_mes"] is True


@pytest.mark.asyncio
async def test_mark_stale_devices_offline_emits_realtime_event():
    bound_device = SimpleNamespace(
        tenant_id=7,
        uuid="dev-bound",
        id=1,
        code="D-1",
        external_device_id="ext-1",
        is_online=True,
        last_seen_at=datetime(2026, 11, 27, 1, 0, tzinfo=timezone.utc),
        equipment_uuid="eq-1",
        save=AsyncMock(),
    )
    unbound_device = SimpleNamespace(
        tenant_id=7,
        uuid="dev-unbound",
        id=2,
        code="D-2",
        external_device_id="ext-2",
        is_online=True,
        last_seen_at=datetime(2026, 11, 27, 1, 0, tzinfo=timezone.utc),
        equipment_uuid=None,
        save=AsyncMock(),
    )

    with (
        patch(
            "apps.kuaiiot.services.device_lifecycle_service.IotDevice.filter",
            new=AsyncMock(return_value=[bound_device, unbound_device]),
        ),
        patch(
            "apps.kuaiiot.services.device_lifecycle_service.AlertService.evaluate_device_offline",
            new=AsyncMock(),
        ),
        patch(
            "apps.kuaiiot.services.device_lifecycle_service.IngestService.sync_offline_to_mes",
            new=AsyncMock(return_value=True),
        ) as sync_mes,
        patch(
            "apps.kuaiiot.services.device_lifecycle_service.IngestService.schedule_device_update"
        ) as schedule_update,
    ):
        result = await DeviceLifecycleService.mark_stale_devices_offline()

    assert result == {"marked_offline": 2, "mes_synced": 1}
    assert bound_device.is_online is False
    assert unbound_device.is_online is False
    sync_mes.assert_awaited_once_with(bound_device)
    assert schedule_update.call_count == 2
    assert schedule_update.call_args_list[0].args == (bound_device,)
    assert schedule_update.call_args_list[0].kwargs == {"synced_to_mes": True}
    assert schedule_update.call_args_list[1].args == (unbound_device,)
    assert schedule_update.call_args_list[1].kwargs == {"synced_to_mes": False}


@pytest.mark.asyncio
async def test_maybe_insert_monitor_bypasses_throttle_on_is_online_change():
    now = datetime(2026, 11, 27, 8, 0, 10, tzinfo=timezone.utc)
    equipment = SimpleNamespace(id=5, uuid="eq-5", code="EQ-5", name="Press 5", status="运行中")

    def _eq_filter(*_args, **_kwargs):
        q = MagicMock()
        q.select_for_update.return_value = q
        q.first = AsyncMock(return_value=equipment)
        return q

    def _mon_filter(latest_row):
        def _factory(*_args, **_kwargs):
            q = MagicMock()
            q.order_by.return_value = q
            q.first = AsyncMock(return_value=latest_row)
            return q

        return _factory

    # 1) Within 5s throttle window, is_online flips True -> False: MUST bypass throttle
    latest_online = SimpleNamespace(
        status="运行中",
        is_online=True,
        monitored_at=now - timedelta(seconds=2),
        created_at=now - timedelta(seconds=2),
    )
    with (
        patch("apps.kuaiiot.services.ingest_service.Equipment.filter", side_effect=_eq_filter),
        patch(
            "apps.kuaiiot.services.ingest_service.EquipmentStatusMonitor.filter",
            side_effect=_mon_filter(latest_online),
        ),
        patch(
            "apps.kuaiiot.services.ingest_service.IngestService._writeback_blocked",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "apps.kuaiiot.services.ingest_service.EquipmentStatusMonitor.create",
            new=AsyncMock(),
        ) as mon_create,
    ):
        written = await IngestService._maybe_insert_monitor(
            1, equipment, {"is_online": False}, now, now
        )
    assert written is True
    assert mon_create.await_args.kwargs["is_online"] is False

    # 2) Within 5s throttle window, is_online flips False -> True (implicit on ingest): MUST bypass throttle
    latest_offline = SimpleNamespace(
        status="运行中",
        is_online=False,
        monitored_at=now - timedelta(seconds=2),
        created_at=now - timedelta(seconds=2),
    )
    with (
        patch("apps.kuaiiot.services.ingest_service.Equipment.filter", side_effect=_eq_filter),
        patch(
            "apps.kuaiiot.services.ingest_service.EquipmentStatusMonitor.filter",
            side_effect=_mon_filter(latest_offline),
        ),
        patch(
            "apps.kuaiiot.services.ingest_service.IngestService._writeback_blocked",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "apps.kuaiiot.services.ingest_service.EquipmentStatusMonitor.create",
            new=AsyncMock(),
        ) as mon_create,
    ):
        written = await IngestService._maybe_insert_monitor(
            1, equipment, {"status": "运行中"}, now, now
        )
    assert written is True
    assert mon_create.await_args.kwargs["is_online"] is True

    # 3) Within 5s throttle window, neither status nor is_online changed: MUST throttle
    with (
        patch("apps.kuaiiot.services.ingest_service.Equipment.filter", side_effect=_eq_filter),
        patch(
            "apps.kuaiiot.services.ingest_service.EquipmentStatusMonitor.filter",
            side_effect=_mon_filter(latest_online),
        ),
        patch(
            "apps.kuaiiot.services.ingest_service.IngestService._writeback_blocked",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "apps.kuaiiot.services.ingest_service.EquipmentStatusMonitor.create",
            new=AsyncMock(),
        ) as mon_create,
    ):
        written = await IngestService._maybe_insert_monitor(
            1, equipment, {"status": "运行中"}, now, now
        )
    assert written is False
    mon_create.assert_not_awaited()
