"""报工记录业务态 capabilities（唯一真源，与 reporting_service 门禁一致）。"""

from __future__ import annotations

from typing import Any, Optional

from infra.exceptions.exceptions import BusinessLogicError

from apps.kuaizhizao.services.document_action_policy.types import (
    ActionCapability,
    CAPABILITY_REASON_MESSAGES,
    ReportingRecordCapabilities,
)


def _cap(allowed: bool, reason: Optional[str] = None) -> ActionCapability:
    return ActionCapability(allowed=allowed, reason=reason if not allowed else None)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def derive_reporting_record_capabilities(
    record: Any,
    *,
    has_posted_sales_outbound: bool | None = None,
    has_approved_inbound_downstream: bool | None = None,
) -> ReportingRecordCapabilities:
    status = _norm(getattr(record, "status", None))
    editable = status in {"draft", "pending"}
    blocked_by_outbound = bool(has_posted_sales_outbound)
    blocked_by_inbound = bool(has_approved_inbound_downstream)

    update_cap = _cap(
        editable,
        "reporting_record.update.not_pending" if not editable else None,
    )

    if blocked_by_outbound:
        delete_cap = _cap(False, "reporting_record.delete.has_sales_outbound")
    elif blocked_by_inbound:
        delete_cap = _cap(False, "reporting_record.delete.has_inbound")
    else:
        delete_cap = _cap(
            editable,
            "reporting_record.delete.not_pending" if not editable else None,
        )

    submit_cap = _cap(
        status in {"draft", "rejected"},
        "reporting_record.submit.not_draft" if status not in {"draft", "rejected"} else None,
    )
    approve_cap = _cap(
        status == "pending",
        "reporting_record.approve.not_pending" if status != "pending" else None,
    )

    if blocked_by_outbound:
        revoke_cap = _cap(False, "reporting_record.revoke_approval.has_sales_outbound")
    elif blocked_by_inbound:
        revoke_cap = _cap(False, "reporting_record.revoke_approval.has_inbound")
    else:
        revoke_cap = _cap(
            status == "approved",
            "reporting_record.revoke_approval.not_approved" if status != "approved" else None,
        )

    print_cap = _cap(True)

    return ReportingRecordCapabilities(
        update=update_cap,
        delete=delete_cap,
        submit=submit_cap,
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
        "approve": caps.approve,
        "revoke_approval": caps.revoke_approval,
        "print": caps.print,
    }
    cap = cap_map.get(action)
    if cap is None:
        raise ValueError(f"Unknown reporting record capability action: {action}")
    if not cap.allowed:
        msg = CAPABILITY_REASON_MESSAGES.get(cap.reason or "", cap.reason or "操作不允许")
        raise BusinessLogicError(msg)
