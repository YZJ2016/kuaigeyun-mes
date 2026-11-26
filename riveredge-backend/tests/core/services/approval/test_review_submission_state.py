"""未提交审核态与 capabilities 门禁对齐。"""

from __future__ import annotations

from types import SimpleNamespace

from apps.kuaizhizao.services.document_action_policy.sales_return import (
    derive_sales_return_capabilities,
)
from core.services.approval.review_submission_state import is_effective_review_draft


def test_false_pending_treated_as_draft_for_capabilities():
    doc = SimpleNamespace(status="待退货", review_status="待审核")
    caps = derive_sales_return_capabilities(
        doc,
        has_items=True,
        audit_required=True,
        review_submitted=False,
    )
    assert caps.delete.allowed is True
    assert caps.submit.allowed is True


def test_submitted_pending_not_draft():
    assert is_effective_review_draft("待审核", review_submitted=True) is False
