"""付款申请单 capabilities"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from infra.exceptions.exceptions import BusinessLogicError

from apps.kuaizhizao.constants import is_draft_status, is_pending_review_status
from apps.kuaizhizao.services.document_action_policy.types import ActionCapability


def _cap(allowed: bool, reason: Optional[str] = None) -> ActionCapability:
    return ActionCapability(allowed=allowed, reason=reason if not allowed else None)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _is_approved(status: Any) -> bool:
    s = _norm(status)
    return s in ("已批准", "部分付款", "已通过", "APPROVED", "AUDITED")


def derive_payment_application_capabilities(
    app: Any,
    *,
    has_linked_payment: bool = False,
) -> dict[str, ActionCapability]:
    status = getattr(app, "status", None)
    remaining = getattr(app, "remaining_amount", 0) or 0
    paid = Decimal(str(getattr(app, "paid_amount", 0) or 0))

    from apps.kuaizhizao.constants import is_rejected_status

    update_ok = (
        is_draft_status(status or "")
        or is_pending_review_status(status or "")
        or is_rejected_status(status or "")
    )
    delete_ok = is_draft_status(status or "")

    submit_ok = is_draft_status(status or "") or is_rejected_status(status or "")
    approve_ok = is_pending_review_status(status or "")

    approved = _is_approved(status)
    push_ok = approved and float(remaining) > 0

    revoke_ok = _norm(status) == "已批准" and paid <= 0 and not has_linked_payment
    revoke_reason = None
    if has_linked_payment:
        revoke_reason = "payment_application.revoke_approval.has_payment"
    elif paid > 0 or _norm(status) == "部分付款":
        revoke_reason = "payment_application.revoke_approval.has_payment"
    elif _norm(status) != "已批准":
        revoke_reason = "payment_application.revoke_approval.not_allowed"

    return {
        "update": _cap(update_ok, "payment_application.update.not_allowed" if not update_ok else None),
        "delete": _cap(delete_ok, "payment_application.delete.not_allowed" if not delete_ok else None),
        "submit": _cap(submit_ok, "payment_application.submit.not_allowed" if not submit_ok else None),
        "approve": _cap(approve_ok, "payment_application.approve.not_allowed" if not approve_ok else None),
        "reject": _cap(approve_ok, "payment_application.approve.not_allowed" if not approve_ok else None),
        "withdraw_submit": _cap(approve_ok, "payment_application.withdraw.not_allowed" if not approve_ok else None),
        "revoke_approval": _cap(revoke_ok, revoke_reason),
        "push_payment": _cap(
            push_ok,
            "payment_application.push_payment.not_allowed"
            if not push_ok
            else None,
        ),
        "print": _cap(True),
    }


def assert_payment_application_capability(
    app: Any,
    action: str,
    *,
    has_linked_payment: bool = False,
) -> None:
    caps = derive_payment_application_capabilities(
        app, has_linked_payment=has_linked_payment
    )
    cap = caps.get(action)
    if not cap or not cap.allowed:
        reason = cap.reason if cap else "payment_application.action.not_allowed"
        raise BusinessLogicError(reason)
