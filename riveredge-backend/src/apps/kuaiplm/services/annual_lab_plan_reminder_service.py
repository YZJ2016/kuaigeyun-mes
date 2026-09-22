"""年度例式实验下月任务到期前提醒（R-07 / INF-03）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from loguru import logger

from apps.kuaiplm.models.annual_lab_plan import (
    MONTH_STATUS_COMPLETED,
    PLAN_STATUS_APPROVED,
    AnnualLabPlan,
    AnnualLabPlanMonth,
)
from apps.kuaiplm.services.kuaiplm_business_notification import (
    ACTION_ANNUAL_LAB_MONTH_DUE,
    TRIGGER_ANNUAL_LAB_PLAN,
    dispatch_kuaiplm_notification,
)
from core.models.application import Application
from core.models.reminder_event import ReminderEvent
from core.services.business.reminder_dispatch_service import (
    register_reminder_handler,
    register_reminder_preparer,
)
from core.services.business.reminder_event_service import ReminderEventService
from core.utils.timezone_utils import (
    resolve_business_datetime,
    site_timezone_name,
    to_api_isoformat,
)

ENTITY_TYPE = "annual_lab_plan_month"
RULE_PREFIX = "kuaiplm.annual_lab_plan"
RULE_MONTH_DUE = f"{RULE_PREFIX}.month_due"
CHANNEL_INTERNAL = "internal"
REMIND_DAY = 1
REMIND_HOUR = 10


def _site_wall_clock_utc(year: int, month: int, day: int, hour: int) -> datetime:
    tz = ZoneInfo(site_timezone_name())
    local = datetime(year, month, day, hour, 0, 0, tzinfo=tz)
    return local.astimezone(timezone.utc)


def _parse_year_month(value: Optional[str]) -> Optional[tuple[int, int]]:
    raw = (value or "").strip()
    if len(raw) != 7 or raw[4] != "-":
        return None
    try:
        year = int(raw[:4])
        month = int(raw[5:7])
    except ValueError:
        return None
    if year < 2000 or month < 1 or month > 12:
        return None
    return year, month


def _annual_lab_plan_detail_path(plan_id: int) -> str:
    return f"/apps/kuaiplm/annual-lab-plans?planId={plan_id}"


class AnnualLabPlanReminderService:
    @staticmethod
    def _month_remind_at(year_month: str) -> Optional[datetime]:
        """任务月 1 日 10:00 站点墙钟 → UTC（下月任务到期前提醒入口）。"""
        parsed = _parse_year_month(year_month)
        if not parsed:
            return None
        year, month = parsed
        return _site_wall_clock_utc(year, month, REMIND_DAY, REMIND_HOUR)

    @staticmethod
    async def stop_month(tenant_id: int, month_id: int, *, reason: str) -> int:
        return await ReminderEventService.stop_future_for_entity(
            tenant_id,
            entity_type=ENTITY_TYPE,
            entity_id=month_id,
            reason=reason,
            rule_id=f"{RULE_MONTH_DUE}:{month_id}",
        )

    @staticmethod
    async def stop_plan(tenant_id: int, plan_id: int, *, reason: str) -> int:
        months = await AnnualLabPlanMonth.filter(
            tenant_id=tenant_id,
            plan_id=plan_id,
            deleted_at__isnull=True,
        ).all()
        total = 0
        for month in months:
            total += await AnnualLabPlanReminderService.stop_month(
                tenant_id, month.id, reason=reason
            )
        return total

    @staticmethod
    async def ensure_month_reminder(
        tenant_id: int, plan: AnnualLabPlan, month: AnnualLabPlanMonth
    ) -> None:
        if plan.status != PLAN_STATUS_APPROVED:
            return
        if month.month_status == MONTH_STATUS_COMPLETED:
            await AnnualLabPlanReminderService.stop_month(
                tenant_id, month.id, reason="月度任务已完成"
            )
            return
        planned_at = AnnualLabPlanReminderService._month_remind_at(month.year_month)
        if not planned_at:
            return
        now = resolve_business_datetime()
        if planned_at <= now:
            return
        await ReminderEventService.ensure_event(
            tenant_id,
            rule_id=f"{RULE_MONTH_DUE}:{month.id}",
            rule_code=RULE_MONTH_DUE,
            entity_type=ENTITY_TYPE,
            entity_id=month.id,
            entity_uuid=str(month.uuid) if month.uuid else None,
            planned_at=planned_at,
            channel=CHANNEL_INTERNAL,
            payload={
                "kind": "month_due",
                "plan_id": plan.id,
                "year_month": month.year_month,
            },
        )

    @staticmethod
    async def sync_plan(tenant_id: int, plan_id: int) -> None:
        plan = await AnnualLabPlan.filter(
            tenant_id=tenant_id, id=plan_id, deleted_at__isnull=True
        ).first()
        if not plan:
            return
        if plan.status != PLAN_STATUS_APPROVED:
            await AnnualLabPlanReminderService.stop_plan(
                tenant_id, plan_id, reason="计划未批准或已关闭"
            )
            return
        months = await AnnualLabPlanMonth.filter(
            tenant_id=tenant_id,
            plan_id=plan_id,
            deleted_at__isnull=True,
        ).all()
        for month in months:
            await AnnualLabPlanReminderService.ensure_month_reminder(
                tenant_id, plan, month
            )


async def prepare_annual_lab_plan_reminders() -> None:
    tenant_ids = (
        await Application.filter(
            code="kuaiplm",
            is_installed=True,
            deleted_at__isnull=True,
        )
        .distinct()
        .values_list("tenant_id", flat=True)
    )
    for tenant_id in tenant_ids:
        plan_ids = (
            await AnnualLabPlan.filter(
                tenant_id=int(tenant_id),
                status=PLAN_STATUS_APPROVED,
                deleted_at__isnull=True,
            )
            .values_list("id", flat=True)
        )
        for plan_id in plan_ids:
            try:
                await AnnualLabPlanReminderService.sync_plan(int(tenant_id), int(plan_id))
            except Exception as exc:
                logger.error(
                    "年度例式实验提醒登记失败 tenant={} plan={}: {}",
                    tenant_id,
                    plan_id,
                    exc,
                )


async def dispatch_annual_lab_plan_reminder(
    tenant_id: int, event: ReminderEvent
) -> Literal["sent", "stopped"]:
    if str(event.rule_code or "") != RULE_MONTH_DUE:
        await ReminderEventService.mark_stopped(
            tenant_id, event.id, f"未知年度计划提醒规则: {event.rule_code}"
        )
        return "stopped"

    month = await AnnualLabPlanMonth.filter(
        tenant_id=tenant_id, id=event.entity_id, deleted_at__isnull=True
    ).first()
    if not month:
        await ReminderEventService.mark_stopped(tenant_id, event.id, "月度台账已删除")
        return "stopped"

    plan = await AnnualLabPlan.filter(
        tenant_id=tenant_id, id=month.plan_id, deleted_at__isnull=True
    ).first()
    if not plan or plan.status != PLAN_STATUS_APPROVED:
        await ReminderEventService.mark_stopped(tenant_id, event.id, "年度计划不可执行")
        return "stopped"
    if month.month_status == MONTH_STATUS_COMPLETED:
        await ReminderEventService.mark_stopped(tenant_id, event.id, "月度任务已完成")
        return "stopped"

    due_text = to_api_isoformat(month.due_at) or "—"
    sent = await dispatch_kuaiplm_notification(
        tenant_id,
        trigger_document=TRIGGER_ANNUAL_LAB_PLAN,
        trigger_action=ACTION_ANNUAL_LAB_MONTH_DUE,
        variables={
            "plan_code": plan.plan_code,
            "plan_title": plan.title,
            "year_month": month.year_month,
            "month_title": month.title or month.year_month,
            "owner_user_name": month.owner_user_name or plan.owner_user_name or "—",
            "due_at": due_text,
            "detail_path": _annual_lab_plan_detail_path(plan.id),
        },
        context={
            "entity_type": ENTITY_TYPE,
            "entity_id": month.id,
            "owner_user_id": month.owner_user_id or plan.owner_user_id,
            "creator_user_id": plan.created_by,
        },
    )
    if not sent:
        logger.info(
            "年度例式下月提醒无匹配规则或接收人 tenant={} plan={} month={}",
            tenant_id,
            plan.plan_code,
            month.year_month,
        )
    return "sent"


register_reminder_handler(RULE_PREFIX, dispatch_annual_lab_plan_reminder)
register_reminder_preparer(prepare_annual_lab_plan_reminders)
