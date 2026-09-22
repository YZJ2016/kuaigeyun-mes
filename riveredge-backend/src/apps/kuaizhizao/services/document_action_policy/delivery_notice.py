"""送货单业务态 capabilities（下推发货管理单等）。"""

from __future__ import annotations

from typing import Any, Optional

from apps.kuaizhizao.services.document_action_policy.types import (
    ActionCapability,
    CAPABILITY_REASON_MESSAGES,
    DeliveryNoticeCapabilities,
)
def _cap(allowed: bool, reason: Optional[str] = None) -> ActionCapability:
    return ActionCapability(allowed=allowed, reason=reason if not allowed else None)


def derive_delivery_notice_capabilities(
    notice: Any,
    *,
    has_active_freight_order: bool = False,
) -> DeliveryNoticeCapabilities:
    status = str(getattr(notice, "status", "") or "").strip()
    push_allowed = status in ("已发送", "已签收") and not has_active_freight_order
    push_reason: Optional[str] = None
    if status == "待发送":
        push_reason = "delivery_notice.push_freight_order.not_sent"
    elif has_active_freight_order:
        push_reason = "delivery_notice.push_freight_order.already_linked"
    elif status not in ("已发送", "已签收"):
        push_reason = "delivery_notice.push_freight_order.not_allowed"
    return DeliveryNoticeCapabilities(
        push_freight_order=_cap(push_allowed, push_reason),
    )


def assert_delivery_notice_push_freight(
    notice: Any,
    *,
    has_active_freight_order: bool = False,
) -> None:
    from infra.exceptions.exceptions import BusinessLogicError

    caps = derive_delivery_notice_capabilities(
        notice,
        has_active_freight_order=has_active_freight_order,
    )
    if not caps.push_freight_order.allowed:
        msg = CAPABILITY_REASON_MESSAGES.get(
            caps.push_freight_order.reason or "",
            caps.push_freight_order.reason or "不可下推发货管理单",
        )
        raise BusinessLogicError(msg)
