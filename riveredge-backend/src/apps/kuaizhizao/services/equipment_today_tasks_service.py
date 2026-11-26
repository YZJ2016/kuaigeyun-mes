"""设备部 — 站点「今日」待完成任务聚合（点检/保养/维修）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaizhizao.models.equipment_fault import EquipmentFault, EquipmentRepair
from apps.kuaizhizao.models.equipment_ops import (
    EquipmentInspectionScheme,
    EquipmentSchemeBinding,
    EquipmentSpotCheck,
)
from apps.kuaizhizao.models.maintenance_plan import MaintenancePlan
from apps.kuaizhizao.models.maintenance_reminder import MaintenanceReminder
from core.utils.timezone_utils import resolve_business_datetime, site_day_bounds_utc, to_site_date

_SPOT_DONE = ("待审核", "已审核")
_EQUIP_EXCLUDED = ("报废", "停用", "scrapped", "disabled")
_OPEN_FAULT = ("待处理", "处理中")
_PLAN_ACTIVE = ("已发布", "执行中")


def _site_today():
    return to_site_date(resolve_business_datetime())


async def count_equipment_today_tasks(*, tenant_id: int, user_id: int) -> int:
    result = await list_equipment_today_tasks(
        tenant_id=tenant_id,
        user_id=user_id,
        limit=500,
    )
    return int(result.get("total") or 0)


async def list_equipment_today_tasks(
    *,
    tenant_id: int,
    user_id: int,
    limit: int = 50,
) -> dict[str, Any]:
    """返回今日待办条目（可执行跳转 link + mobile_route）。"""
    now = resolve_business_datetime()
    today = _site_today()
    day_start, day_end = site_day_bounds_utc(today)
    cap = max(1, min(int(limit or 50), 200))

    items: List[dict[str, Any]] = []

    domain_scheme_ids = list(
        await EquipmentInspectionScheme.filter(
            tenant_id=tenant_id,
            domain="equipment",
            deleted_at__isnull=True,
            is_active=True,
        ).values_list("id", flat=True)
    )
    equipment_ids = list(
        await Equipment.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            is_active=True,
        )
        .exclude(status__in=list(_EQUIP_EXCLUDED))
        .values_list("id", flat=True)
    )
    if domain_scheme_ids and equipment_ids:
        binding_eq_ids = set(
            await EquipmentSchemeBinding.filter(
                tenant_id=tenant_id,
                scheme_type="spot_check",
                equipment_id__in=equipment_ids,
                scheme_id__in=domain_scheme_ids,
                deleted_at__isnull=True,
            ).values_list("equipment_id", flat=True)
        )
        today_checks = await EquipmentSpotCheck.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            equipment_id__in=equipment_ids,
            check_date=today,
            status__in=list(_SPOT_DONE),
            scheme_id__in=domain_scheme_ids,
        ).all()
        done_eq_ids = {c.equipment_id for c in today_checks if c.equipment_id in binding_eq_ids}
        pending_ids = [eid for eid in binding_eq_ids if eid not in done_eq_ids]
        if pending_ids:
            rows = await Equipment.filter(
                tenant_id=tenant_id,
                id__in=pending_ids[:cap],
                deleted_at__isnull=True,
            ).order_by("code", "id")
            for eq in rows:
                code = (eq.code or "").strip()
                name = (eq.name or "").strip()
                label = f"{code} {name}".strip() or str(eq.uuid)
                items.append(
                    {
                        "id": f"equipment_spot_today_{eq.id}",
                        "kind": "spot_check",
                        "priority": "high",
                        "title": f"今日点检：{label}",
                        "description": f"点检日 {today.isoformat()}",
                        "link": "/apps/kuaizhizao/equipment-management/spot-checks",
                        "mobile_route": f"/equipment/spot-check-conduct?equipmentUuid={eq.uuid}",
                        "status": "pending",
                        "due_date": to_site_date(now).isoformat(),
                        "created_at": now,
                        "meta": {"equipment_name": name or code, "equipment_uuid": eq.uuid},
                    }
                )

    reminders = (
        await MaintenanceReminder.filter(
            tenant_id=tenant_id,
            is_handled=False,
            deleted_at__isnull=True,
            days_until_due__lte=0,
        )
        .order_by("days_until_due", "-reminder_date")
        .limit(cap)
    )
    for rem in reminders:
        name = (rem.equipment_name or rem.equipment_code or "").strip() or "设备"
        overdue = int(rem.days_until_due or 0) < 0
        items.append(
            {
                "id": f"maintenance_reminder_{rem.id}",
                "kind": "maintenance_reminder",
                "priority": "high" if overdue else "medium",
                "title": f"{'保养逾期' if overdue else '今日保养'}：{name}",
                "description": (rem.reminder_message or "").strip() or None,
                "link": "/apps/kuaizhizao/equipment-management/maintenance-reminders",
                "mobile_route": "/equipment/maintenance-reminders",
                "status": "pending",
                "due_date": today.isoformat(),
                "created_at": rem.reminder_date or rem.created_at,
                "meta": {
                    "equipment_uuid": rem.equipment_uuid,
                    "plan_uuid": rem.maintenance_plan_uuid,
                },
            }
        )

    plans = (
        await MaintenancePlan.filter(
            tenant_id=tenant_id,
            status__in=list(_PLAN_ACTIVE),
            planned_start_date__gte=day_start,
            planned_start_date__lt=day_end,
            deleted_at__isnull=True,
        )
        .order_by("planned_start_date", "plan_no")
        .limit(cap)
    )
    for plan in plans:
        eq_label = (plan.equipment_name or plan.scheme_name or plan.plan_name or "").strip()
        items.append(
            {
                "id": f"maintenance_plan_today_{plan.id}",
                "kind": "maintenance_plan",
                "priority": "medium",
                "title": f"今日保养计划：{plan.plan_name}",
                "description": eq_label or plan.plan_no,
                "link": f"/apps/kuaizhizao/equipment-management/maintenance-plans?uuid={plan.uuid}",
                "mobile_route": "/equipment/maintenance-executions",
                "status": "pending",
                "due_date": today.isoformat(),
                "created_at": plan.planned_start_date or plan.created_at,
                "meta": {"plan_no": plan.plan_no, "plan_uuid": plan.uuid},
            }
        )

    repairs = (
        await EquipmentRepair.filter(
            tenant_id=tenant_id,
            status="进行中",
            repairer_id=user_id,
            deleted_at__isnull=True,
        )
        .order_by("-created_at")
        .limit(cap)
    )
    for rep in repairs:
        eq = (rep.equipment_name or "").strip() or "设备"
        items.append(
            {
                "id": f"equipment_repair_mine_{rep.id}",
                "kind": "repair",
                "priority": "high",
                "title": f"维修进行中：{rep.repair_no or eq}",
                "description": eq,
                "link": f"/apps/kuaizhizao/equipment-management/equipment-repairs?uuid={rep.uuid}",
                "mobile_route": f"/equipment/repair-detail?uuid={rep.uuid}",
                "status": "in_progress",
                "due_date": today.isoformat(),
                "created_at": rep.created_at,
                "meta": {"repair_uuid": rep.uuid},
            }
        )

    faults = (
        await EquipmentFault.filter(
            tenant_id=tenant_id,
            status__in=list(_OPEN_FAULT),
            deleted_at__isnull=True,
        )
        .order_by("-created_at")
        .limit(min(8, cap))
    )
    for fault in faults:
        eq = (fault.equipment_name or "").strip() or "设备"
        items.append(
            {
                "id": f"equipment_fault_{fault.id}",
                "kind": "fault",
                "priority": "high" if fault.status == "待处理" else "medium",
                "title": f"{'待处理故障' if fault.status == '待处理' else '处理中故障'}：{fault.fault_no or eq}",
                "description": eq,
                "link": f"/apps/kuaizhizao/equipment-management/equipment-faults?uuid={fault.uuid}",
                "mobile_route": f"/equipment/fault-detail?uuid={fault.uuid}",
                "status": "pending" if fault.status == "待处理" else "in_progress",
                "due_date": today.isoformat(),
                "created_at": fault.created_at,
                "meta": {"fault_uuid": fault.uuid},
            }
        )

    prio_rank = {"high": 0, "medium": 1, "low": 2}

    def _sort_key(row: dict[str, Any]) -> tuple:
        created = row.get("created_at")
        if not isinstance(created, datetime):
            created = resolve_business_datetime()
        return (prio_rank.get(str(row.get("priority") or "medium"), 3), created)

    items.sort(key=_sort_key)
    trimmed = items[:cap]
    return {
        "items": trimmed,
        "total": len(trimmed),
        "task_date": today.isoformat(),
        "as_of": now,
    }
