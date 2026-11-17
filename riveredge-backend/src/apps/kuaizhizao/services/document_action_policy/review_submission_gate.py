"""未提交审核与 capabilities / 删除门禁（与 review_submission_state、审批实例同源）。"""

from __future__ import annotations

from typing import Any, Optional

from apps.kuaizhizao.constants import (
    is_draft_status,
    is_pending_review_status,
    is_rejected_status,
)
from core.services.approval.review_submission_state import (
    is_effective_review_draft,
    is_effective_review_pending,
    is_review_label_pending,
)


def _norm_status(value: Any) -> str:
    return str(value or "").strip()


def looks_pending_submission(status: Any, review_status: Any = None) -> bool:
    """主状态或 review 字段呈「待审/待提交」形态（可能为误标）。"""
    st = _norm_status(status)
    if is_pending_review_status(st) or st in ("已提交",):
        return True
    return is_review_label_pending(review_status)


def allows_delete_unsubmitted(
    status: Any,
    review_status: Any = None,
    *,
    review_submitted: Optional[bool] = None,
) -> bool:
    """未提交可删：草稿、驳回，或待审但无审批实例（误标）。

    review_submitted=None 表示无审批实例证据（生产端按审批实例解析后恒为 bool，
    未解析的 None 视为「未提交」），与单测桩语义一致。
    """
    st = _norm_status(status)
    if is_rejected_status(st):
        return True
    if is_draft_status(st):
        return True
    if is_pending_review_status(st) or st == "已提交":
        return review_submitted is not True
    if is_effective_review_draft(review_status, review_submitted=review_submitted):
        return True
    return False


def allows_submit_unsubmitted(
    status: Any,
    review_status: Any = None,
    *,
    review_submitted: Optional[bool] = None,
) -> bool:
    if is_rejected_status(_norm_status(status)):
        return True
    if is_draft_status(_norm_status(status)):
        return True
    if is_effective_review_draft(review_status, review_submitted=review_submitted):
        return True
    return False


def allows_approve_submitted_pending(
    status: Any,
    review_status: Any = None,
    *,
    review_submitted: Optional[bool] = None,
) -> bool:
    st = _norm_status(status)
    if is_pending_review_status(st) and review_submitted is not False:
        return True
    return is_effective_review_pending(review_status, review_submitted=review_submitted)
