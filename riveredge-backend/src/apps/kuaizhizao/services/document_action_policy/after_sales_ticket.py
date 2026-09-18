"""售后服务工单业务态 capabilities（唯一真源，与 service 门禁一致）。"""

from __future__ import annotations

from typing import Any, Optional

from infra.exceptions.exceptions import BusinessLogicError

from apps.kuaizhizao.services.document_action_policy.types import (
    CAPABILITY_REASON_MESSAGES,
    ActionCapability,
    AfterSalesTicketCapabilities,
)

_PUSHABLE_REQUEST_TYPES = frozenset({"退货", "换货"})
_CLOSED = "已关闭"


def _cap(allowed: bool, reason: Optional[str] = None) -> ActionCapability:
    return ActionCapability(allowed=allowed, reason=reason if not allowed else None)


def derive_after_sales_ticket_capabilities(
    ticket: Any,
    *,
    has_items: bool = False,
    has_returnable_qty: bool = False,
    existing_repair_order_code: Optional[str] = None,
    existing_visit_code: Optional[str] = None,
) -> AfterSalesTicketCapabilities:
    status = str(getattr(ticket, "status", "") or "").strip()
    request_type = str(getattr(ticket, "request_type", "") or "").strip()
    sales_order_id = getattr(ticket, "sales_order_id", None)
    sales_return_id = getattr(ticket, "sales_return_id", None)
    closed = status == _CLOSED

    update_cap = _cap(
        not closed,
        "after_sales_ticket.update.closed" if closed else None,
    )
    delete_cap = _cap(True)
    close_cap = _cap(
        not closed,
        "after_sales_ticket.close.already_closed" if closed else None,
    )

    push_allowed = False
    push_reason = "after_sales_ticket.push_sales_return.not_allowed"
    if closed:
        push_reason = "after_sales_ticket.push_sales_return.closed"
    elif request_type not in _PUSHABLE_REQUEST_TYPES:
        push_reason = "after_sales_ticket.push_sales_return.request_type"
    elif not sales_order_id:
        push_reason = "after_sales_ticket.push_sales_return.no_sales_order"
    elif sales_return_id:
        push_reason = "after_sales_ticket.push_sales_return.already_pushed"
    elif not has_items:
        push_reason = "after_sales_ticket.push_sales_return.no_items"
    elif not has_returnable_qty:
        push_reason = "after_sales_ticket.push_sales_return.no_returnable"
    else:
        push_allowed = True
        push_reason = None

    repair_allowed = False
    repair_reason = "after_sales_ticket.push_repair_order.not_allowed"
    if closed:
        repair_reason = "after_sales_ticket.push_repair_order.closed"
    elif request_type != "维修":
        repair_reason = "after_sales_ticket.push_repair_order.request_type"
    elif existing_repair_order_code:
        repair_reason = "after_sales_ticket.push_repair_order.already_exists"
    else:
        repair_allowed = True
        repair_reason = None

    visit_allowed = False
    visit_reason = "after_sales_ticket.push_return_visit.not_allowed"
    if closed:
        visit_reason = "after_sales_ticket.push_return_visit.closed"
    elif existing_visit_code:
        visit_reason = "after_sales_ticket.push_return_visit.already_exists"
    else:
        visit_allowed = True
        visit_reason = None

    return AfterSalesTicketCapabilities(
        update=update_cap,
        delete=delete_cap,
        close=close_cap,
        push_sales_return=_cap(push_allowed, push_reason),
        push_repair_order=_cap(repair_allowed, repair_reason),
        push_return_visit=_cap(visit_allowed, visit_reason),
    )


def assert_after_sales_ticket_capability(
    ticket: Any,
    action: str,
    *,
    has_items: bool = False,
    has_returnable_qty: bool = False,
    existing_repair_order_code: Optional[str] = None,
    existing_visit_code: Optional[str] = None,
) -> None:
    caps = derive_after_sales_ticket_capabilities(
        ticket,
        has_items=has_items,
        has_returnable_qty=has_returnable_qty,
        existing_repair_order_code=existing_repair_order_code,
        existing_visit_code=existing_visit_code,
    )
    cap_map = {
        "update": caps.update,
        "delete": caps.delete,
        "close": caps.close,
        "push_sales_return": caps.push_sales_return,
        "push_repair_order": caps.push_repair_order,
        "push_return_visit": caps.push_return_visit,
    }
    cap = cap_map.get(action)
    if cap is None:
        raise ValueError(f"Unknown after-sales ticket capability action: {action}")
    if not cap.allowed:
        msg = CAPABILITY_REASON_MESSAGES.get(cap.reason or "", cap.reason or "操作不允许")
        raise BusinessLogicError(msg)
