"""收货通知单业务态 capabilities（与 shipment_notice 对称）。"""

from __future__ import annotations

from typing import Any, Optional

from infra.exceptions.exceptions import BusinessLogicError

from apps.kuaizhizao.constants import is_submitted_status
from apps.kuaizhizao.services.document_action_policy.types import (
    ActionCapability,
    CAPABILITY_REASON_MESSAGES,
    ReceiptNoticeCapabilities,
)

_REVIEW_APPROVED = frozenset({"审核通过", "已通过", "已审核", "approved", "通过", "APPROVED"})
_REVIEW_REJECTED = frozenset({"审核驳回", "已驳回", "rejected", "REJECTED", "驳回"})
_REVIEW_PENDING = frozenset({"待审核", "pending_review", "pending_approval", "pending", "PENDING"})

_PENDING_STATUS = "待收货"
_NOTIFIED_STATUS = "已通知"
_RECEIPT_WITHDRAWABLE = frozenset({"草稿", "draft", "DRAFT", "待入库"})


def _cap(allowed: bool, reason: Optional[str] = None) -> ActionCapability:
    return ActionCapability(allowed=allowed, reason=reason if not allowed else None)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _is_pending(status: Any) -> bool:
    return _norm(status) == _PENDING_STATUS


def _is_notified(status: Any) -> bool:
    return _norm(status) == _NOTIFIED_STATUS


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


def derive_receipt_notice_capabilities(
    notice: Any,
    *,
    has_items: bool = True,
    has_warehouse: bool = True,
    receipt_withdrawable: bool = True,
) -> ReceiptNoticeCapabilities:
    status = getattr(notice, "status", None)
    review = getattr(notice, "review_status", None)
    pending_business = _is_pending(status)
    editable_review = _review_editable(review)

    if not pending_business:
        update_reason = "receipt_notice.update.not_pending"
    elif is_submitted_status(review):
        update_reason = "receipt_notice.update.submitted"
    elif not editable_review:
        update_reason = "receipt_notice.update.not_draft"
    else:
        update_reason = None
    update_cap = _cap(update_reason is None, update_reason)

    if not pending_business:
        delete_reason = "receipt_notice.delete.not_pending"
    elif is_submitted_status(review):
        delete_reason = "receipt_notice.delete.submitted"
    elif not editable_review:
        delete_reason = "receipt_notice.update.not_draft"
    else:
        delete_reason = None
    delete_cap = _cap(delete_reason is None, delete_reason)

    notify_allowed = False
    notify_reason = "receipt_notice.notify.not_pending"
    if not pending_business:
        notify_reason = "receipt_notice.notify.not_pending"
    elif not _review_approved(review):
        notify_reason = "receipt_notice.notify.not_audited"
    elif getattr(notice, "purchase_receipt_id", None):
        notify_reason = "receipt_notice.notify.already_notified"
    elif not has_items:
        notify_reason = "receipt_notice.notify.no_items"
    elif not has_warehouse:
        notify_reason = "receipt_notice.notify.no_warehouse"
    else:
        notify_allowed = True
        notify_reason = None
    notify_cap = _cap(notify_allowed, notify_reason)

    withdraw_allowed = False
    withdraw_reason = "receipt_notice.withdraw.not_notified"
    if not _is_notified(status):
        withdraw_reason = "receipt_notice.withdraw.not_notified"
    elif not receipt_withdrawable:
        withdraw_reason = "receipt_notice.withdraw.receipt_processing"
    else:
        withdraw_allowed = True
        withdraw_reason = None
    withdraw_cap = _cap(withdraw_allowed, withdraw_reason)

    if not pending_business:
        submit_reason = "receipt_notice.submit.not_draft"
    elif not has_items:
        submit_reason = "receipt_notice.submit.no_items"
    elif not editable_review:
        submit_reason = "receipt_notice.submit.not_draft"
    else:
        submit_reason = None
    submit_cap = _cap(submit_reason is None, submit_reason)

    withdraw_submit_allowed = pending_business and (
        is_submitted_status(review) or _review_pending(review)
    )
    withdraw_submit_cap = _cap(
        withdraw_submit_allowed,
        None if withdraw_submit_allowed else "receipt_notice.withdraw_submit.not_allowed",
    )
    approve_allowed = pending_business and _review_pending(review) and not is_submitted_status(review)
    approve_cap = _cap(
        approve_allowed,
        None if approve_allowed else "receipt_notice.approve.not_pending",
    )
    revoke_allowed = pending_business and _review_approved(review)
    revoke_cap = _cap(
        revoke_allowed,
        None if revoke_allowed else "receipt_notice.revoke_approval.not_allowed",
    )

    return ReceiptNoticeCapabilities(
        update=update_cap,
        delete=delete_cap,
        notify=notify_cap,
        withdraw=withdraw_cap,
        print=_cap(True),
        submit=submit_cap,
        withdraw_submit=withdraw_submit_cap,
        approve=approve_cap,
        revoke_approval=revoke_cap,
    )


def assert_receipt_notice_capability(
    notice: Any,
    action: str,
    *,
    has_items: bool = True,
    has_warehouse: bool = True,
    receipt_withdrawable: bool = True,
) -> None:
    caps = derive_receipt_notice_capabilities(
        notice,
        has_items=has_items,
        has_warehouse=has_warehouse,
        receipt_withdrawable=receipt_withdrawable,
    )
    cap_map = {
        "update": caps.update,
        "delete": caps.delete,
        "notify": caps.notify,
        "withdraw": caps.withdraw,
        "print": caps.print,
        "submit": caps.submit,
        "withdraw_submit": caps.withdraw_submit,
        "approve": caps.approve,
        "reject": caps.approve,
        "revoke_approval": caps.revoke_approval,
    }
    cap = cap_map.get(action)
    if cap is None:
        raise ValueError(f"Unknown receipt notice capability action: {action}")
    if not cap.allowed:
        msg = CAPABILITY_REASON_MESSAGES.get(cap.reason or "", cap.reason or "操作不允许")
        raise BusinessLogicError(msg)
