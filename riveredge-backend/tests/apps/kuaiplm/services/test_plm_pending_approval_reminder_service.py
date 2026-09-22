"""PLM 待审 24h 提醒登记测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiplm.constants.rd_project import RdDeliverableStatus
from apps.kuaiplm.services.plm_pending_approval_reminder_service import (
    APPROVAL_DELAY_HOURS,
    ENTITY_RD_DELIVERABLE,
    PlmPendingApprovalReminderService,
    dispatch_plm_pending_approval_reminder,
)


@pytest.mark.asyncio
async def test_schedule_uses_24h_delay():
    submitted_at = MagicMock(tzinfo=object())
    with patch(
        "apps.kuaiplm.services.plm_pending_approval_reminder_service.ReminderEventService.ensure_event",
        new_callable=AsyncMock,
    ) as ensure:
        await PlmPendingApprovalReminderService.schedule(
            1,
            entity_type=ENTITY_RD_DELIVERABLE,
            entity_id=7,
            entity_uuid="uuid-7",
            submitted_at=submitted_at,
            doc_code="规格书A",
            title="规格书A",
        )
        ensure.assert_awaited_once()
        assert ensure.await_args.kwargs["payload"]["delay_hours"] == APPROVAL_DELAY_HOURS


@pytest.mark.asyncio
async def test_dispatch_stops_when_deliverable_no_longer_submitted():
    event = MagicMock()
    event.id = 3
    event.entity_id = 9
    event.entity_type = ENTITY_RD_DELIVERABLE
    event.payload = {"entity_type": ENTITY_RD_DELIVERABLE, "delay_hours": 24}

    with patch(
        "apps.kuaiplm.services.plm_pending_approval_reminder_service.RdProjectDeliverable.filter"
    ) as q, patch(
        "apps.kuaiplm.services.plm_pending_approval_reminder_service.ReminderEventService.mark_stopped",
        new_callable=AsyncMock,
    ) as mark_stopped:
        q.return_value.first = AsyncMock(
            return_value=MagicMock(status=RdDeliverableStatus.APPROVED.value)
        )
        outcome = await dispatch_plm_pending_approval_reminder(1, event)
        assert outcome == "stopped"
        mark_stopped.assert_awaited_once()
