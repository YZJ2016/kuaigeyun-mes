"""撤回后单据回草稿时，审批决策应收敛为 cancelled，避免待审列表残留。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.services.approval.approval_instance_service import ApprovalInstanceService


@pytest.mark.asyncio
async def test_purchase_request_draft_maps_to_cancelled() -> None:
    row = SimpleNamespace(status="DRAFT")
    with patch(
        "apps.kuaizhizao.models.purchase_requisition.PurchaseRequisition.get_or_none",
        new=AsyncMock(return_value=row),
    ):
        decision = await ApprovalInstanceService._entity_audit_decision(
            tenant_id=1,
            entity_type="purchase_request",
            entity_id=99,
        )
    assert decision == "cancelled"


@pytest.mark.asyncio
async def test_purchase_request_pending_review_stays_open() -> None:
    row = SimpleNamespace(status="PENDING_REVIEW")
    with patch(
        "apps.kuaizhizao.models.purchase_requisition.PurchaseRequisition.get_or_none",
        new=AsyncMock(return_value=row),
    ):
        decision = await ApprovalInstanceService._entity_audit_decision(
            tenant_id=1,
            entity_type="purchase_request",
            entity_id=99,
        )
    assert decision is None


@pytest.mark.asyncio
async def test_reconcile_cancels_when_decision_cancelled() -> None:
    inst = SimpleNamespace(
        id=7,
        status="pending",
        data={"entity_type": "purchase_request", "entity_id": 99},
        current_approver_id=3,
        completed_at=None,
        save=AsyncMock(),
    )
    task = SimpleNamespace(approval_instance=inst)

    class _Query:
        def __init__(self) -> None:
            self.updated = None

        def prefetch_related(self, *_a, **_k):
            return self

        async def all(self):
            return [task]

        async def update(self, **kwargs):
            self.updated = kwargs

    q = _Query()

    with (
        patch(
            "core.services.approval.approval_instance_service.ApprovalTask.filter",
            return_value=q,
        ),
        patch.object(
            ApprovalInstanceService,
            "_entity_audit_decision",
            new=AsyncMock(return_value="cancelled"),
        ),
    ):
        closed = await ApprovalInstanceService.reconcile_orphaned_approval_tasks(1, 3)

    assert closed == 1
    assert inst.status == "cancelled"
    assert inst.current_approver_id is None
    assert q.updated == {"status": "cancelled"}
    inst.save.assert_awaited()
