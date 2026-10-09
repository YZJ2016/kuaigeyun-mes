"""委外试验（L58）校验与列表能力勾选。"""

from __future__ import annotations

from typing import Any, Optional

from apps.kuaiplm.constants.lab_request_types import (
    LAB_REQUEST_STATUS_COMPLETED,
    LAB_REQUEST_STATUS_DRAFT,
    LAB_REQUEST_STATUS_IN_LAB,
    LAB_REQUEST_STATUS_PENDING,
    LAB_REQUEST_STATUS_PENDING_REVIEW,
    LAB_REQUEST_STATUS_REJECTED,
    LAB_REQUEST_STATUS_REVOKED,
    LAB_REQUEST_TYPE_OUTSOURCE,
)


def outsource_content_ready(title: Optional[str], test_reason: Optional[str]) -> bool:
    return bool((title or "").strip() and (test_reason or "").strip())


def validate_outsource_on_submit(*, title: Optional[str], test_reason: Optional[str]) -> None:
    from infra.exceptions.exceptions import ValidationError

    if not (title or "").strip():
        raise ValidationError("试验名称不能为空")
    if not (test_reason or "").strip():
        raise ValidationError("委外试验须填写试验原由")


def compute_outsource_capabilities(row: Any) -> dict[str, bool]:
    """L58 列表勾选：填报、部门审过、填价、实验室受理。"""
    bt = (getattr(row, "business_type", None) or "").strip().lower()
    if bt != LAB_REQUEST_TYPE_OUTSOURCE:
        return {}
    status = (getattr(row, "status", None) or "").strip().lower()
    filled = outsource_content_ready(
        getattr(row, "title", None),
        getattr(row, "test_reason", None),
    )
    dept_approved = status not in {
        LAB_REQUEST_STATUS_DRAFT,
        LAB_REQUEST_STATUS_PENDING_REVIEW,
        LAB_REQUEST_STATUS_REJECTED,
        LAB_REQUEST_STATUS_REVOKED,
    } and bool(getattr(row, "submitted_at", None))
    price = getattr(row, "outsource_price", None)
    price_filled = price is not None and str(price).strip() != ""
    lab_accepted = status in {
        LAB_REQUEST_STATUS_IN_LAB,
        LAB_REQUEST_STATUS_COMPLETED,
    } or getattr(row, "accepted_at", None) is not None
    return {
        "filled": filled,
        "dept_approved": dept_approved and filled,
        "price_filled": price_filled,
        "lab_accepted": lab_accepted,
    }
