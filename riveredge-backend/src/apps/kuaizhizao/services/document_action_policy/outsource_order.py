"""工序委外 capabilities（工序发料门禁）。"""

from __future__ import annotations

from typing import Any, Optional

from infra.exceptions.exceptions import BusinessLogicError

from apps.kuaizhizao.services.document_action_policy.types import ActionCapability


def _cap(allowed: bool, reason: Optional[str] = None) -> ActionCapability:
    return ActionCapability(allowed=allowed, reason=reason if not allowed else None)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def derive_outsource_order_push_issue_cap(record: Any) -> ActionCapability:
    status = _norm(getattr(record, "status", None))
    if status == "cancelled":
        return _cap(False, "outsource_order.push_issue.cancelled")
    if status == "completed":
        return _cap(False, "outsource_order.push_issue.completed")
    if status in ("released", "in_progress", "已下达", "执行中"):
        return _cap(True)
    return _cap(False, "outsource_order.push_issue.not_released")


def assert_outsource_order_push_issue(record: Any) -> None:
    cap = derive_outsource_order_push_issue_cap(record)
    if not cap.allowed:
        raise BusinessLogicError(
            "当前工序委外单不可工序发料，请先下达或检查状态"
        )