"""快数采 equipment-ops 大屏数据馈送（供快报表 HTTP 数据源消费）。"""

from __future__ import annotations

from typing import Any

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaiiot.models.iot import IotDevice, IotTagSnapshot
from apps.kuaiiot.schemas.iot import EquipmentOpsFeedResponse
from apps.kuaiiot.services.oee_live_service import OeeLiveService
from core.utils.timezone_utils import resolve_business_datetime, to_api_isoformat


class EquipmentOpsFeedService:
    @staticmethod
    async def build_feed(tenant_id: int, *, hours: int = 24) -> EquipmentOpsFeedResponse:
        devices = await IotDevice.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).order_by("-last_seen_at")
        equipment_list: list[dict[str, Any]] = []
        ops_metrics: list[dict[str, Any]] = []
        status_dist: dict[str, int] = {}

        for device in devices:
            equipment_name = device.name
            equipment_code = device.code
            if device.equipment_uuid:
                equipment = await Equipment.filter(
                    tenant_id=tenant_id,
                    uuid=device.equipment_uuid,
                    deleted_at__isnull=True,
                ).first()
                if equipment:
                    equipment_name = equipment.name
                    equipment_code = equipment.code

            snapshots = await IotTagSnapshot.filter(
                tenant_id=tenant_id,
                device_id=device.id,
                deleted_at__isnull=True,
            )
            snapshot_map = {item.tag_key: item for item in snapshots}
            temp = snapshot_map.get("temp") or snapshot_map.get("temperature")
            status_tag = snapshot_map.get("status")

            oee_item = None
            if device.equipment_uuid:
                try:
                    oee_item = await OeeLiveService.get_equipment_oee_live(
                        tenant_id,
                        device.equipment_uuid,
                        hours=hours,
                    )
                except Exception:
                    oee_item = None

            latest_status = (
                (status_tag.value_text if status_tag else None)
                or (oee_item.latest_status if oee_item else None)
                or ("在线" if device.is_online else "离线")
            )
            status_key = str(latest_status)
            status_dist[status_key] = status_dist.get(status_key, 0) + 1

            equipment_list.append(
                {
                    "device_uuid": device.uuid,
                    "equipment_uuid": device.equipment_uuid,
                    "code": equipment_code,
                    "name": equipment_name,
                    "status": latest_status,
                    "is_online": device.is_online,
                    "last_seen_at": to_api_isoformat(device.last_seen_at) if device.last_seen_at else None,
                }
            )
            ops_metrics.append(
                {
                    "device_uuid": device.uuid,
                    "equipment_uuid": device.equipment_uuid,
                    "equipment_code": equipment_code,
                    "equipment_name": equipment_name,
                    "status": latest_status,
                    "is_online": device.is_online,
                    "temperature": float(temp.value_number) if temp and temp.value_number is not None else None,
                    "availability_rate": oee_item.sensor.get("availability_rate") if oee_item else None,
                    "quality_rate": oee_item.mes_quality_rate if oee_item else None,
                    "oee_live": oee_item.oee_live if oee_item else None,
                    "last_seen_at": to_api_isoformat(device.last_seen_at) if device.last_seen_at else None,
                }
            )

        workshop_stats = [
            {"metric": "online_devices", "value": sum(1 for item in devices if item.is_online)},
            {"metric": "bound_devices", "value": sum(1 for item in devices if item.equipment_uuid)},
            {"metric": "total_devices", "value": len(devices)},
        ]
        spot_check_recent = [
            {
                "equipment_name": item["equipment_name"],
                "status": item["status"],
                "sampled_at": item["last_seen_at"],
            }
            for item in equipment_list[:10]
        ]

        return EquipmentOpsFeedResponse(
            generated_at=resolve_business_datetime(),
            equipment_list=equipment_list,
            ops_metrics=ops_metrics,
            status_dist=[{"status": key, "count": value} for key, value in status_dist.items()],
            workshop_stats=workshop_stats,
            spot_check_recent=spot_check_recent,
        )
