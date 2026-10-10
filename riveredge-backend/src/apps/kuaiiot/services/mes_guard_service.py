"""MES 设备态写回护栏。"""

from __future__ import annotations

from typing import Any, Optional

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaizhizao.models.equipment_fault import EquipmentFault, EquipmentRepair
from apps.kuaizhizao.services.equipment_service import EquipmentService
from apps.kuaizhizao.services.equipment_status_monitor_service import EquipmentStatusMonitorService
from apps.kuaiiot.services.status_mapper import normalize_equipment_status

MES_STATUS_PROTECTED = frozenset({"停用", "报废", "校验中"})
OPEN_FAULT_STATUSES = ("待处理", "处理中")
TELEMETRY_KEYS = frozenset({"temperature", "pressure", "vibration", "other_parameters"})


class MesGuardService:
    @staticmethod
    async def _is_status_writeback_blocked(tenant_id: int, equipment_id: int) -> bool:
        equipment = await Equipment.filter(
            tenant_id=tenant_id,
            id=equipment_id,
            deleted_at__isnull=True,
        ).first()
        if not equipment:
            return True
        if str(equipment.status or "") in MES_STATUS_PROTECTED:
            return True
        if await EquipmentRepair.filter(
            tenant_id=tenant_id,
            equipment_id=equipment_id,
            status="进行中",
            deleted_at__isnull=True,
        ).exists():
            return True
        if await EquipmentFault.filter(
            tenant_id=tenant_id,
            equipment_id=equipment_id,
            status__in=list(OPEN_FAULT_STATUSES),
            deleted_at__isnull=True,
        ).exists():
            return True
        return False

    @staticmethod
    async def prepare_mes_payload(
        tenant_id: int,
        equipment_uuid: str,
        mes_payload: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """
        准备写回 MES 的 payload。

        - 传感器 status 归一化；缺失时不默认运行中
        - 护栏命中时保留 equipment 当前 status，且不改变 is_online 语义
        - 护栏命中且无采集量时跳过写回（返回 None）
        """
        if not mes_payload:
            return None

        equipment = await EquipmentService.get_equipment_by_uuid(tenant_id, equipment_uuid)
        payload = dict(mes_payload)
        blocked = await MesGuardService._is_status_writeback_blocked(tenant_id, equipment.id)

        if "status" in payload:
            payload["status"] = normalize_equipment_status(str(payload["status"]))
        else:
            payload["status"] = equipment.status

        if blocked:
            payload["status"] = equipment.status
            latest = await EquipmentStatusMonitorService().get_latest_status(tenant_id, equipment_uuid)
            payload["is_online"] = latest.is_online if latest else payload.get("is_online", True)
        elif "is_online" not in payload:
            payload["is_online"] = True

        has_telemetry = any(key in payload for key in TELEMETRY_KEYS)
        if blocked and not has_telemetry and payload["status"] == equipment.status:
            return None
        return payload
