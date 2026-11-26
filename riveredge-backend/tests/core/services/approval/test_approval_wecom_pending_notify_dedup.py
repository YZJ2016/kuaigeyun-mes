"""企微待办：节点推进后勿重复发待审通知。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.services.approval.approval_instance_service import ApprovalInstanceService


@pytest.mark.asyncio
async def test_action_notification_skips_pending_notify_when_flag_set():
    instance = SimpleNamespace(
        id=1,
        status="pending",
        current_approver_id=99,
        title="测试单",
        submitter_id=10,
        uuid="u-1",
        fetch_related=AsyncMock(),
        process=SimpleNamespace(name="流程A"),
    )
    action = SimpleNamespace(action="approve", comment="ok", created_at=None)

    with patch.object(
        ApprovalInstanceService,
        "_send_internal_to_user",
        new=AsyncMock(),
    ), patch.object(
        ApprovalInstanceService,
        "_sync_approval_wecom_cards_after_action",
        new=AsyncMock(),
    ), patch.object(
        ApprovalInstanceService,
        "_notify_pending_approvers",
        new=AsyncMock(),
    ) as notify_pending:
        await ApprovalInstanceService._send_approval_action_notification(
            tenant_id=2,
            approval_instance=instance,
            action=action,
            user_id=5,
            old_status="pending",
            old_current_approver_id=21,
            skip_pending_approver_notify=True,
        )

    notify_pending.assert_not_awaited()


@pytest.mark.asyncio
async def test_action_notification_still_notifies_pending_on_transfer_path():
    instance = SimpleNamespace(
        id=1,
        status="pending",
        current_approver_id=88,
        title="测试单",
        submitter_id=10,
        uuid="u-1",
        fetch_related=AsyncMock(),
        process=SimpleNamespace(name="流程A"),
    )
    action = SimpleNamespace(action="transfer", comment=None, created_at=None)

    with patch(
        "core.services.approval.approval_instance_service.User.filter",
        return_value=SimpleNamespace(first=AsyncMock(return_value=None)),
    ), patch.object(
        ApprovalInstanceService,
        "_send_internal_to_user",
        new=AsyncMock(),
    ), patch.object(
        ApprovalInstanceService,
        "_sync_approval_wecom_cards_after_action",
        new=AsyncMock(),
    ), patch.object(
        ApprovalInstanceService,
        "_notify_pending_approvers",
        new=AsyncMock(),
    ) as notify_pending:
        await ApprovalInstanceService._send_approval_action_notification(
            tenant_id=2,
            approval_instance=instance,
            action=action,
            user_id=5,
            old_status="pending",
            old_current_approver_id=21,
            skip_pending_approver_notify=False,
        )

    notify_pending.assert_awaited_once()