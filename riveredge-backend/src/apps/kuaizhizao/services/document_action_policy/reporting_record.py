"""报工记录业务态 capabilities（唯一真源，与 reporting_service 门禁一致）。"""

from __future__ import annotations

from typing import Any, Optional

from infra.exceptions.exceptions import BusinessLogicError

from apps.kuaizhizao.constants import is_submitted_status
from apps.kuaizhizao.services.document_action_policy.types import (
    ActionCapability,
    CAPABILITY_REASON_MESSAGES,
    ReportingRecordCapabilities,
)

_REVIEW_APPROVED = frozenset({"审核通过", "已通过", "已审核", "approved", "通过", "APPROVED"})
_REVIEW_REJECTED = frozenset({"审核驳回", "已驳回", "rejected", "REJECTED", "驳回"})
_REVIEW_PENDING = frozenset({"待审核", "pending_review", "pending_approval", "pending", "PENDING"})


def _cap(allowed: bool, reason: Optional[str] = None) -> ActionCapability:
    return ActionCapability(allowed=allowed, reason=reason if not allowed else None)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _review_approved(review_status: Any) -> bool:
    raw = _norm(review_status)
    return raw in _REVIEW_APPROVED or raw.lower() in _REVIEW_APPROVED


def _review_rejected(review_status: Any) -> bool:
    raw = _norm(review_status)
    return raw in _REVIEW_REJECTED or raw.lower() in _REVIEW_REJECTED


def _review_pending(review_status: Any) -> bool:
    raw = _norm(review_status)
    return raw in _REVIEW_PENDING or raw.lower() in _REVIEW_PENDING


def _review_editable(review_status: Any) -> bool:
    raw = _norm(review_status)
    return raw in {"", "草稿", "draft", "DRAFT"} or _review_rejected(review_status)


def derive_reporting_record_capabilities(
    record: Any,
    *,
    has_posted_sales_outbound: bool | None = None,
    has_approved_inbound_downstream: bool | None = None,
) -> ReportingRecordCapabilities:
    status = _norm(getattr(record, "status", None))
    review = getattr(record, "review_status", None)
    is_draft = status in {"draft", "草稿", "DRAFT"}
    is_approved = status in {"approved", "已审核", "审核通过"}
    editable_review = _review_editable(review)
    blocked_by_outbound = bool(has_posted_sales_outbound)
    blocked_by_inbound = bool(has_approved_inbound_downstream)

    if not is_draft:
        update_reason = "reporting_record.update.not_pending"
    elif is_submitted_status(review):
        update_reason = "reporting_record.update.submitted"
    elif not editable_review:
        update_reason = "reporting_record.update.not_pending"
    else:
        update_reason = None
    update_cap = _cap(update_reason is None, update_reason)

    if blocked_by_outbound:
        delete_cap = _cap(False, "reporting_record.delete.has_sales_outbound")
    elif blocked_by_inbound:
        delete_cap = _cap(False, "reporting_record.delete.has_inbound")
    elif not is_draft:
        delete_cap = _cap(False, "reporting_record.delete.not_pending")
    elif is_submitted_status(review):
        delete_cap = _cap(False, "reporting_record.update.submitted")
    elif not editable_review:
        delete_cap = _cap(False, "reporting_record.delete.not_pending")
    else:
        delete_cap = _cap(True)

    if not is_draft:
        submit_reason = "reporting_record.submit.not_draft"
    elif not editable_review:
        submit_reason = "reporting_record.submit.not_draft"
    else:
        submit_reason = None
    submit_cap = _cap(submit_reason is None, submit_reason)

    submit_review_allowed = is_draft and is_submitted_status(review)
    submit_review_cap = _cap(
        submit_review_allowed,
        None if submit_review_allowed else "reporting_record.submit_review.not_allowed",
    )

    withdraw_submit_allowed = is_draft and (
        is_submitted_status(review) or _review_pending(review)
    )
    withdraw_submit_cap = _cap(
        withdraw_submit_allowed,
        None if withdraw_submit_allowed else "reporting_record.withdraw_submit.not_allowed",
    )

    approve_allowed = is_draft and _review_pending(review) and not is_submitted_status(review)
    approve_cap = _cap(
        approve_allowed,
        None if approve_allowed else "reporting_record.approve.not_pending",
    )

    if blocked_by_outbound:
        revoke_cap = _cap(False, "reporting_record.revoke_approval.has_sales_outbound")
    elif blocked_by_inbound:
        revoke_cap = _cap(False, "reporting_record.revoke_approval.has_inbound")
    else:
        revoke_cap = _cap(
            is_approved and _review_approved(review),
            "reporting_record.revoke_approval.not_approved"
            if not (is_approved and _review_approved(review))
            else None,
        )

    print_cap = _cap(True)

    return ReportingRecordCapabilities(
        update=update_cap,
        delete=delete_cap,
        submit=submit_cap,
        submit_review=submit_review_cap,
        withdraw_submit=withdraw_submit_cap,
        approve=approve_cap,
        revoke_approval=revoke_cap,
        print=print_cap,
    )


def assert_reporting_record_capability(
    record: Any,
    action: str,
    *,
    has_posted_sales_outbound: bool | None = None,
    has_approved_inbound_downstream: bool | None = None,
) -> None:
    caps = derive_reporting_record_capabilities(
        record,
        has_posted_sales_outbound=has_posted_sales_outbound,
        has_approved_inbound_downstream=has_approved_inbound_downstream,
    )
    cap_map = {
        "update": caps.update,
        "delete": caps.delete,
        "submit": caps.submit,
        "submit_review": caps.submit_review,
        "withdraw_submit": caps.withdraw_submit,
        "approve": caps.approve,
        "reject": caps.approve,
        "revoke_approval": caps.revoke_approval,
        "print": caps.print,
    }
    cap = cap_map.get(action)
    if cap is None:
        raise ValueError(f"Unknown reporting record capability action: {action}")
    if not cap.allowed:
        msg = CAPABILITY_REASON_MESSAGES.get(cap.reason or "", cap.reason or "操作不允许")
        raise BusinessLogicError(msg)
