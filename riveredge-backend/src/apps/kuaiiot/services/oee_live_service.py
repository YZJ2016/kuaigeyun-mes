"""快数采 OEE 实时信号（基于 sensor 监控，禁止造假）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaizhizao.models.equipment_status_monitor import EquipmentStatusMonitor
from apps.kuaizhizao.models.reporting_record import ReportingRecord
from apps.kuaiiot.constants import MES_DATA_SOURCE
from apps.kuaiiot.models.iot import IotDevice
from apps.kuaiiot.schemas.iot import OeeLiveEquipmentResponse, OeeLiveListResponse
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import NotFoundError

RUNNING_STATUSES = frozenset({"运行中"})
IDLE_STATUSES = frozenset({"待机", "正常"})
DOWN_STATUSES = frozenset({"故障", "维修中", "停用"})


@dataclass(frozen=True)
class _StatusSegment:
    status: str
    started_at: datetime
    ended_at: datetime

    @property
    def minutes(self) -> float:
        delta = self.ended_at - self.started_at
        return max(delta.total_seconds(), 0) / 60.0


class OeeLiveService:
    @staticmethod
    def _bucket_status(status: str) -> str:
        text = str(status or "").strip()
        if text in RUNNING_STATUSES:
            return "running"
        if text in DOWN_STATUSES:
            return "down"
        return "idle"

    @staticmethod
    def _build_segments(
        monitors: list[EquipmentStatusMonitor],
        window_start: datetime,
        window_end: datetime,
    ) -> list[_StatusSegment]:
        if not monitors:
            return []
        ordered = sorted(monitors, key=lambda item: item.monitored_at or window_start)
        segments: list[_StatusSegment] = []
        for index, monitor in enumerate(ordered):
            start = monitor.monitored_at or window_start
            if start < window_start:
                start = window_start
            end = window_end
            if index + 1 < len(ordered):
                next_at = ordered[index + 1].monitored_at or window_end
                end = min(next_at, window_end)
            if end <= start:
                continue
            segments.append(_StatusSegment(status=str(monitor.status or "待机"), started_at=start, ended_at=end))
        return segments

    @staticmethod
    def _summarize_segments(segments: list[_StatusSegment]) -> dict[str, float]:
        totals = {"running_minutes": 0.0, "idle_minutes": 0.0, "down_minutes": 0.0}
        for segment in segments:
            bucket = OeeLiveService._bucket_status(segment.status)
            key = f"{bucket}_minutes"
            totals[key] = totals.get(key, 0.0) + segment.minutes
        active = totals["running_minutes"] + totals["idle_minutes"] + totals["down_minutes"]
        availability_rate = (totals["running_minutes"] / active * 100) if active > 0 else 0.0
        totals["availability_rate"] = round(min(max(availability_rate, 0.0), 100.0), 2)
        totals["running_minutes"] = round(totals["running_minutes"], 2)
        totals["idle_minutes"] = round(totals["idle_minutes"], 2)
        totals["down_minutes"] = round(totals["down_minutes"], 2)
        return totals

    @staticmethod
    async def _mes_quality_rate(
        tenant_id: int,
        equipment: Equipment,
        window_start: datetime,
        window_end: datetime,
    ) -> Optional[float]:
        records = await ReportingRecord.filter(
            tenant_id=tenant_id,
            reported_at__gte=window_start,
            reported_at__lte=window_end,
            status="approved",
            deleted_at__isnull=True,
        )
        actual = Decimal("0")
        qualified = Decimal("0")
        for record in records:
            device_info = record.device_info or {}
            device_id = device_info.get("equipment_id") or device_info.get("id")
            device_code = device_info.get("equipment_code") or device_info.get("code")
            if device_id != equipment.id and device_code != equipment.code:
                continue
            actual += Decimal(str(record.reported_quantity or 0))
            qualified += Decimal(str(record.qualified_quantity or 0))
        if actual <= 0:
            return None
        return round(float(qualified / actual * 100), 2)

    @staticmethod
    async def get_equipment_oee_live(
        tenant_id: int,
        equipment_uuid: str,
        *,
        hours: int = 24,
    ) -> OeeLiveEquipmentResponse:
        equipment = await Equipment.filter(
            tenant_id=tenant_id,
            uuid=equipment_uuid,
            deleted_at__isnull=True,
        ).first()
        if not equipment:
            raise NotFoundError(f"MES 设备不存在: {equipment_uuid}")

        window_end = resolve_business_datetime()
        window_start = window_end - timedelta(hours=max(hours, 1))
        monitors = await EquipmentStatusMonitor.filter(
            tenant_id=tenant_id,
            equipment_uuid=equipment_uuid,
            data_source=MES_DATA_SOURCE,
            monitored_at__gte=window_start,
            monitored_at__lte=window_end,
            deleted_at__isnull=True,
        ).order_by("monitored_at")
        segments = OeeLiveService._build_segments(list(monitors), window_start, window_end)
        sensor = OeeLiveService._summarize_segments(segments)
        quality_rate = await OeeLiveService._mes_quality_rate(tenant_id, equipment, window_start, window_end)

        iot_device = await IotDevice.filter(
            tenant_id=tenant_id,
            equipment_uuid=equipment_uuid,
            deleted_at__isnull=True,
        ).first()

        oee_live: Optional[float] = None
        oee_note = "仅展示 sensor 可用率，未合成 OEE"
        if quality_rate is not None and sensor["availability_rate"] > 0:
            oee_live = round(sensor["availability_rate"] * quality_rate / 100, 2)
            oee_note = "OEE 由 sensor 可用率 × MES 良品率合成，性能稼动率未纳入"

        latest = monitors[-1] if monitors else None
        return OeeLiveEquipmentResponse(
            equipment_uuid=equipment.uuid,
            equipment_code=equipment.code,
            equipment_name=equipment.name,
            window_start=window_start,
            window_end=window_end,
            sensor=sensor,
            mes_quality_rate=quality_rate,
            oee_live=oee_live,
            oee_note=oee_note,
            latest_status=latest.status if latest else equipment.status,
            is_online=latest.is_online if latest else bool(iot_device and iot_device.is_online),
            iot_device_uuid=iot_device.uuid if iot_device else None,
            monitor_points=len(monitors),
        )

    @staticmethod
    async def list_equipment_oee_live(
        tenant_id: int,
        *,
        hours: int = 24,
        limit: int = 50,
    ) -> OeeLiveListResponse:
        devices = await IotDevice.filter(
            tenant_id=tenant_id,
            equipment_uuid__not_isnull=True,
            deleted_at__isnull=True,
        ).order_by("-last_seen_at").limit(limit)
        items: list[OeeLiveEquipmentResponse] = []
        for device in devices:
            if not device.equipment_uuid:
                continue
            try:
                items.append(
                    await OeeLiveService.get_equipment_oee_live(
                        tenant_id,
                        device.equipment_uuid,
                        hours=hours,
                    )
                )
            except NotFoundError:
                continue
        return OeeLiveListResponse(items=items, total=len(items))
