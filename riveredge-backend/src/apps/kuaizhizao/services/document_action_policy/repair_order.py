"""维修单业务态 capabilities（下推派工/结算/回访）。"""

from __future__ import annotations

from typing import Any, Optional

from infra.exceptions.exceptions import BusinessLogicError

from apps.kuaizhizao.services.document_action_policy.types import (
    CAPABILITY_REASON_MESSAGES,
    ActionCapability,
    RepairOrderCapabilities,
)

_CLOSED = "已关闭"
_PUSHABLE_STATUSES = frozenset({"待派工", "维修中", "待验收"})


def _cap(allowed: bool, reason: Optional[str] = None) -> ActionCapability:
    return ActionCapability(allowed=allowed, reason=reason if not allowed else None)


def derive_repair_order_capabilities(
    order: Any,
    *,
    existing_dispatch_code: Optional[str] = None,
    existing_settlement_code: Optional[str] = None,
    existing_visit_code: Optional[str] = None,
) -> RepairOrderCapabilities:
    status = str(getattr(order, "status", "") or "").strip()
    closed = status == _CLOSED

    update_cap = _cap(not closed, "repair_order.update.closed" if closed else None)
    delete_cap = _cap(not closed, "repair_order.delete.closed" if closed else None)
    close_cap = _cap(not closed, "repair_order.close.already_closed" if closed else None)

    def _push_cap(
        *,
        already_code: Optional[str],
        already_reason: str,
        not_allowed_reason: str,
        require_acceptance: bool = False,
    ) -> ActionCapability:
        if closed:
            return _cap(False, "repair_order.push.closed")
        if status not in _PUSHABLE_STATUSES:
            return _cap(False, not_allowed_reason)
        if require_acceptance and status not in {"待验收", "维修中"}:
            return _cap(False, "repair_order.push_settlement.not_ready")
        if already_code:
            return _cap(False, already_reason)
        return _cap(True)

    return RepairOrderCapabilities(
        update=update_cap,
        delete=delete_cap,
        close=close_cap,
        push_dispatch=_push_cap(
            already_code=existing_dispatch_code,
            already_reason="repair_order.push_dispatch.already_exists",
            not_allowed_reason="repair_order.push_dispatch.not_allowed",
        ),
        push_settlement=_push_cap(
            already_code=existing_settlement_code,
            already_reason="repair_order.push_settlement.already_exists",
            not_allowed_reason="repair_order.push_settlement.not_allowed",
            require_acceptance=True,
        ),
        push_return_visit=_push_cap(
            already_code=existing_visit_code,
            already_reason="repair_order.push_return_visit.already_exists",
            not_allowed_reason="repair_order.push_return_visit.not_allowed",
        ),
    )


def assert_repair_order_capability(
    order: Any,
    action: str,
    *,
    existing_dispatch_code: Optional[str] = None,
    existing_settlement_code: Optional[str] = None,
    existing_visit_code: Optional[str] = None,
) -> None:
    caps = derive_repair_order_capabilities(
        order,
        existing_dispatch_code=existing_dispatch_code,
        existing_settlement_code=existing_settlement_code,
        existing_visit_code=existing_visit_code,
    )
    cap_map = {
        "update": caps.update,
        "delete": caps.delete,
        "close": caps.close,
        "push_dispatch": caps.push_dispatch,
        "push_settlement": caps.push_settlement,
        "push_return_visit": caps.push_return_visit,
    }
    cap = cap_map.get(action)
    if cap is None:
        raise ValueError(f"Unknown repair order capability action: {action}")
    if not cap.allowed:
        msg = CAPABILITY_REASON_MESSAGES.get(cap.reason or "", cap.reason or "操作不允许")
        raise BusinessLogicError(msg)
