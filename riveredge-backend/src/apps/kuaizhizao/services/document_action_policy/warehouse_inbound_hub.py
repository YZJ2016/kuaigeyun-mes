"""入库 Hub 聚合行业务态 capabilities（与 inboundHubTypes / inboundBatchConfirm 门禁一致）。"""

from __future__ import annotations

from typing import Any, Optional

from infra.exceptions.exceptions import BusinessLogicError

from apps.kuaizhizao.constants import is_submitted_status
from apps.kuaizhizao.services.document_action_policy.types import (
    ActionCapability,
    CAPABILITY_REASON_MESSAGES,
    InboundHubCapabilities,
)
from core.services.approval.review_submission_state import (
    is_effective_review_draft,
    is_effective_review_pending,
)

_INBOUND_PENDING_STATUSES = frozenset({
    "待入库", "草稿", "待退货", "待退料", "待收货", "pending", "draft", "待归还", "待确认", "DRAFT",
})
_INBOUND_POSTED_STATUSES = frozenset({
    "已入库", "已退货", "已退料", "已归还", "已完成", "已确认", "completed", "processed", "已入库",
})
_OUTSOURCE_PREVIEW_ONLY = frozenset({
    "outsource_material_return",
    "outsource_product_return",
})
_EDITABLE_RECEIPT_TYPES = frozenset({
    "purchase",
    "finished_goods",
    "semi_finished_goods",
    "production_return",
    "other_inbound",
    "material_return",
    "sales_return",
})
_PURCHASE_REVIEW_APPROVED = frozenset({
    "审核通过", "已通过", "已审核", "approved", "通过", "APPROVED",
})
_PURCHASE_REVIEW_REJECTED = frozenset({
    "审核驳回", "已驳回", "rejected", "REJECTED", "驳回",
})


def _purchase_review_approved(review_status: Any) -> bool:
    raw = _norm(review_status)
    return raw in _PURCHASE_REVIEW_APPROVED or raw.lower() in _PURCHASE_REVIEW_APPROVED


def _purchase_review_rejected(review_status: Any) -> bool:
    raw = _norm(review_status)
    return raw in _PURCHASE_REVIEW_REJECTED or raw.lower() in _PURCHASE_REVIEW_REJECTED


def purchase_receipt_mutation_block_reason(record: Any, *, delete: bool = False) -> Optional[str]:
    """已提交、待审核、已通过的采购入库不可改删。驳回和草稿可以。"""
    review = getattr(record, "review_status", None)
    if is_submitted_status(review):
        return "purchase_receipt.delete.submitted" if delete else "purchase_receipt.update.submitted"
    if is_effective_review_pending(review) or _purchase_review_approved(review):
        return "purchase_receipt.update.not_draft"
    return None


_WITHDRAWABLE_RECEIPT_TYPES = frozenset({
    "purchase",
    "finished_goods",
    "semi_finished_goods",
    "production_return",
    "customer_material",
    "sales_return",
    "material_return",
    "other_inbound",
})


def _cap(allowed: bool, reason: Optional[str] = None) -> ActionCapability:
    return ActionCapability(allowed=allowed, reason=reason if not allowed else None)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _is_posted(receipt_type: str, status: str) -> bool:
    if receipt_type == "production_return":
        return status == "已退料"
    if receipt_type == "customer_material":
        return status in {"processed", "已入库"}
    if receipt_type == "sales_return":
        return status == "已退货" or status.lower() == "completed"
    if receipt_type == "material_return":
        return status == "已归还" or status.lower() == "completed"
    return status in _INBOUND_POSTED_STATUSES or status.lower() == "completed"


