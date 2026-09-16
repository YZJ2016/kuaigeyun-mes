"""年度例式实验下月任务提醒登记测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiplm.models.annual_lab_plan import (
    MONTH_STATUS_COMPLETED,
    MONTH_STATUS_PENDING,
    PLAN_STATUS_APPROVED,
    PLAN_STATUS_DRAFT,
)
from apps.kuaiplm.services.annual_lab_plan_reminder_service import (
    RULE_MONTH_DUE,
    AnnualLabPlanReminderService,
    _month_remind_at,
    dispatch_annual_lab_plan_reminder,
)


def test_month_remind_at_first_day_site_10am():
    planned = _month_remind_at("2026-10")
    assert planned is not None
    assert planned.tzinfo is not None


@pytest.mark.asyncio
async def test_ensure_month_reminder_skips_completed():
    plan = MagicMock()
    plan.id = 1
    plan.status = PLAN_STATUS_APPROVED
    month = MagicMock()
    month.id = 8
    month.uuid = "uuid-8"
    month.month_status = MONTH_STATUS_COMPLETED
    month.year_month = "2026-10"

    with patch(
        "apps.kuaiplm.services.annual_lab_plan_reminder_service.AnnualLabPlanReminderService.stop_month",
        new_callable=AsyncMock,
    ) as stop_month, patch(
        "apps.kuaiplm.services.annual_lab_plan_reminder_service.ReminderEventService.ensure_event",
        new_callable=AsyncMock,
    ) as ensure:
        await AnnualLabPlanReminderService.ensure_month_reminder(1, plan, month)
        stop_month.assert_awaited_once()
        ensure.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_month_reminder_registers_future_event():
    plan = MagicMock()
    plan.id = 1
    plan.status = PLAN_STATUS_APPROVED
    month = MagicMock()
    month.id = 9
    month.uuid = "uuid-9"
    month.month_status = MONTH_STATUS_PENDING
    month.year_month = "2099-12"

    with patch(
        "apps.kuaiplm.services.annual_lab_plan_reminder_service.ReminderEventService.ensure_event",
        new_callable=AsyncMock,
    ) as ensure:
        await AnnualLabPlanReminderService.ensure_month_reminder(1, plan, month)
        ensure.assert_awaited_once()
        kwargs = ensure.await_args.kwargs
        assert kwargs["rule_code"] == RULE_MONTH_DUE
        assert kwargs["entity_id"] == 9


@pytest.mark.asyncio
async def test_sync_plan_stops_when_not_approved():
    with patch(
        "apps.kuaiplm.services.annual_lab_plan_reminder_service.AnnualLabPlan.filter"
    ) as q, patch(
        "apps.kuaiplm.services.annual_lab_plan_reminder_service.AnnualLabPlanReminderService.stop_plan",
        new_callable=AsyncMock,
    ) as stop_plan:
        q.return_value.first = AsyncMock(
            return_value=MagicMock(status=PLAN_STATUS_DRAFT, id=3)
        )
        await AnnualLabPlanReminderService.sync_plan(1, 3)
        stop_plan.assert_awaited_once_with(1, 3, reason="计划未批准或已关闭")


@pytest.mark.asyncio
async def test_dispatch_stops_when_month_completed():
    event = MagicMock()
    event.id = 21
    event.entity_id = 4
    event.rule_code = RULE_MONTH_DUE
    event.payload = {}

    month = MagicMock()
    month.id = 4
    month.plan_id = 2
    month.month_status = MONTH_STATUS_COMPLETED
    month.year_month = "2026-10"

    plan = MagicMock()
    plan.status = PLAN_STATUS_APPROVED

    with patch(
        "apps.kuaiplm.services.annual_lab_plan_reminder_service.AnnualLabPlanMonth.filter"
    ) as month_q, patch(
        "apps.kuaiplm.services.annual_lab_plan_reminder_service.AnnualLabPlan.filter"
    ) as plan_q, patch(
        "apps.kuaiplm.services.annual_lab_plan_reminder_service.ReminderEventService.mark_stopped",
        new_callable=AsyncMock,
    ):
        month_q.return_value.first = AsyncMock(return_value=month)
        plan_q.return_value.first = AsyncMock(return_value=plan)
        outcome = await dispatch_annual_lab_plan_reminder(1, event)
        assert outcome == "stopped"


@pytest.mark.asyncio
async def test_dispatch_month_due_sends_notification():
    event = MagicMock()
    event.id = 22
    event.entity_id = 5
    event.rule_code = RULE_MONTH_DUE
    event.payload = {}

    month = MagicMock()
    month.id = 5
    month.plan_id = 2
    month.month_status = MONTH_STATUS_PENDING
    month.year_month = "2026-11"
    month.title = "11月例试"
    month.owner_user_id = 42
    month.owner_user_name = "刘月皓"
    month.due_at = datetime(2026, 11, 30, 15, 59, 59, tzinfo=timezone.utc)

    plan = MagicMock()
    plan.id = 2
    plan.status = PLAN_STATUS_APPROVED
    plan.plan_code = "ALP2026001"
    plan.title = "2026年度例试"
    plan.owner_user_id = 42
    plan.owner_user_name = "刘月皓"
    plan.created_by = 7

    with patch(
        "apps.kuaiplm.services.annual_lab_plan_reminder_service.AnnualLabPlanMonth.filter"
    ) as month_q, patch(
        "apps.kuaiplm.services.annual_lab_plan_reminder_service.AnnualLabPlan.filter"
    ) as plan_q, patch(
        "apps.kuaiplm.services.annual_lab_plan_reminder_service.dispatch_kuaiplm_notification",
        new_callable=AsyncMock,
        return_value=1,
    ) as dispatch:
        month_q.return_value.first = AsyncMock(return_value=month)
        plan_q.return_value.first = AsyncMock(return_value=plan)
        outcome = await dispatch_annual_lab_plan_reminder(1, event)
        assert outcome == "sent"
        dispatch.assert_awaited_once()
        assert dispatch.await_args.kwargs["trigger_action"] == "month_due"
