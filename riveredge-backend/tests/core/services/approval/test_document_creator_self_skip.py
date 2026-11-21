from types import SimpleNamespace
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

from core.services.approval.approval_instance_service import ApprovalInstanceService


@pytest.mark.asyncio
@pytest.mark.parametrize("approvers, remaining", [([7], []), ([7, 8], [8]), ([99], [99])])
async def test_creator_skips_only_own_approval(approvers, remaining):
    instance = SimpleNamespace(
        id=1,
        tenant_id=2,
        data={"document_owner_id": 7},
        submitter_id=99,
        status="pending",
        current_approver_id=None,
        save=AsyncMock(),
    )
    node = {"id": "review", "type": "approval", "data": {}}
    with ExitStack() as stack:
        stack.enter_context(patch.object(ApprovalInstanceService, "_resolve_node_approvers", AsyncMock(return_value=approvers)))
        skip = stack.enter_context(patch.object(ApprovalInstanceService, "_auto_pass_empty_approval_node", AsyncMock(return_value=[])))
        stack.enter_context(patch.object(ApprovalInstanceService, "_create_approval_history", AsyncMock()))
        stack.enter_context(patch.object(ApprovalInstanceService, "_node_would_auto_pass_same_prior_approver", AsyncMock(return_value=False)))
        sync = stack.enter_context(patch.object(ApprovalInstanceService, "_sync_node_approver_tasks", AsyncMock(return_value=[])))
        await ApprovalInstanceService._create_node_tasks(2, instance, node)

    if not remaining:
        skip.assert_awaited_once()
        assert skip.call_args.kwargs["action_by"] == 7
        sync.assert_not_awaited()
    else:
        skip.assert_not_awaited()
        assert sync.call_args.args[3] == remaining
        assert instance.current_approver_id == remaining[0]


@pytest.mark.asyncio
async def test_missing_creator_does_not_skip_submitter():
    instance = SimpleNamespace(data={}, submitter_id=99)
    assert await ApprovalInstanceService._document_creator_for_self_skip(instance) is None
