"""通用会签申请 8h 待审提醒（INF-03）— 5M / 物料申请 / 样品检验等。"""

from __future__ import annotations

from datetime import timedelta
from typing import Literal, Optional

from loguru import logger

from apps.kuaioa.models.form_request import KuaioaFormRequest
from apps.kuaioa.services.kuaioa_form_notification import (
    ACTION_FORM_APPROVAL_OVERDUE,
    TRIGGER_KUAIOA_FORM_REQUEST,
)
from core.models.reminder_event import ReminderEvent
from core.services.approval.approval_data_scope import (
    list_pending_approver_user_ids_for_entity,
)
from core.services.business.business_notification_service import (
    BusinessNotificationService,
)
from core.services.business.reminder_dispatch_service import register_reminder_handler
from core.services.business.reminder_event_service import ReminderEventService

ENTITY_TYPE = "kuaioa_form_request"
RULE_PREFIX = "kuaioa.form_request"
RULE_APPROVAL = f"{RULE_PREFIX}.approval"
CHANNEL_INTERNAL = "internal"
APPROVAL_DELAY_HOURS = 8


class KuaioaFormRequestReminderService:
    @staticmethod
    async def stop_all(tenant_id: int, request_id: int, *, reason: str) -> int:
        return await ReminderEventService.stop_future_for_entity(
            tenant_id,
            entity_type=ENTITY_TYPE,
            entity_id=request_id,
            reason=reason,
        )

    @staticmethod
    async def sync_after_submit(tenant_id: int, row: KuaioaFormRequest) -> None:
        if row.status != "pending" or not row.submitted_at:
            return
        await KuaioaFormRequestReminderService.stop_all(
            tenant_id, row.id, reason="重新提交"
        )
        if row.submitted_at.tzinfo is None:
            raise ValueError("submitted_at 必须是带时区的 UTC 时刻")
        planned_at = row.submitted_at + timedelta(hours=APPROVAL_DELAY_HOURS)
        await ReminderEventService.ensure_event(
            tenant_id,
            rule_id=f"{RULE_APPROVAL}:{row.id}",
            rule_code=RULE_APPROVAL,
            entity_type=ENTITY_TYPE,
            entity_id=row.id,
            entity_uuid=str(row.uuid),
            planned_at=planned_at,
            channel=CHANNEL_INTERNAL,
            payload={
                "delay_hours": APPROVAL_DELAY_HOURS,
                "business_type": row.business_type,
                "title": row.title,
                "request_code": row.request_code,
            },
        )

    @staticmethod
    async def sync_after_terminal(tenant_id: int, request_id: int, *, reason: str) -> None:
        await KuaioaFormRequestReminderService.stop_all(
            tenant_id, request_id, reason=reason
        )


async def dispatch_kuaioa_form_request_reminder(
    tenant_id: int, event: ReminderEvent
) -> Literal["sent", "stopped"]:
    row = await KuaioaFormRequest.filter(
        tenant_id=tenant_id, id=event.entity_id, deleted_at__isnull=True
    ).first()
    if not row:
        await ReminderEventService.mark_stopped(tenant_id, event.id, "申请单已删除")
        return "stopped"
    if row.status != "pending":
        await ReminderEventService.mark_stopped(tenant_id, event.id, "已不在待审")
        return "stopped"

    payload = event.payload or {}
    approver_ids = await list_pending_approver_user_ids_for_entity(
        tenant_id, ENTITY_TYPE, row.id
    )
    hours = int(payload.get("delay_hours") or APPROVAL_DELAY_HOURS)
    sent = await BusinessNotificationService.dispatch(
        tenant_id,
        trigger_document=TRIGGER_KUAIOA_FORM_REQUEST,
        trigger_action=ACTION_FORM_APPROVAL_OVERDUE,
        variables={
            "request_code": row.request_code or f"申请#{row.id}",
            "title": row.title or "",
            "business_type": row.business_type or "",
            "delay_hours": str(hours),
        },
        context={
            "entity_type": ENTITY_TYPE,
            "entity_id": row.id,
            "entity_uuid": str(row.uuid),
            "creator_user_id": row.created_by,
            "pending_approver_user_ids": approver_ids,
        },
    )
    if sent == 0:
        logger.warning(
            "通用会签待审超时无接收人 tenant={} request={} approvers={}",
            tenant_id,
            row.request_code,
            approver_ids,
        )
    return "sent"


register_reminder_handler(RULE_PREFIX, dispatch_kuaioa_form_request_reminder)
