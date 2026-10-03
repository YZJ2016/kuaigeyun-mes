"""IngestService 单元测试。"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiiot.services.ingest_service import IngestService


class TestIngestServiceCoerce:
    def test_coerce_boolean(self):
        assert IngestService._coerce_value(True, "boolean") == (None, None, True)
        assert IngestService._coerce_value("online", "boolean") == (None, None, True)

    def test_coerce_number(self):
        assert IngestService._coerce_value("12.5", "number") == (None, Decimal("12.5"), None)

    def test_apply_map_target_status(self):
        payload = {}
        IngestService._apply_map_target("status", "运行中", None, None, payload)
        assert payload["status"] == "运行中"

    def test_apply_map_target_other_parameters(self):
        payload = {}
        IngestService._apply_map_target("other_parameters.speed", None, Decimal("120"), None, payload)
        assert payload["other_parameters"]["speed"] == 120.0


def _device_mock():
    device = AsyncMock()
    device.equipment_uuid = "eq-1"
    device.tenant_id = 1
    device.last_mes_sync_at = None
    device.save = AsyncMock()
    return device


@pytest.mark.asyncio
async def test_maybe_sync_mes_throttles_same_status_telemetry():
    device = _device_mock()
    now = datetime(2026, 8, 7, 4, 0, tzinfo=timezone.utc)
    latest = MagicMock(status="运行中", is_online=True)

    with patch("apps.kuaiiot.services.ingest_service.resolve_business_datetime", return_value=now), patch(
        "apps.kuaiiot.services.ingest_service.EquipmentStatusMonitorService"
    ) as mock_service_cls, patch(
        "apps.kuaiiot.services.ingest_service.MesGuardService.prepare_mes_payload",
        new=AsyncMock(side_effect=lambda tenant_id, equipment_uuid, mes_payload: dict(mes_payload)),
    ):
        mock_service = mock_service_cls.return_value
        mock_service.create_status_monitor = AsyncMock()
        mock_service.get_latest_status = AsyncMock(return_value=latest)

        synced = await IngestService._maybe_sync_mes(
            device, {"status": "运行中", "temperature": 36}, now
        )
        assert synced is True

        device.last_mes_sync_at = now
        synced_again = await IngestService._maybe_sync_mes(
            device, {"status": "运行中", "temperature": 37}, now
        )
        assert synced_again is False
        assert mock_service.create_status_monitor.await_count == 1


@pytest.mark.asyncio
async def test_maybe_sync_mes_bypasses_throttle_on_status_change():
    device = _device_mock()
    now = datetime(2026, 8, 7, 4, 0, tzinfo=timezone.utc)
    device.last_mes_sync_at = now
    latest = MagicMock(status="运行中", is_online=True)

    with patch("apps.kuaiiot.services.ingest_service.resolve_business_datetime", return_value=now), patch(
        "apps.kuaiiot.services.ingest_service.EquipmentStatusMonitorService"
    ) as mock_service_cls, patch(
        "apps.kuaiiot.services.ingest_service.MesGuardService.prepare_mes_payload",
        new=AsyncMock(side_effect=lambda tenant_id, equipment_uuid, mes_payload: dict(mes_payload)),
    ):
        mock_service = mock_service_cls.return_value
        mock_service.create_status_monitor = AsyncMock()
        mock_service.get_latest_status = AsyncMock(return_value=latest)

        synced = await IngestService._maybe_sync_mes(device, {"status": "故障", "is_online": True}, now)
        assert synced is True
        mock_service.create_status_monitor.assert_awaited_once()


@pytest.mark.asyncio
async def test_maybe_sync_mes_bypasses_throttle_on_online_change():
    device = _device_mock()
    now = datetime(2026, 8, 7, 4, 0, tzinfo=timezone.utc)
    device.last_mes_sync_at = now
    latest = MagicMock(status="待机", is_online=True)

    with patch("apps.kuaiiot.services.ingest_service.resolve_business_datetime", return_value=now), patch(
        "apps.kuaiiot.services.ingest_service.EquipmentStatusMonitorService"
    ) as mock_service_cls, patch(
        "apps.kuaiiot.services.ingest_service.MesGuardService.prepare_mes_payload",
        new=AsyncMock(side_effect=lambda tenant_id, equipment_uuid, mes_payload: dict(mes_payload)),
    ):
        mock_service = mock_service_cls.return_value
        mock_service.create_status_monitor = AsyncMock()
        mock_service.get_latest_status = AsyncMock(return_value=latest)

        synced = await IngestService._maybe_sync_mes(
            device, {"status": "待机", "is_online": False}, now
        )
        assert synced is True


@pytest.mark.asyncio
async def test_maybe_sync_mes_missing_equipment_does_not_raise():
    from infra.exceptions.exceptions import NotFoundError

    device = _device_mock()
    device.equipment_uuid = "missing-eq"
    now = datetime(2026, 8, 7, 4, 0, tzinfo=timezone.utc)

    with patch("apps.kuaiiot.services.ingest_service.resolve_business_datetime", return_value=now), patch(
        "apps.kuaiiot.services.ingest_service.EquipmentStatusMonitorService"
    ) as mock_service_cls, patch(
        "apps.kuaiiot.services.ingest_service.MesGuardService.prepare_mes_payload",
        new=AsyncMock(side_effect=NotFoundError("设备不存在")),
    ):
        synced = await IngestService._maybe_sync_mes(device, {"status": "运行中"}, now)
        assert synced is False
        mock_service_cls.return_value.create_status_monitor.assert_not_called()


@pytest.mark.asyncio
async def test_maybe_sync_mes_guard_skip_returns_false():
    device = _device_mock()
    now = datetime(2026, 8, 7, 4, 0, tzinfo=timezone.utc)

    with patch("apps.kuaiiot.services.ingest_service.resolve_business_datetime", return_value=now), patch(
        "apps.kuaiiot.services.ingest_service.EquipmentStatusMonitorService"
    ) as mock_service_cls, patch(
        "apps.kuaiiot.services.ingest_service.MesGuardService.prepare_mes_payload",
        new=AsyncMock(return_value=None),
    ):
        synced = await IngestService._maybe_sync_mes(device, {"status": "运行中"}, now)
        assert synced is False
        mock_service_cls.return_value.create_status_monitor.assert_not_called()
