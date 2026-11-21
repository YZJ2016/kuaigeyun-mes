"""工单业务态 capabilities（唯一真源，与 work_order_service 门禁一致）。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from infra.exceptions.exceptions import BusinessLogicError

from apps.kuaizhizao.constants import is_submitted_status
from apps.kuaizhizao.services.document_action_policy.types import (
    ActionCapability,
    CAPABILITY_REASON_MESSAGES,
    WorkOrderCapabilities,
)

_DRAFT = frozenset({"draft", "草稿", "DRAFT"})
_RELEASED = frozenset({"released", "已下达", "RELEASED"})
_IN_PROGRESS = frozenset({"in_progress", "执行中", "IN_PROGRESS"})
_COMPLETED = frozenset({"completed", "已完成", "COMPLETED"})
_CANCELLED = frozenset({"cancelled", "已取消", "CANCELLED"})
_SPLIT = frozenset({"split", "已拆分"})
_REVIEW_APPROVED = frozenset({
    "已通过",
    "审核通过",
    "approved",
    "APPROVED",
    "通过",
    "已审核",
})
_REVIEW_PENDING = frozenset({
    "待审核",
    "pending_review",
    "PENDING_REVIEW",
    "pending_approval",
    "pending",
    "PENDING",
    "已提交",
})
_REVIEW_REJECTED = frozenset({"已驳回", "审核驳回", "rejected", "REJECTED"})


def _cap(allowed: bool, reason: Optional[str] = None) -> ActionCapability:
    return ActionCapability(allowed=allowed, reason=reason if not allowed else None)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _has_work(wo: Any) -> bool:
    qty = getattr(wo, "completed_quantity", None) or 0
    try:
        return Decimal(str(qty)) > 0
    except Exception:
        return False


def _is_list_work_order_row(wo: Any) -> bool:
    row_kind = _norm(getattr(wo, "row_kind", "work_order"))
    return row_kind == "work_order" or row_kind == ""


def _is_split_child_work_order_row(wo: Any) -> bool:
    return _norm(getattr(wo, "row_kind", "work_order")) == "split"


def _revoke_status_allowed(wo: Any, *, status: str) -> bool:
    is_released = status in _RELEASED
    is_in_progress = status in _IN_PROGRESS
    return is_released or is_in_progress


def _is_manual_complete(wo: Any, *, status: str) -> bool:
    return status in _COMPLETED and bool(getattr(wo, "manually_completed", False))


def _review_editable(review: Any) -> bool:
    raw = _norm(review)
    if not raw:
        return True
    if raw in _DRAFT or raw.upper() in {"DRAFT"}:
        return True
    return raw in _REVIEW_REJECTED or raw.upper() in {"REJECTED"}


def _review_pending(review: Any) -> bool:
    raw = _norm(review)
    if not raw:
        return False
    return raw in _REVIEW_PENDING or raw.upper() in {
        "PENDING",
        "PENDING_REVIEW",
        "PENDING_APPROVAL",
    }


def _review_approved(review: Any) -> bool:
    raw = _norm(review)
    if not raw:
        return False
    return raw in _REVIEW_APPROVED or raw.upper() in {"APPROVED"}


def derive_work_order_capabilities(
    wo: Any,
    *,
    has_returnable_picking: bool | None = None,
    has_downstream_documents: bool | None = None,
    audit_required: bool | None = None,
    review_submitted: Optional[bool] = None,
) -> WorkOrderCapabilities:
    if not _is_list_work_order_row(wo):
        deny = _cap(False, "work_order.not_applicable")
        print_cap = _cap(True) if _is_split_child_work_order_row(wo) else deny
        return WorkOrderCapabilities(
            update=deny,
            delete=deny,
            submit=deny,
            submit_review=deny,
            withdraw_submit=deny,
            approve=deny,
            revoke_approval=deny,
            release=deny,
            revoke=deny,
            withdraw_manual_complete=deny,
            freeze=deny,
            unfreeze=deny,
            cancel=deny,
            set_priority=deny,
            print=print_cap,
            push_production_picking=deny,
            push_finished_goods_receipt=deny,
            push_production_return=deny,
            push_purchase_requisition=deny,
        )

    status = _norm(getattr(wo, "status", None))
    review = getattr(wo, "review_status", None)
    is_frozen = bool(getattr(wo, "is_frozen", False))
    actual_start = getattr(wo, "actual_start_date", None)
    has_work = _has_work(wo)

    is_draft = status in _DRAFT
    is_released = status in _RELEASED
    is_in_progress = status in _IN_PROGRESS
    is_completed = status in _COMPLETED
    is_cancelled = status in _CANCELLED
    is_split = status in _SPLIT
    is_terminal = is_cancelled or is_split

    # 已提交（SUBMITTED）专供提交审核/撤销提交；删改另认审核可编辑态
    review_committed = is_submitted_status(review)
    review_mutable = _review_editable(review)
    update_allowed = is_draft and review_mutable
    if update_allowed:
        update_reason = None
    elif _review_approved(review):
        update_reason = "work_order.update.approved"
    elif review_committed or _review_pending(review):
        update_reason = "work_order.update.submitted"
    else:
        update_reason = "work_order.update.not_draft"
    update_cap = _cap(update_allowed, update_reason)

    # 规范：已提交/待审/已审核不可删；已下达须先撤回下达，已审核须先反审核
    delete_allowed = False
    delete_reason = "work_order.delete.not_allowed"
    if not review_mutable:
        if (is_released or is_in_progress) and _review_approved(review):
            delete_reason = "work_order.delete.need_revoke_then_unaudit"
        elif _review_approved(review):
            delete_reason = "work_order.delete.approved"
        else:
            delete_reason = "work_order.delete.submitted"
    elif is_draft or is_cancelled:
        delete_allowed = True
        delete_reason = None
    elif is_released and not actual_start and not has_work:
        delete_allowed = True
        delete_reason = None
    delete_cap = _cap(delete_allowed, delete_reason)

    from apps.kuaizhizao.services.document_action_policy.review_submission_gate import (
        allows_approve_submitted_pending,
    )

    if not is_draft:
        submit_reason = "work_order.submit.not_draft"
    elif not _review_editable(review):
        submit_reason = "work_order.submit.not_draft"
    else:
        submit_reason = None
    submit_cap = _cap(submit_reason is None, submit_reason)

    submit_review_allowed = is_draft and review_committed
    submit_review_cap = _cap(
        submit_review_allowed,
        None if submit_review_allowed else "work_order.submit_review.not_allowed",
    )

    withdraw_submit_allowed = is_draft and (review_committed or _review_pending(review))
    withdraw_submit_cap = _cap(
        withdraw_submit_allowed,
        None if withdraw_submit_allowed else "work_order.withdraw_submit.not_allowed",
    )

    approve_allowed = (
        is_draft
        and not review_committed
        and (
            _review_pending(review)
            or allows_approve_submitted_pending(
                status,
                review,
                review_submitted=review_submitted,
            )
        )
    )
    approve_cap = _cap(
        approve_allowed,
        None if approve_allowed else "work_order.approve.not_pending",
    )

    if has_downstream_documents:
        revoke_approval_cap = _cap(False, "work_order.revoke_approval.has_downstream")
    elif is_draft and _review_approved(review):
        revoke_approval_cap = _cap(True)
    else:
        revoke_approval_cap = _cap(False, "work_order.revoke_approval.not_allowed")

    release_allowed = is_draft and not is_split and not is_frozen
    release_reason = None
    if not is_draft:
        release_reason = "work_order.release.not_draft"
    elif is_frozen:
        release_reason = "work_order.release.frozen"
    elif is_split:
        release_reason = "work_order.release.split"
    elif release_allowed and audit_required:
        review_norm = _norm(review)
        if review_norm in _REVIEW_PENDING:
            release_allowed = False
            release_reason = "work_order.release.pending_audit"
        elif review_norm in _REVIEW_REJECTED:
            release_allowed = False
            release_reason = "work_order.release.audit_rejected"
        elif review_norm not in _REVIEW_APPROVED:
            release_allowed = False
            release_reason = "work_order.release.audit_required"
    release_cap = _cap(release_allowed, release_reason)

    revoke_status_ok = _revoke_status_allowed(wo, status=status)
    if not revoke_status_ok:
        revoke_cap = _cap(False, "work_order.revoke.not_allowed")
    elif has_work:
        revoke_cap = _cap(False, "work_order.revoke.has_work")
    elif has_downstream_documents:
        revoke_cap = _cap(False, "work_order.revoke.has_downstream")
    else:
        revoke_cap = _cap(True)

    withdraw_manual_complete_allowed = _is_manual_complete(wo, status=status)
    withdraw_manual_complete_cap = _cap(
        withdraw_manual_complete_allowed,
        "work_order.withdraw_manual_complete.not_allowed"
        if not withdraw_manual_complete_allowed
        else None,
    )

    freeze_allowed = not is_terminal and not is_completed and not is_frozen
    freeze_cap = _cap(
        freeze_allowed,
        "work_order.freeze.already_frozen" if is_frozen else "work_order.freeze.not_allowed"
        if not freeze_allowed
        else None,
    )

    unfreeze_cap = _cap(
        is_frozen,
        "work_order.unfreeze.not_frozen" if not is_frozen else None,
    )

    cancel_allowed = not is_completed and not is_terminal
    cancel_cap = _cap(
        cancel_allowed,
        "work_order.cancel.not_allowed" if not cancel_allowed else None,
    )

    set_priority_allowed = not is_terminal
    set_priority_cap = _cap(
        set_priority_allowed,
        "work_order.set_priority.not_allowed" if not set_priority_allowed else None,
    )

    print_cap = _cap(True)

    push_picking_allowed = (
        not is_frozen
        and not is_terminal
        and not is_completed
        and (is_released or is_in_progress)
    )
    push_picking_reason = None
    if is_frozen:
        push_picking_reason = "work_order.push_production_picking.frozen"
    elif is_draft:
        push_picking_reason = "work_order.push_production_picking.draft"
    elif is_completed:
        push_picking_reason = "work_order.push_production_picking.completed"
    elif is_cancelled:
        push_picking_reason = "work_order.push_production_picking.cancelled"
    elif is_split:
        push_picking_reason = "work_order.push_production_picking.split"
    elif not push_picking_allowed:
        push_picking_reason = "work_order.push_production_picking.not_allowed"
    push_picking_cap = _cap(push_picking_allowed, push_picking_reason)

    push_inbound_allowed = (
        not is_frozen
        and not is_terminal
        and (is_released or is_in_progress or is_completed)
    )
    push_inbound_reason = None
    if is_frozen:
        push_inbound_reason = "work_order.push_finished_goods_receipt.frozen"
    elif not push_inbound_allowed:
        push_inbound_reason = "work_order.push_finished_goods_receipt.not_allowed"
    push_inbound_cap = _cap(push_inbound_allowed, push_inbound_reason)

    push_return_allowed = (
        not is_frozen
        and not is_terminal
        and (is_in_progress or is_completed)
    )
    push_return_reason = None
    if is_frozen:
        push_return_reason = "work_order.push_production_return.frozen"
    elif not (is_in_progress or is_completed):
        push_return_reason = "work_order.push_production_return.not_allowed"
    elif has_returnable_picking is False:
        push_return_allowed = False
        push_return_reason = "work_order.push_production_return.no_returnable_lines"
    elif not push_return_allowed:
        push_return_reason = "work_order.push_production_return.not_allowed"
    push_return_cap = _cap(push_return_allowed, push_return_reason)

    push_pr_allowed = (
        not is_frozen
        and not is_terminal
        and not is_completed
        and (is_released or is_in_progress)
    )
    push_pr_reason = None
    if is_frozen:
        push_pr_reason = "work_order.push_purchase_requisition.frozen"
    elif not (is_released or is_in_progress):
        push_pr_reason = "work_order.push_purchase_requisition.not_allowed"
    elif not push_pr_allowed:
        push_pr_reason = "work_order.push_purchase_requisition.not_allowed"
    push_pr_cap = _cap(push_pr_allowed, push_pr_reason)

    return WorkOrderCapabilities(
        update=update_cap,
        delete=delete_cap,
        submit=submit_cap,
        submit_review=submit_review_cap,
        withdraw_submit=withdraw_submit_cap,
        approve=approve_cap,
        revoke_approval=revoke_approval_cap,
        release=release_cap,
        revoke=revoke_cap,
        withdraw_manual_complete=withdraw_manual_complete_cap,
        freeze=freeze_cap,
        unfreeze=unfreeze_cap,
        cancel=cancel_cap,
        set_priority=set_priority_cap,
        print=print_cap,
        push_production_picking=push_picking_cap,
        push_finished_goods_receipt=push_inbound_cap,
        push_production_return=push_return_cap,
        push_purchase_requisition=push_pr_cap,
    )


def assert_work_order_capability(
    wo: Any,
    action: str,
    *,
    has_returnable_picking: bool | None = None,
    has_downstream_documents: bool | None = None,
    audit_required: bool | None = None,
    review_submitted: Optional[bool] = None,
) -> None:
    caps = derive_work_order_capabilities(
        wo,
        has_returnable_picking=has_returnable_picking,
        has_downstream_documents=has_downstream_documents,
        audit_required=audit_required,
        review_submitted=review_submitted,
    )
    cap_map = {
        "update": caps.update,
        "delete": caps.delete,
        "submit": caps.submit,
        "submit_review": caps.submit_review,
        "withdraw_submit": caps.withdraw_submit,
        "approve": caps.approve,
        "revoke_approval": caps.revoke_approval,
        "release": caps.release,
        "revoke": caps.revoke,
        "withdraw_manual_complete": caps.withdraw_manual_complete,
        "freeze": caps.freeze,
        "unfreeze": caps.unfreeze,
        "cancel": caps.cancel,
        "set_priority": caps.set_priority,
        "print": caps.print,
        "push_production_picking": caps.push_production_picking,
        "push_finished_goods_receipt": caps.push_finished_goods_receipt,
        "push_production_return": caps.push_production_return,
    }
    cap = cap_map.get(action)
    if cap is None:
        raise ValueError(f"Unknown work order capability action: {action}")
    if not cap.allowed:
        msg = CAPABILITY_REASON_MESSAGES.get(cap.reason or "", cap.reason or "操作不允许")
        raise BusinessLogicError(msg)