def derive_inbound_hub_capabilities(
    record: Any,
    *,
    receipt_type: Optional[str] = None,
    payable_request_open: bool = False,
    purchase_return_open: bool = False,
    has_items: bool = True,
) -> InboundHubCapabilities:
    rt = _norm(receipt_type or getattr(record, "receipt_type", None))
    status = _norm(getattr(record, "status", None))

    confirm_allowed = False
    confirm_reason = "inbound_hub.confirm.not_pending"
    if rt in _OUTSOURCE_PREVIEW_ONLY:
        if _is_posted(rt, status):
            confirm_reason = "inbound_hub.confirm.outsource_already_posted"
        else:
            confirm_reason = "inbound_hub.confirm.outsource_use_pull_entry"
    elif rt == "customer_material":
        if status == "pending":
            confirm_allowed = True
            confirm_reason = None
        else:
            confirm_reason = "customer_material.confirm.not_pending"
    elif status in _INBOUND_PENDING_STATUSES:
        # 上游此处对 purchase 要求已审核方可过账；采购入库审核动作链（submit/approve/withdraw
        # 服务与路由）尚未摘取，confirm 暂保持放行，链落地后恢复上游门禁。
        confirm_allowed = True
        confirm_reason = None

    posted = _is_posted(rt, status)
    if rt in _WITHDRAWABLE_RECEIPT_TYPES and posted:
        withdraw_allowed = True
        withdraw_reason = None
    elif rt in _OUTSOURCE_PREVIEW_ONLY:
        withdraw_allowed = False
        withdraw_reason = "inbound_hub.withdraw.unsupported_type"
    elif not posted:
        withdraw_allowed = False
        withdraw_reason = "inbound_hub.withdraw.not_posted"
    else:
        withdraw_allowed = False
        withdraw_reason = "inbound_hub.withdraw.unsupported_type"

    if rt == "purchase" and status in _INBOUND_PENDING_STATUSES:
        block = purchase_receipt_mutation_block_reason(record)
        update_allowed = block is None
        update_reason = block
    elif rt in _EDITABLE_RECEIPT_TYPES and status in _INBOUND_PENDING_STATUSES:
        update_allowed = True
        update_reason = None
    elif rt in _OUTSOURCE_PREVIEW_ONLY:
        update_allowed = False
        update_reason = "inbound_hub.update.unsupported_type"
    elif posted:
        update_allowed = False
        update_reason = "inbound_hub.update.posted"
    else:
        update_allowed = False
        update_reason = "inbound_hub.update.not_allowed"

    push_pa_cap: Optional[ActionCapability] = None
    push_pr_cap: Optional[ActionCapability] = None
    if rt == "purchase":
        if posted and payable_request_open:
            push_pa_cap = _cap(True)
        elif posted:
            push_pa_cap = _cap(
                False, "purchase_receipt.push_payment_application.no_open_amount"
            )
        else:
            push_pa_cap = _cap(
                False, "purchase_receipt.push_payment_application.not_posted"
            )
        if posted and purchase_return_open:
            push_pr_cap = _cap(True)
        elif posted:
            push_pr_cap = _cap(
                False, "purchase_receipt.push_purchase_return.no_returnable"
            )
        else:
            push_pr_cap = _cap(
                False, "purchase_receipt.push_purchase_return.not_posted"
            )

    submit_cap: Optional[ActionCapability] = None
    submit_review_cap: Optional[ActionCapability] = None
    withdraw_submit_cap: Optional[ActionCapability] = None
    approve_cap: Optional[ActionCapability] = None
    revoke_cap: Optional[ActionCapability] = None
    if rt == "purchase":
        review = getattr(record, "review_status", None)
        committed = is_submitted_status(review)
        pending_review = is_effective_review_pending(review)
        approved = _purchase_review_approved(review)
        rejected = _purchase_review_rejected(review)
        draft_review = is_effective_review_draft(review) or _norm(review) in {"", "草稿", "draft", "DRAFT"}
        pending_business = status in _INBOUND_PENDING_STATUSES
        if not has_items:
            submit_cap = _cap(False, "purchase_receipt.submit.no_items")
        else:
            submit_allowed = pending_business and not committed and not pending_review and not approved and (
                draft_review or rejected
            )
            submit_cap = _cap(submit_allowed, None if submit_allowed else "purchase_receipt.submit.not_draft")
        submit_review_allowed = pending_business and has_items and committed
        submit_review_cap = _cap(
            submit_review_allowed,
            None
            if submit_review_allowed
            else (
                "purchase_receipt.submit.no_items"
                if not has_items
                else "purchase_receipt.submit_review.not_allowed"
            ),
        )
        withdraw_submit_allowed = pending_business and (committed or pending_review)
        withdraw_submit_cap = _cap(
            withdraw_submit_allowed,
            None if withdraw_submit_allowed else "purchase_receipt.withdraw_submit.not_pending",
        )
        approve_cap = _cap(pending_review, None if pending_review else "purchase_receipt.approve.not_pending")
        revoke_allowed = pending_business and approved
        revoke_cap = _cap(revoke_allowed, None if revoke_allowed else "purchase_receipt.revoke_approval.not_allowed")

    return InboundHubCapabilities(
        confirm=_cap(confirm_allowed, confirm_reason),
        withdraw=_cap(withdraw_allowed, withdraw_reason),
        update=_cap(update_allowed, update_reason),
        print=_cap(True),
        push_payment_application=push_pa_cap,
        push_purchase_return=push_pr_cap,
        submit=submit_cap,
        submit_review=submit_review_cap,
        withdraw_submit=withdraw_submit_cap,
        approve=approve_cap,
        revoke_approval=revoke_cap,
    )


def assert_inbound_hub_capability(
    record: Any,
    action: str,
    *,
    receipt_type: Optional[str] = None,
    has_items: bool = True,
) -> None:
    caps = derive_inbound_hub_capabilities(
        record,
        receipt_type=receipt_type,
        has_items=has_items,
    )
    cap_map = {
        "confirm": caps.confirm,
        "withdraw": caps.withdraw,
        "update": caps.update,
        "print": caps.print,
        "submit": caps.submit,
        "submit_review": caps.submit_review,
        "withdraw_submit": caps.withdraw_submit,
        "approve": caps.approve,
        "reject": caps.approve,
        "revoke_approval": caps.revoke_approval,
    }
    cap = cap_map.get(action)
    if cap is None:
        raise ValueError(f"Unknown inbound hub capability action: {action}")
    if not cap.allowed:
        msg = CAPABILITY_REASON_MESSAGES.get(cap.reason or "", cap.reason or "操作不允许")
        raise BusinessLogicError(msg)
