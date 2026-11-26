"""审批企微可更新卡片：发送落库与失效。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.messaging import approval_wecom_card_service as svc
from core.services.messaging.wecom_message_service import WeComMessageSendResult


@pytest.mark.asyncio
async def test_send_and_track_prefers_template_card_with_response_code():
    with (
        patch.object(
            svc,
            "resolve_wecom_recipient_userids",
            new=AsyncMock(return_value=(["ww_user"], None)),
        ),
        patch.object(
            svc,
            "invalidate_approval_wecom_cards_for_users",
            new=AsyncMock(return_value=0),
        ),
        patch.object(
            svc,
            "send_wecom_template_card_message",
            new=AsyncMock(
                return_value=WeComMessageSendResult(
                    ok=True, msgid="mid-1", response_code="rc-1"
                )
            ),
        ),
        patch.object(svc.ApprovalWecomCard, "create", new=AsyncMock()) as create_mock,
    ):
        ok = await svc.send_and_track_approval_pending_card(
            tenant_id=1,
            approval_instance_id=9,
            recipient_user_id=3,
            subject="待审批：采购申请",
            content="请审批",
            document_url="https://erp.example.com/mobile/approval/detail?uuid=x&tenant_id=1",
        )

    assert ok is True
    create_mock.assert_awaited_once()
    kwargs = create_mock.await_args.kwargs
    assert kwargs["card_kind"] == "template_card"
    assert kwargs["response_code"] == "rc-1"
    assert kwargs["msgid"] == "mid-1"


@pytest.mark.asyncio
async def test_send_and_track_keeps_msgid_when_no_response_code():
    with (
        patch.object(
            svc,
            "resolve_wecom_recipient_userids",
            new=AsyncMock(return_value=(["ww_user"], None)),
        ),
        patch.object(
            svc,
            "invalidate_approval_wecom_cards_for_users",
            new=AsyncMock(return_value=0),
        ),
        patch.object(
            svc,
            "send_wecom_template_card_message",
            new=AsyncMock(return_value=WeComMessageSendResult(ok=True, msgid="mid-t")),
        ),
        patch.object(
            svc,
            "send_wecom_textcard_message_result",
            new=AsyncMock(),
        ) as textcard_mock,
        patch.object(svc.ApprovalWecomCard, "create", new=AsyncMock()) as create_mock,
    ):
        ok = await svc.send_and_track_approval_pending_card(
            tenant_id=1,
            approval_instance_id=9,
            recipient_user_id=3,
            subject="待审批",
            content="正文",
            document_url="https://erp.example.com/mobile/?tenant_id=1",
        )

    assert ok is True
    textcard_mock.assert_not_awaited()
    kwargs = create_mock.await_args.kwargs
    assert kwargs["card_kind"] == "template_card"
    assert kwargs["msgid"] == "mid-t"
    assert kwargs["response_code"] is None
    assert kwargs["task_id"]


@pytest.mark.asyncio
async def test_invalidate_uses_button_replace_for_template_card():
    row = MagicMock()
    row.id = 1
    row.tenant_id = 1
    row.approval_instance_id = 9
    row.card_kind = "template_card"
    row.response_code = "rc-1"
    row.wecom_userid = "ww_user"
    row.task_id = "task-1"
    row.subject = "待审批"
    row.document_url = "https://erp.example.com/x"
    row.save = AsyncMock()

    qs = MagicMock()
    qs.filter = MagicMock(return_value=qs)
    qs.all = AsyncMock(return_value=[row])
    with (
        patch.object(svc.ApprovalWecomCard, "filter", return_value=qs),
        patch.object(svc, "update_wecom_template_card", new=AsyncMock(return_value=True)) as upd,
    ):
        n = await svc.invalidate_approval_wecom_cards(
            tenant_id=1,
            approval_instance_id=9,
            status_label="已撤回",
        )

    assert n == 1
    upd.assert_awaited()
    upd_kwargs = upd.await_args.kwargs
    assert upd_kwargs.get("template_card") is not None
    assert row.status == "updated"
    assert row.response_code is None


def test_parse_approval_instance_id():
    assert svc.parse_approval_instance_id({"approval_instance_id": "12"}) == 12
    assert svc.parse_approval_instance_id({"approval_instance_id": "x"}) is None
    assert svc.parse_approval_instance_id(None) is None


@pytest.mark.asyncio
async def test_invalidate_soft_skip_recall_without_response_code():
    row = MagicMock()
    row.id = 1
    row.tenant_id = 1
    row.approval_instance_id = 9
    row.card_kind = "template_card"
    row.response_code = None
    row.wecom_userid = "ww_user"
    row.msgid = "mid-1"
    row.save = AsyncMock()

    qs = MagicMock()
    qs.filter = MagicMock(return_value=qs)
    qs.all = AsyncMock(return_value=[row])
    with (
        patch.object(svc.ApprovalWecomCard, "filter", return_value=qs),
        patch.object(svc, "recall_wecom_message", new=AsyncMock()) as recall,
    ):
        n = await svc.invalidate_approval_wecom_cards_for_users(
            tenant_id=1,
            approval_instance_id=9,
            recipient_user_ids=[3],
            status_label="已更新",
            recall_if_no_response_code=False,
        )

    assert n == 1
    recall.assert_not_awaited()
    assert row.status == "superseded"
