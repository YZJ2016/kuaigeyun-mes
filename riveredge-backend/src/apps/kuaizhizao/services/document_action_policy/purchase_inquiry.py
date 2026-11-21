"""采购询价单业务态 capabilities（唯一真源，与 service 门禁一致）。"""

from __future__ import annotations

from typing import Any, Optional

from infra.exceptions.exceptions import BusinessLogicError

from apps.kuaizhizao.constants import DocumentStatus, ReviewStatus, is_rejected_status, is_submitted_status
from apps.kuaizhizao.constants.purchase_inquiry import PurchaseInquiryStatus
from apps.kuaizhizao.services.document_action_policy.types import (
    ActionCapability,
    CAPABILITY_REASON_MESSAGES,
    PurchaseInquiryCapabilities,
)


def _cap(allowed: bool, reason: Optional[str] = None) -> ActionCapability:
    return ActionCapability(allowed=allowed, reason=reason if not allowed else None)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _normalize_review_status(review_status: Any) -> str:
    from apps.kuaizhizao.constants import REVIEW_STATUS_ALIASES

    raw = _norm(review_status)
    if not raw:
        return ""
    return REVIEW_STATUS_ALIASES.get(raw, raw.upper())


def _is_review_awaiting_decision(review_status: Any) -> bool:
    """已提交待人工审：PENDING_REVIEW / 待审核。建单默认 DRAFT/PENDING 不算待审。"""
    rs = _normalize_review_status(review_status)
    return rs in {
        DocumentStatus.PENDING_REVIEW.value,
        "待审核",
        "PENDING_APPROVAL",
        "已提交",
    }


def derive_purchase_inquiry_capabilities(inquiry: Any) -> PurchaseInquiryCapabilities:
    status = getattr(inquiry, "status", None)
    review_status = getattr(inquiry, "review_status", None)
    st = _norm(status)

    review_rejected = _normalize_review_status(review_status) == ReviewStatus.REJECTED.value
    review_committed = is_submitted_status(str(review_status or ""))
    review_pending = _is_review_awaiting_decision(review_status)
    review_approved = _normalize_review_status(review_status) == ReviewStatus.APPROVED.value
    business_draft = st == PurchaseInquiryStatus.DRAFT.value
    review_open = _normalize_review_status(review_status) in {ReviewStatus.DRAFT.value, ""}

    update_allowed = (business_draft and not review_committed) or review_rejected or is_rejected_status(st)
    update_reason = None
    if not update_allowed:
        update_reason = (
            "purchase_inquiry.update.submitted"
            if review_committed
            else "purchase_inquiry.update.not_draft"
        )
    update_cap = _cap(update_allowed, update_reason)

    delete_allowed = business_draft and not review_committed and not review_pending
    delete_reason = None
    if not delete_allowed:
        delete_reason = (
            "purchase_inquiry.delete.submitted"
            if review_committed
            else "purchase_inquiry.delete.not_draft"
        )
    delete_cap = _cap(delete_allowed, delete_reason)

    submit_allowed = business_draft and (review_open or review_rejected or is_rejected_status(st))
    submit_cap = _cap(
        submit_allowed,
        "purchase_inquiry.submit.not_draft" if not submit_allowed else None,
    )

    withdraw_submit_allowed = business_draft and (review_committed or review_pending)
    withdraw_submit_cap = _cap(
        withdraw_submit_allowed,
        "purchase_inquiry.withdraw_submit.not_pending" if not withdraw_submit_allowed else None,
    )

    approve_cap = _cap(
        _is_review_awaiting_decision(review_status),
        "purchase_inquiry.approve.not_pending" if not _is_review_awaiting_decision(review_status) else None,
    )

    revoke_allowed = business_draft and review_approved
    revoke_cap = _cap(
        revoke_allowed,
        "purchase_inquiry.revoke_approval.not_approved" if not revoke_allowed else None,
    )

    push_po_cap = _cap(
        st == PurchaseInquiryStatus.AWARDED.value,
        "purchase_inquiry.push_purchase_order.not_allowed"
        if st != PurchaseInquiryStatus.AWARDED.value
        else None,
    )

    return PurchaseInquiryCapabilities(
        update=update_cap,
        delete=delete_cap,
        submit=submit_cap,
        withdraw_submit=withdraw_submit_cap,
        approve=approve_cap,
        revoke_approval=revoke_cap,
        push_purchase_order=push_po_cap,
    )


def assert_purchase_inquiry_capability(inquiry: Any, action: str) -> None:
    caps = derive_purchase_inquiry_capabilities(inquiry)
    cap_map = {
        "update": caps.update,
        "delete": caps.delete,
        "submit": caps.submit,
        "withdraw_submit": caps.withdraw_submit,
        "approve": caps.approve,
        "revoke_approval": caps.revoke_approval,
        "push_purchase_order": caps.push_purchase_order,
    }
    cap = cap_map.get(action)
    if cap is None:
        raise ValueError(f"Unknown purchase inquiry capability action: {action}")
    if not cap.allowed:
        msg = CAPABILITY_REASON_MESSAGES.get(cap.reason or "", cap.reason or "操作不允许")
        raise BusinessLogicError(msg)
