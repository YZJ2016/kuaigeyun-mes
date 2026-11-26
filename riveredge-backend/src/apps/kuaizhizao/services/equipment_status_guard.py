"""设备台账状态写护栏（状态监控 / 故障同步共用）。"""

from __future__ import annotations

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaizhizao.models.equipment_fault import EquipmentFault, EquipmentRepair
from apps.kuaizhizao.schemas.equipment import EQUIPMENT_STATUS_PROTECTED

_OPEN_FAULT_STATUSES = ("待处理", "处理中")


async def equipment_status_writeback_blocked(tenant_id: int, equipment_id: int) -> bool:
    """与 MesGuard 一致：受保护台账态，或存在进行中维修 / 未闭环故障时，禁止外部回写状态。"""
    equipment = await Equipment.filter(
        tenant_id=tenant_id,
        id=equipment_id,
        deleted_at__isnull=True,
    ).first()
    if not equipment:
        return True
    if str(equipment.status or "") in EQUIPMENT_STATUS_PROTECTED:
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
        status__in=list(_OPEN_FAULT_STATUSES),
        deleted_at__isnull=True,
    ).exists():
        return True
    return False


def resolve_status_for_monitor_writeback(
    current_status: str | None,
    requested_status: str,
    *,
    blocked: bool,
) -> str:
    """回写台账时的生效状态：护栏命中则保留当前台账态。"""
    current = str(current_status or "").strip()
    requested = str(requested_status or "").strip()
    if blocked and current:
        return current
    return requested or current or "正常"
