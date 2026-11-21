"""统一需求（需求计划）业务态 capabilities（保存/提交/审核拆分 + 下推计算）。"""

from __future__ import annotations

from typing import Any, Optional

from infra.exceptions.exceptions import BusinessLogicError

from apps.kuaizhizao.constants import (
    DemandStatus,
    LEGACY_AUDITED_VALUES,
    ReviewStatus,
    is_draft_status,
    is_pending_review_status,
    is_submitted_status,
    normalize_status,
)
from apps.kuaizhizao.services.document_action_policy.types import (
    ActionCapability,
    CAPABILITY_REASON_MESSAGES,
    DemandCapabilities,
)


def _cap(allowed: bool, reason: Optional[str] = None) -> ActionCapability:
    return ActionCapability(allowed=allowed, reason=reason if not allowed else None)


def _norm_review_status(review_status: Any) -> str:
    from apps.kuaizhizao.constants import REVIEW_STATUS_ALIASES

    raw = str(review_status or "").strip()
    if not raw:
        return ""
    return REVIEW_STATUS_ALIASES.get(raw, raw.upper())


def demand_allows_computation_merge(demand: Any) -> bool:
    """与需求下推需求计算门禁一致：审核通过且处于可计算状态（已审核/已确认/已生效等）。"""
    review_norm = _norm_review_status(getattr(demand, "review_status", None))
    if review_norm != ReviewStatus.APPROVED.value:
        return False
    raw = str(getattr(demand, "status", "") or "").strip()
    if raw in LEGACY_AUDITED_VALUES:
        return True
    status_norm = normalize_status(raw)
    return status_norm in (
        DemandStatus.AUDITED.value,
        DemandStatus.CONFIRMED.value,
        "EFFECTIVE",
    )


def _is_rejected(status: Any) -> bool:
    raw = str(status or "").strip()
    return normalize_status(raw) == DemandStatus.REJECTED.value or raw in ("已驳回", "REJECTED")


def _is_editable_plan(demand: Any) -> bool:
    status = str(getattr(demand, "status", "") or "").strip()
    if is_submitted_status(status) or is_pending_review_status(status):
        return False
    return is_draft_status(status) or _is_rejected(status)


def derive_demand_capabilities(demand: Any) -> DemandCapabilities:
    status = str(getattr(demand, "status", "") or "").strip()
    review = getattr(demand, "review_status", None)
    demand_type = str(getattr(demand, "demand_type", None) or "").strip()
    submitted = is_submitted_status(status)
    pending = is_pending_review_status(status)
    approved_review = _norm_review_status(review) == ReviewStatus.APPROVED.value

    merge_allowed = demand_allows_computation_merge(demand)
    merge_reason = "demand.merge_computation.not_audited" if not merge_allowed else None
    if merge_allowed and bool(getattr(demand, "pushed_to_computation", False)):
        merge_allowed = False
        merge_reason = "demand.push_computation.already_pushed"
    merge_cap = _cap(merge_allowed, merge_reason if not merge_allowed else None)

    delete_allowed = False
    delete_reason = "demand.delete.not_allowed"
    if demand_type in ("sales_forecast", "sales_order"):
        delete_reason = "demand.delete.synced_upstream"
    elif demand_type == "demand_plan":
        if submitted:
            delete_reason = "demand.delete.submitted"
        elif pending or approved_review:
            delete_reason = "demand.delete.not_allowed"
        elif is_draft_status(status) or _is_rejected(status):
            delete_allowed = True
            delete_reason = None
    delete_cap = _cap(delete_allowed, delete_reason)

    update_allowed = demand_type == "demand_plan" and _is_editable_plan(demand)
    update_cap = _cap(
        update_allowed,
        "demand.update.submitted" if submitted or pending else "demand.update.not_allowed",
    ) if not update_allowed else _cap(True)

    submit_allowed = demand_type == "demand_plan" and (
        (is_draft_status(status) and not submitted) or _is_rejected(status)
    )
    submit_cap = _cap(
        submit_allowed,
        "demand.submit.not_draft" if not submit_allowed else None,
    )

    submit_review_allowed = demand_type == "demand_plan" and submitted
    submit_review_cap = _cap(
        submit_review_allowed,
        "demand.submit_review.not_allowed" if not submit_review_allowed else None,
    )

    withdraw_submit_allowed = demand_type == "demand_plan" and (submitted or pending)
    withdraw_submit_cap = _cap(
        withdraw_submit_allowed,
        "demand.withdraw_submit.not_pending" if not withdraw_submit_allowed else None,
    )

    approve_cap = _cap(
        demand_type == "demand_plan" and pending,
        "demand.approve.not_pending" if not (demand_type == "demand_plan" and pending) else None,
    )

    revoke_allowed = (
        demand_type == "demand_plan"
        and normalize_status(status) in (DemandStatus.AUDITED.value, DemandStatus.CONFIRMED.value)
        and approved_review
        and not bool(getattr(demand, "pushed_to_computation", False))
    )
    revoke_cap = _cap(
        revoke_allowed,
        "demand.revoke_approval.not_allowed" if not revoke_allowed else None,
    )

    return DemandCapabilities(
        merge_computation=merge_cap,
        delete=delete_cap,
        update=update_cap,
        submit=submit_cap,
        submit_review=submit_review_cap,
        withdraw_submit=withdraw_submit_cap,
        approve=approve_cap,
        revoke_approval=revoke_cap,
    )


def assert_demand_capability(demand: Any, action: str) -> None:
    caps = derive_demand_capabilities(demand)
    cap_map = {
        "merge_computation": caps.merge_computation,
        "delete": caps.delete,
        "update": caps.update,
        "submit": caps.submit,
        "submit_review": caps.submit_review,
        "withdraw_submit": caps.withdraw_submit,
        "approve": caps.approve,
        "reject": caps.approve,
        "revoke_approval": caps.revoke_approval,
    }
    cap = cap_map.get(action)
    if cap is None:
        raise ValueError(f"Unknown demand capability action: {action}")
    if not cap.allowed:
        msg = CAPABILITY_REASON_MESSAGES.get(cap.reason or "", cap.reason or "操作不允许")
        raise BusinessLogicError(msg)
