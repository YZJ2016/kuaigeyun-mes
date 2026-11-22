from types import SimpleNamespace
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.models.approval_task import ApprovalTask
from core.services.approval.approval_instance_service import ApprovalInstanceService
from infra.exceptions.exceptions import ValidationError


def _pending_instance():
    return SimpleNamespace(
        id=1,
        tenant_id=2,
        data={"document_owner_id": 7},
        submitter_id=99,
        status="pending",
        current_approver_id=None,
        save=AsyncMock(),
        process=SimpleNamespace(nodes={}),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "approvers, remaining, records_others_waiting",
    [([7], [7], False), ([7, 8], [8], True), ([99], [99], False)],
)
async def test_creator_skips_only_when_others_remain(approvers, remaining, records_others_waiting):
    instance = _pending_instance()
    node = {"id": "review", "type": "approval", "data": {"emptyApproverPolicy": "auto_pass"}}
    with ExitStack() as stack:
        stack.enter_context(patch.object(ApprovalInstanceService, "_resolve_node_approvers", AsyncMock(return_value=approvers)))
        skip = stack.enter_context(patch.object(ApprovalInstanceService, "_auto_pass_empty_approval_node", AsyncMock(return_value=[])))
        history = stack.enter_context(patch.object(ApprovalInstanceService, "_create_approval_history", AsyncMock()))
        stack.enter_context(patch.object(ApprovalInstanceService, "_node_would_auto_pass_same_prior_approver", AsyncMock(return_value=True)))
        sync = stack.enter_context(patch.object(ApprovalInstanceService, "_sync_node_approver_tasks", AsyncMock(return_value=[])))
        await ApprovalInstanceService._create_node_tasks(2, instance, node)

    skip.assert_not_awaited()
    assert sync.call_args.args[3] == remaining
    assert instance.current_approver_id == remaining[0]
    assert instance.status == "pending"
    if records_others_waiting:
        history.assert_awaited()
    else:
        history.assert_not_awaited()


@pytest.mark.asyncio
async def test_sole_creator_does_not_auto_pass_document():
    instance = _pending_instance()
    node = {"id": "final", "type": "approval", "data": {"emptyApproverPolicy": "block"}}
    with ExitStack() as stack:
        stack.enter_context(patch.object(ApprovalInstanceService, "_resolve_node_approvers", AsyncMock(return_value=[7])))
        skip = stack.enter_context(patch.object(ApprovalInstanceService, "_auto_pass_empty_approval_node", AsyncMock(return_value=[])))
        sync = stack.enter_context(patch.object(ApprovalInstanceService, "_sync_node_approver_tasks", AsyncMock(return_value=[])))
        stack.enter_context(patch.object(ApprovalInstanceService, "_create_approval_history", AsyncMock()))
        await ApprovalInstanceService._create_node_tasks(2, instance, node)

    skip.assert_not_awaited()
    assert sync.call_args.args[3] == [7]
    assert instance.status == "pending"
    assert instance.current_approver_id == 7


@pytest.mark.asyncio
async def test_same_approver_second_level_does_not_auto_pass():
    instance = _pending_instance()
    instance.data = {}
    node = {"id": "n2", "type": "approval", "data": {}}
    with ExitStack() as stack:
        stack.enter_context(patch.object(ApprovalInstanceService, "_document_creator_for_self_skip", AsyncMock(return_value=None)))
        stack.enter_context(patch.object(ApprovalInstanceService, "_resolve_node_approvers", AsyncMock(return_value=[8])))
        skip = stack.enter_context(patch.object(ApprovalInstanceService, "_auto_pass_empty_approval_node", AsyncMock(return_value=[])))
        stack.enter_context(
            patch.object(
                ApprovalInstanceService,
                "_node_would_auto_pass_same_prior_approver",
                AsyncMock(return_value=True),
            )
        )
        sync = stack.enter_context(patch.object(ApprovalInstanceService, "_sync_node_approver_tasks", AsyncMock(return_value=[])))
        await ApprovalInstanceService._create_node_tasks(2, instance, node)

    skip.assert_not_awaited()
    assert sync.call_args.args[3] == [8]
    assert instance.status == "pending"


@pytest.mark.asyncio
async def test_empty_approver_block_still_rejects():
    instance = _pending_instance()
    node = {"id": "review", "type": "approval", "data": {"emptyApproverPolicy": "block"}}
    with patch.object(ApprovalInstanceService, "_resolve_node_approvers", AsyncMock(return_value=[])), patch.object(
        ApprovalInstanceService, "_auto_pass_empty_approval_node", AsyncMock(return_value=[])
    ) as skip:
        with pytest.raises(ValidationError):
            await ApprovalInstanceService._create_node_tasks(2, instance, node)
    skip.assert_not_awaited()
    assert instance.status == "pending"


@pytest.mark.asyncio
async def test_sync_keeps_pending_task_for_sole_creator():
    instance = SimpleNamespace(id=1, data={"document_owner_id": 7})
    node = {"id": "review", "type": "approval", "data": {}}
    created: list[dict] = []

    async def _create(**kwargs):
        created.append(kwargs)
        return SimpleNamespace(**kwargs)

    pending = MagicMock()
    pending.all = AsyncMock(return_value=[])
    with patch.object(ApprovalTask, "filter", return_value=pending), patch.object(
        ApprovalTask, "create", _create
    ), patch(
        "core.services.approval.approval_advanced_actions.ApprovalAdvancedActions.apply_task_due_at",
        AsyncMock(),
    ):
        await ApprovalInstanceService._sync_node_approver_tasks(
            2, instance, node, approvers=[7]
        )
    assert created[0]["approver_id"] == 7


@pytest.mark.asyncio
async def test_missing_creator_does_not_skip_submitter():
    instance = SimpleNamespace(data={}, submitter_id=99)
    assert await ApprovalInstanceService._document_creator_for_self_skip(instance) is None
