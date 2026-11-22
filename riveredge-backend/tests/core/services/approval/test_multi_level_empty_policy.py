"""multi_level_manager 空名单按 emptyApproverPolicy 原值处理，block 不得改写成 auto_pass。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.services.approval.approval_instance_service import ApprovalInstanceService
from infra.exceptions.exceptions import ValidationError


def _instance():
    return SimpleNamespace(
        id=1,
        tenant_id=2,
        data={},
        submitter_id=10,
        status="pending",
        current_approver_id=None,
        save=AsyncMock(),
        process=SimpleNamespace(nodes={}),
    )


def _node(policy: str):
    return {
        "id": "lvl3",
        "type": "approval",
        "data": {
            "approverType": "multi_level_manager",
            "managerLevel": 3,
            "emptyApproverPolicy": policy,
        },
    }


@pytest.mark.asyncio
async def test_multi_level_block_raises_when_hierarchy_is_short():
    with patch.object(
        ApprovalInstanceService,
        "_resolve_submitter_department_manager_at_level",
        new=AsyncMock(return_value=[]),
    ), patch.object(
        ApprovalInstanceService,
        "_auto_pass_empty_approval_node",
        new=AsyncMock(return_value=[]),
    ) as skip:
        with pytest.raises(ValidationError):
            await ApprovalInstanceService._create_node_tasks(2, _instance(), _node("block"))
    skip.assert_not_awaited()


@pytest.mark.asyncio
async def test_multi_level_auto_pass_still_skips_when_hierarchy_is_short():
    with patch.object(
        ApprovalInstanceService,
        "_resolve_submitter_department_manager_at_level",
        new=AsyncMock(return_value=[]),
    ), patch.object(
        ApprovalInstanceService,
        "_auto_pass_empty_approval_node",
        new=AsyncMock(return_value=[]),
    ) as skip:
        await ApprovalInstanceService._create_node_tasks(2, _instance(), _node("auto_pass"))
    skip.assert_awaited()


@pytest.mark.asyncio
async def test_multi_level_block_is_not_treated_as_empty_auto_pass():
    with patch.object(
        ApprovalInstanceService,
        "_resolve_submitter_department_manager_at_level",
        new=AsyncMock(return_value=[]),
    ):
        would = await ApprovalInstanceService._node_would_auto_pass_when_empty(
            2, _node("block"), _instance()
        )
    assert would is False


@pytest.mark.asyncio
async def test_multi_level_auto_pass_policy_still_counts_as_empty_auto_pass():
    with patch.object(
        ApprovalInstanceService,
        "_resolve_submitter_department_manager_at_level",
        new=AsyncMock(return_value=[]),
    ):
        would = await ApprovalInstanceService._node_would_auto_pass_when_empty(
            2, _node("auto_pass"), _instance()
        )
    assert would is True
