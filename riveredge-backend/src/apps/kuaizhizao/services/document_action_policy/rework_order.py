"""返工单业务态 capabilities（唯一真源）。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from infra.exceptions.exceptions import BusinessLogicError

from apps.kuaizhizao.constants import is_submitted_status
from apps.kuaizhizao.constants.rework_business_types import (
    REWORK_BUSINESS_INVENTORY_VERIFY,
    REWORK_BUSINESS_MULTI_SIGNOFF,
)
from apps.kuaizhizao.constants.rework_signoff_chain import SIGNOFF_FLOW_KEY
from apps.kuaizhizao.services.document_action_policy.types import (
    ActionCapability,
    CAPABILITY_REASON_MESSAGES,
    ReworkOrderCapabilities,
)
from apps.kuaizhizao.utils.rework_order_constants import (
    ROUTING_MODE_DYNAMIC,
    TERMINAL_REWORK_ORDER_STATUSES,
)

_TERMINAL = TERMINAL_REWORK_ORDER_STATUSES | frozenset({"cancelled"})

_CAPABILITY_CONTEXT_KEYS = frozenset({
    "has_reports",
    "current_op_completed",
    "has_completed_operation",
    "awaiting_route_decision",
    "verification_passed",
    "has_operation_links",
})

_REVIEW_APPROVED = frozenset({"审核通过", "已通过", "已审核", "approved", "通过", "APPROVED"})
_REVIEW_REJECTED = frozenset({"审核驳回", "已驳回", "rejected", "REJECTED", "驳回"})
_REVIEW_PENDING = frozenset({"待审核", "pending_review", "pending_approval", "pending", "PENDING"})


def capability_kwargs_from_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """从 compute_capability_context 结果提取 derive_rework_order_capabilities 可接受参数。"""
    return {key: ctx[key] for key in _CAPABILITY_CONTEXT_KEYS if key in ctx}


def _cap(allowed: bool, reason: Optional[str] = None) -> ActionCapability:
    return ActionCapability(allowed=allowed, reason=reason if not allowed else None)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


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


def _signoff_flow_active(record: Any) -> bool:
    """会签部门链已发起且未关闭：各部门仍须填报（含领导审批通过之后）。"""
    payload = getattr(record, "extension_payload", None) or {}
    if not isinstance(payload, dict):
        return False
    flow = payload.get(SIGNOFF_FLOW_KEY)
    if not isinstance(flow, dict):
        return False
    key = _norm(flow.get("current_node_key"))
    return bool(key) and key != "closed"


def derive_rework_order_capabilities(
    record: Any,
    *,
    has_reports: bool = False,
    current_op_completed: bool = False,
    has_completed_operation: bool = False,
    awaiting_route_decision: bool = False,
    verification_passed: bool = False,
    has_operation_links: bool = False,
) -> ReworkOrderCapabilities:
    status = _norm(getattr(record, "status", None))
    review = getattr(record, "review_status", None)
    routing_mode = _norm(getattr(record, "routing_mode", ROUTING_MODE_DYNAMIC))
    business_type = _norm(getattr(record, "business_type", None)) or "simple_exec"
    verification_required = bool(getattr(record, "verification_required", False))
    is_terminal = status in _TERMINAL
    is_draft = status == "draft"
    is_signoff = business_type in (REWORK_BUSINESS_MULTI_SIGNOFF, REWORK_BUSINESS_INVENTORY_VERIFY)
    is_multi_signoff = business_type == REWORK_BUSINESS_MULTI_SIGNOFF
    review_committed = is_submitted_status(review)
    editable_review = _review_editable(review)
    # 部门链进行中允许保存本节点字段；不能只认 SUBMITTED，否则领导通过后计划/仓库无法填报
    signoff_dept_fill = is_signoff and is_draft and _signoff_flow_active(record)

    update_allowed = (is_draft and not review_committed and editable_review) or signoff_dept_fill
    if signoff_dept_fill:
        update_reason = None
    elif review_committed:
        update_reason = "rework_order.update.submitted"
    elif not update_allowed:
        update_reason = "rework_order.update.not_draft"
    else:
        update_reason = None
    update_cap = _cap(update_allowed, update_reason)

    delete_allowed = False
    delete_reason = "rework_order.delete.not_allowed"
    if review_committed:
        delete_reason = "rework_order.delete.submitted"
    elif status in ("draft", "cancelled") or (status == "released" and not has_reports):
        delete_allowed = True
        delete_reason = None
    delete_cap = _cap(delete_allowed, delete_reason)

    if is_signoff:
        if not is_draft:
            submit_reason = "rework_order.submit.not_draft"
        elif not editable_review:
            submit_reason = "rework_order.submit.not_draft"
        else:
            submit_reason = None
        submit_cap = _cap(submit_reason is None, submit_reason)
        submit_review_allowed = is_draft and review_committed
        submit_review_cap = _cap(
            submit_review_allowed,
            None if submit_review_allowed else "rework_order.submit_review.not_allowed",
        )
        withdraw_submit_allowed = is_draft and (review_committed or _review_pending(review))
        withdraw_submit_cap = _cap(
            withdraw_submit_allowed,
            None if withdraw_submit_allowed else "rework_order.withdraw_submit.not_allowed",
        )
        # 会签链运行中 review 常为已提交；节点待审时仍须允许审批人操作
        approve_allowed = is_draft and _review_pending(review) and (
            is_multi_signoff or not review_committed
        )
        approve_cap = _cap(
            approve_allowed,
            None if approve_allowed else "rework_order.approve.not_pending",
        )
        revoke_allowed = is_draft and _review_approved(review)
        revoke_cap = _cap(
            revoke_allowed,
            None if revoke_allowed else "rework_order.revoke_approval.not_allowed",
        )
    else:
        deny_signoff = _cap(False, "rework_order.submit.not_signoff")
        submit_cap = deny_signoff
        submit_review_cap = deny_signoff
        withdraw_submit_cap = _cap(False, "rework_order.withdraw_submit.not_allowed")
        approve_cap = _cap(False, "rework_order.approve.not_pending")
        revoke_cap = _cap(False, "rework_order.revoke_approval.not_allowed")

    # 多部门会签：走工作台/会签链，不提供宿主工序路线「下达」
    # 库存验证：审核通过且已配置工序路线后可下达
    # 简化执行：草稿且已配置工序路线（通常来自原工单）可下达
    if is_multi_signoff:
        release_allowed = False
        release_reason = "rework_order.release.signoff_workflow"
    elif business_type == REWORK_BUSINESS_INVENTORY_VERIFY:
        if not is_draft:
            release_allowed = False
            release_reason = "rework_order.release.not_draft"
        elif not _review_approved(review):
            release_allowed = False
            release_reason = "rework_order.release.awaiting_approval"
        elif not has_operation_links:
            release_allowed = False
            release_reason = "rework_order.release.no_route"
        else:
            release_allowed = True
            release_reason = None
    else:
        if not is_draft:
            release_allowed = False
            release_reason = "rework_order.release.not_draft"
        elif not has_operation_links:
            release_allowed = False
            release_reason = "rework_order.release.no_route"
        else:
            release_allowed = True
            release_reason = None
    release_cap = _cap(release_allowed, release_reason)

    execute_allowed = status in ("released", "in_progress") and not awaiting_route_decision
    execute_cap = _cap(
        execute_allowed,
        "rework_order.execute.awaiting_decision"
        if awaiting_route_decision
        else "rework_order.execute.not_allowed"
        if not execute_allowed
        else None,
    )

    assign_allowed = status in (
        "draft",
        "released",
        "in_progress",
        "on_hold",
    )
    assign_cap = _cap(
        assign_allowed,
        "rework_order.assign.not_allowed" if not assign_allowed else None,
    )

    advance_allowed = (
        routing_mode == ROUTING_MODE_DYNAMIC
        and status == "in_progress"
        and awaiting_route_decision
    )
    advance_cap = _cap(
        advance_allowed,
        "rework_order.advance.not_dynamic" if routing_mode != ROUTING_MODE_DYNAMIC else "rework_order.advance.not_allowed"
        if not advance_allowed
        else None,
    )

    request_complete_allowed = (
        status == "in_progress"
        and has_completed_operation
        and (awaiting_route_decision or current_op_completed or routing_mode != ROUTING_MODE_DYNAMIC)
    )
    request_complete_cap = _cap(
        request_complete_allowed,
        "rework_order.request_complete.not_allowed" if not request_complete_allowed else None,
    )

    quality_release_allowed = status == "pending_verification" and verification_passed
    quality_release_cap = _cap(
        quality_release_allowed,
        "rework_order.quality_release.verification_pending"
        if status == "pending_verification" and not verification_passed
        else "rework_order.quality_release.not_allowed"
        if not quality_release_allowed
        else None,
    )

    base_close_ready = status == "quality_released" or (
        status == "pending_verification" and not verification_required
    )
    finance_signed = bool(getattr(record, "finance_signed_at", None))
    if is_signoff:
        finance_sign_allowed = base_close_ready and not finance_signed
        finance_sign_cap = _cap(
            finance_sign_allowed,
            "rework_order.finance_sign.already_signed"
            if base_close_ready and finance_signed
            else "rework_order.finance_sign.not_allowed"
            if not finance_sign_allowed
            else None,
        )
        close_allowed = base_close_ready and finance_signed
        close_cap = _cap(
            close_allowed,
            "rework_order.close.awaiting_finance"
            if base_close_ready and not finance_signed
            else "rework_order.close.not_allowed"
            if not close_allowed
            else None,
        )
    else:
        finance_sign_cap = _cap(False, "rework_order.finance_sign.not_allowed")
        close_allowed = base_close_ready
        close_cap = _cap(
            close_allowed,
            "rework_order.close.not_allowed" if not close_allowed else None,
        )

    pqc_checked = bool(getattr(record, "pqc_checked_at", None))
    if business_type == "inventory_verify":
        pqc_status_ok = status not in ("draft", "cancelled")
        pqc_check_allowed = pqc_status_ok and not pqc_checked
        if not pqc_status_ok:
            pqc_reason = "rework_order.pqc_check.not_allowed"
        elif pqc_checked:
            pqc_reason = "rework_order.pqc_check.already_checked"
        else:
            pqc_reason = None
        pqc_check_cap = _cap(pqc_check_allowed, pqc_reason)
        oqc_notify_allowed = pqc_status_ok and pqc_checked
        oqc_notify_cap = _cap(
            oqc_notify_allowed,
            "rework_order.oqc_notify.pqc_required"
            if pqc_status_ok and not pqc_checked
            else "rework_order.oqc_notify.not_allowed"
            if not oqc_notify_allowed
            else None,
        )
    else:
        pqc_check_cap = _cap(False, "rework_order.pqc_check.not_inventory_verify")
        oqc_notify_cap = _cap(False, "rework_order.oqc_notify.not_inventory_verify")

    cancel_allowed = False
    cancel_reason = "rework_order.cancel.not_allowed"
    if status == "draft" and not review_committed and editable_review:
        cancel_allowed = True
        cancel_reason = None
    elif status == "released" and not has_reports:
        cancel_allowed = True
        cancel_reason = None
    elif status == "cancelled":
        cancel_reason = "rework_order.cancel.already_cancelled"
    elif is_terminal:
        cancel_reason = "rework_order.cancel.terminal"

    hold_allowed = status in ("released", "in_progress")
    hold_cap = _cap(hold_allowed, "rework_order.hold.not_allowed" if not hold_allowed else None)

    resume_allowed = status == "on_hold"
    resume_cap = _cap(resume_allowed, "rework_order.resume.not_on_hold" if not resume_allowed else None)

    return ReworkOrderCapabilities(
        update=update_cap,
        delete=delete_cap,
        submit=submit_cap,
        submit_review=submit_review_cap,
        withdraw_submit=withdraw_submit_cap,
        approve=approve_cap,
        revoke_approval=revoke_cap,
        release=release_cap,
        execute=execute_cap,
        assign=assign_cap,
        advance_next=advance_cap,
        request_complete=request_complete_cap,
        quality_release=quality_release_cap,
        finance_sign=finance_sign_cap,
        pqc_check=pqc_check_cap,
        oqc_notify=oqc_notify_cap,
        close=close_cap,
        cancel=_cap(cancel_allowed, cancel_reason),
        hold=hold_cap,
        resume=resume_cap,
        print=_cap(not is_terminal or status == "closed"),
    )


def assert_rework_order_capability(record: Any, action: str, caps: Optional[ReworkOrderCapabilities] = None) -> None:
    resolved = caps or derive_rework_order_capabilities(record)
    cap_map = {
        "update": resolved.update,
        "delete": resolved.delete,
        "submit": resolved.submit,
        "submit_review": resolved.submit_review,
        "withdraw_submit": resolved.withdraw_submit,
        "approve": resolved.approve,
        "reject": resolved.approve,
        "revoke_approval": resolved.revoke_approval,
        "release": resolved.release,
        "execute": resolved.execute,
        "assign": resolved.assign,
        "advance_next": resolved.advance_next,
        "request_complete": resolved.request_complete,
        "quality_release": resolved.quality_release,
        "finance_sign": resolved.finance_sign,
        "pqc_check": resolved.pqc_check,
        "oqc_notify": resolved.oqc_notify,
        "close": resolved.close,
        "cancel": resolved.cancel,
        "hold": resolved.hold,
        "resume": resolved.resume,
        "print": resolved.print,
    }
    cap = cap_map.get(action)
    if cap is None:
        raise ValueError(f"Unknown rework order capability action: {action}")
    if not cap.allowed:
        msg = CAPABILITY_REASON_MESSAGES.get(cap.reason or "", cap.reason or "操作不允许")
        raise BusinessLogicError(msg)
