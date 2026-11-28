"""其他费用支出申请 capabilities（审核看 review_status；Approved 才可下推支出）"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from infra.exceptions.exceptions import BusinessLogicError

from apps.kuaicaiwu.services.document_action_policy.other_expense import (
    is_other_expense_approved_status,
    is_other_expense_cancelled_status,
)
from apps.kuaizhizao.services.document_action_policy.types import (
    ActionCapability,
    CAPABILITY_REASON_MESSAGES,
)

_EDITABLE_REVIEW = frozenset({"", "草稿", "draft", "驳回", "rejected", "已驳回"})
_PENDING_REVIEW = frozenset({
    "待审核",
    "pending_review",
    "PENDING_REVIEW",
    "pending_approval",
    "已提交",
    "pending",
})
_APPROVED_REVIEW = frozenset({"approved", "已审核", "审核通过", "已通过", "通过"})


def _cap(allowed: bool, reason: Optional[str] = None) -> ActionCapability:
    return ActionCapability(allowed=allowed, reason=reason if not allowed else None)


def _review(row: Any) -> str:
    return str(getattr(row, "review_status", "") or "").strip()


def derive_other_expense_application_capabilities(
    row: Any,
    *,
    has_linked_expense: bool = False,
) -> dict[str, ActionCapability]:
    st = str(getattr(row, "status", "") or "")
    review = _review(row)
    remaining = Decimal(str(getattr(row, "remaining_amount", 0) or 0))
    pushed = Decimal(str(getattr(row, "pushed_amount", 0) or 0))
    cancelled = is_other_expense_cancelled_status(st)

    editable = review in _EDITABLE_REVIEW and not cancelled
    submitted = review == "SUBMITTED" and not cancelled
    pending = review in _PENDING_REVIEW and not cancelled
    approved_review = review in _APPROVED_REVIEW
    approved_biz = is_other_expense_approved_status(st)

    update_ok = editable
    delete_ok = editable and pushed <= 0
    submit_ok = editable
    submit_review_ok = submitted
    approve_ok = pending
    withdraw_ok = submitted or pending
    push_ok = (approved_review or approved_biz) and remaining > 0 and not cancelled

    revoke_ok = (approved_review or approved_biz) and pushed <= 0 and not has_linked_expense and not cancelled
    revoke_reason = None
    if has_linked_expense or pushed > 0:
        revoke_reason = "other_expense_application.revoke_approval.has_expense"
    elif not (approved_review or approved_biz):
        revoke_reason = "other_expense_application.revoke_approval.not_allowed"

    return {
        "update": _cap(update_ok, "other_expense_application.update.not_allowed" if not update_ok else None),
        "delete": _cap(delete_ok, "other_expense_application.delete.not_allowed" if not delete_ok else None),
        "submit": _cap(submit_ok, "other_expense_application.submit.not_allowed" if not submit_ok else None),
        "submit_review": _cap(
            submit_review_ok,
            "other_expense_application.submit_review.not_allowed" if not submit_review_ok else None,
        ),
        "approve": _cap(approve_ok, "other_expense_application.approve.not_allowed" if not approve_ok else None),
        "reject": _cap(approve_ok, "other_expense_application.approve.not_allowed" if not approve_ok else None),
        "withdraw_submit": _cap(
            withdraw_ok,
            "other_expense_application.withdraw.not_allowed" if not withdraw_ok else None,
        ),
        "revoke_approval": _cap(revoke_ok, revoke_reason),
        "push_other_expense": _cap(
            push_ok,
            "other_expense_application.push_other_expense.not_allowed" if not push_ok else None,
        ),
        "print": _cap(True),
    }


def assert_other_expense_application_capability(
    row: Any,
    action: str,
    *,
    has_linked_expense: bool = False,
) -> None:
    caps = derive_other_expense_application_capabilities(
        row, has_linked_expense=has_linked_expense
    )
    cap = caps.get(action)
    if not cap or not cap.allowed:
        reason = cap.reason if cap else "other_expense_application.action.not_allowed"
        raise BusinessLogicError(
            CAPABILITY_REASON_MESSAGES.get(reason, reason)
        )
