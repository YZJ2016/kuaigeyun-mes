"""未提交审核的 review 态：须为草稿；误标待审且无审批实例时按草稿处理。"""

from __future__ import annotations

from typing import Any, Optional

_REVIEW_DRAFT_RAW = frozenset({"草稿", "draft", "DRAFT", ""})
_REVIEW_PENDING_RAW = frozenset({
    "待审核",
    "pending",
    "pending_review",
    "pending_approval",
    "PENDING",
    "PENDING_REVIEW",
    "已提交",
})


def _norm_review(value: Any) -> str:
    return str(value or "").strip()


def _norm_review_lower(value: Any) -> str:
    return _norm_review(value).lower()


def is_review_label_draft(review_status: Any) -> bool:
    raw = _norm_review(review_status)
    if not raw:
        return True
    lowered = _norm_review_lower(review_status)
    return raw in _REVIEW_DRAFT_RAW or lowered in _REVIEW_DRAFT_RAW


def is_review_label_pending(review_status: Any) -> bool:
    raw = _norm_review(review_status)
    lowered = _norm_review_lower(review_status)
    return raw in _REVIEW_PENDING_RAW or lowered in _REVIEW_PENDING_RAW


def is_effective_review_draft(
    review_status: Any,
    *,
    review_submitted: Optional[bool] = None,
) -> bool:
    """未提交或显式草稿 → True；已提交待审 → False。"""
    if is_review_label_draft(review_status):
        return True
    if review_submitted is False and is_review_label_pending(review_status):
        return True
    return False


def is_effective_review_pending(
    review_status: Any,
    *,
    review_submitted: Optional[bool] = None,
) -> bool:
    if review_submitted is False:
        return False
    return is_review_label_pending(review_status)
