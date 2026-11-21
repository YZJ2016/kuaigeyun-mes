"""节点推进后应通知新待办审批人（任务制审批）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.services.approval.approval_instance_service import ApprovalInstanceService


@pytest.mark.asyncio
async def test_create_node_tasks_spawns_notify_when_flag_set():
    instance = SimpleNamespace(
        id=99,
        status="pending",
        current_approver_id=None,
        save=AsyncMock(),
        process=SimpleNamespace(nodes={}),
    )
    node = {"id": "n2", "type": "approval", "data": {"label": "二审"}}
    approvers = [68]

    with patch.object(
        ApprovalInstanceService,
        "_document_creator_for_self_skip",
        new=AsyncMock(return_value=None),
    ), patch.object(
        ApprovalInstanceService,
        "_node_would_auto_pass_same_prior_approver",
        new=AsyncMock(return_value=False),
    ), patch.object(
        ApprovalInstanceService,
        "_resolve_node_approvers",
        new=AsyncMock(return_value=approvers),
    ), patch.object(
        ApprovalInstanceService,
        "_sync_node_approver_tasks",
        new=AsyncMock(return_value=[SimpleNamespace(id=1)]),
    ), patch.object(
        ApprovalInstanceService,
        "_spawn_pending_node_notifications",
    ) as spawn:
        await ApprovalInstanceService._create_node_tasks(
            2,
            instance,
            node,
            notify_pending_approvers=True,
        )

    spawn.assert_called_once_with(
        tenant_id=2,
        approval_instance_id=99,
        approver_ids=[68],
    )


@pytest.mark.asyncio
async def test_create_node_tasks_does_not_notify_on_bootstrap_default():
    instance = SimpleNamespace(
        id=99,
        status="pending",
        current_approver_id=None,
        save=AsyncMock(),
        process=SimpleNamespace(nodes={}),
    )
    node = {"id": "n1", "type": "approval", "data": {}}

    with patch.object(
        ApprovalInstanceService,
        "_document_creator_for_self_skip",
        new=AsyncMock(return_value=None),
    ), patch.object(
        ApprovalInstanceService,
        "_node_would_auto_pass_same_prior_approver",
        new=AsyncMock(return_value=False),
    ), patch.object(
        ApprovalInstanceService,
        "_resolve_node_approvers",
        new=AsyncMock(return_value=[21]),
    ), patch.object(
        ApprovalInstanceService,
        "_sync_node_approver_tasks",
        new=AsyncMock(return_value=[]),
    ), patch.object(
        ApprovalInstanceService,
        "_spawn_pending_node_notifications",
    ) as spawn:
        await ApprovalInstanceService._create_node_tasks(2, instance, node)

    spawn.assert_not_called()


@pytest.mark.asyncio
async def test_advance_passes_notify_flag_to_create_node_tasks():
    graph = {
        "nodes": [
            {"id": "n1", "type": "approval"},
            {"id": "n2", "type": "approval"},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "end"},
        ],
    }
    instance = SimpleNamespace(
        id=1,
        status="pending",
        current_node="n1",
        current_approver_id=21,
        completed_at=None,
        process=SimpleNamespace(nodes=graph),
        save=AsyncMock(),
        fetch_related=AsyncMock(),
    )
    create = AsyncMock(return_value=[])

    with patch(
        "core.services.approval.approval_instance_service.ApprovalTask.filter",
        return_value=SimpleNamespace(update=AsyncMock(return_value=1)),
    ), patch.object(
        ApprovalInstanceService,
        "_get_next_node",
        return_value=graph["nodes"][1],
    ), patch.object(
        ApprovalInstanceService,
        "_create_node_tasks",
        new=create,
    ):
        await ApprovalInstanceService._advance_instance_after_node_completion(
            2, instance, "approved", route_action_by=21
        )

    assert create.await_count == 1
    _args, kwargs = create.call_args
    assert kwargs.get("notify_pending_approvers") is True
