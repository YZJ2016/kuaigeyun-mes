"""工序委外工序发料 capability。"""

from types import SimpleNamespace

from apps.kuaizhizao.services.document_action_policy.outsource_order import (
    derive_outsource_order_push_issue_cap,
)


def test_push_issue_allowed_in_progress():
    row = SimpleNamespace(status="in_progress")
    cap = derive_outsource_order_push_issue_cap(row)
    assert cap.allowed is True


def test_push_issue_blocked_completed():
    row = SimpleNamespace(status="completed")
    cap = derive_outsource_order_push_issue_cap(row)
    assert cap.allowed is False