"""快数采设备在线生命周期。"""

from __future__ import annotations

from datetime import timedelta

from apps.kuaiiot.constants import OFFLINE_THRESHOLD_SECONDS
from apps.kuaiiot.models.iot import IotDevice
from apps.kuaiiot.services.alert_service import AlertService
from apps.kuaiiot.services.ingest_service import IngestService
from core.utils.timezone_utils import resolve_business_datetime


class DeviceLifecycleService:
    @staticmethod
    async def mark_stale_devices_offline() -> dict[str, int]:
        cutoff = resolve_business_datetime() - timedelta(seconds=OFFLINE_THRESHOLD_SECONDS)
        devices = await IotDevice.filter(
            is_online=True,
            last_seen_at__lt=cutoff,
            deleted_at__isnull=True,
        )
        marked = 0
        mes_synced = 0
        for device in devices:
            device.is_online = False
            await device.save()
            marked += 1
            await AlertService.evaluate_device_offline(device.tenant_id, device)
            if device.equipment_uuid:
                synced = await IngestService.sync_offline_to_mes(device)
                if synced:
                    mes_synced += 1
        return {"marked_offline": marked, "mes_synced": mes_synced}
