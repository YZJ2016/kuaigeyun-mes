"""audit_flow_guard 门控：流程已结束但单据仍待审时可补齐写回。"""

import pytest

from core.services.approval.audit_flow_guard import (
    assert_manual_approval_action_allowed,
    should_sync_doc_after_flow_completed,
)
from infra.exceptions.exceptions import BusinessLogicError


def test_manual_approve_allowed_when_flow_completed_approved():
    gate = {
        "has_pending_flow": False,
        "flow_completed_approved": True,
        "flow_completed_rejected": False,
    }
    assert_manual_approval_action_allowed(gate, doc_label="销售出库单", verb="审核")


def test_manual_approve_blocked_without_instance():
    gate = {
        "has_pending_flow": False,
        "flow_completed_approved": False,
        "flow_completed_rejected": False,
    }
    with pytest.raises(BusinessLogicError, match="无进行中的审批流程"):
        assert_manual_approval_action_allowed(gate, doc_label="销售出库单", verb="审核")


def test_should_sync_doc_after_flow_completed():
    approved_gate = {"flow_completed_approved": True, "flow_completed_rejected": False}
    rejected_gate = {"flow_completed_approved": False, "flow_completed_rejected": True}
    assert should_sync_doc_after_flow_completed(approved_gate, approve=True) is True
    assert should_sync_doc_after_flow_completed(approved_gate, approve=False) is False
    assert should_sync_doc_after_flow_completed(rejected_gate, approve=False) is True


def test_manual_reject_allowed_when_flow_completed_rejected():
    gate = {
        "has_pending_flow": False,
        "flow_completed_approved": False,
        "flow_completed_rejected": True,
    }
    assert_manual_approval_action_allowed(gate, doc_label="发货通知单", verb="驳回")


def test_approval_instance_finished_on_submit():
    from core.services.approval.audit_flow_guard import approval_instance_finished_on_submit

    class _Inst:
        status = "approved"

    assert approval_instance_finished_on_submit(_Inst()) is True
    assert approval_instance_finished_on_submit(type("X", (), {"status": "pending"})()) is False
