"""B-03: 完成回调失败留痕 + revoke_noop + revoke 补齐门控。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.approval.audit_flow_guard import assert_manual_approval_action_allowed


def test_revoke_verb_allowed_when_flow_completed_approved():
    gate = {
        "has_pending_flow": False,
        "flow_completed_approved": True,
        "flow_completed_rejected": False,
    }
    assert_manual_approval_action_allowed(gate, doc_label="销售订单", verb="反审核")


@pytest.mark.asyncio
async def test_handle_approval_completion_records_writeback_failure():
    from core.services.approval.approval_instance_service import ApprovalInstanceService

    instance = MagicMock()
    instance.id = 11
    instance.status = "approved"
    instance.data = {"entity_type": "sales_order", "entity_id": 99}
    instance.submitter_id = 1
    instance.save = AsyncMock()

    hist_q = MagicMock()
    hist_q.order_by.return_value.first = AsyncMock(return_value=None)

    async def _failing_handler():
        raise RuntimeError("credit limit exceeded")

    with (
        patch(
            "core.services.approval.approval_instance_service.ApprovalHistory.filter",
            return_value=hist_q,
        ),
        patch(
            "apps.kuaizhizao.services.sales_order_service.SalesOrderService"
        ) as mock_svc_cls,
    ):
        mock_svc = MagicMock()
        mock_svc.approve_sales_order = AsyncMock(side_effect=RuntimeError("credit limit exceeded"))
        mock_svc_cls.return_value = mock_svc
        await ApprovalInstanceService._handle_approval_completion(1, instance)

    assert "writeback_failure" in instance.data
    assert "credit limit exceeded" in instance.data["writeback_failure"]["error"]
    instance.save.assert_awaited()
    _ = _failing_handler


@pytest.mark.asyncio
async def test_cancel_approval_writes_revoke_noop_on_completed():
    from core.services.approval.approval_instance_service import ApprovalInstanceService

    instance = MagicMock()
    instance.id = 22
    instance.status = "approved"
    instance.current_node = "end"

    with (
        patch.object(
            ApprovalInstanceService,
            "get_instance_by_entity",
            new=AsyncMock(return_value=instance),
        ),
        patch.object(
            ApprovalInstanceService,
            "_create_approval_history",
            new=AsyncMock(),
        ) as hist,
    ):
        ok = await ApprovalInstanceService.cancel_approval(
            tenant_id=1,
            entity_type="sales_order",
            entity_id=99,
            operator_id=5,
        )

    assert ok is False
    hist.assert_awaited_once()
    kwargs = hist.await_args.kwargs
    assert kwargs["action"] == "revoke_noop"
