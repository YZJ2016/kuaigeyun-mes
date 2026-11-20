"""未审核单据打印门禁（系统参数 parameters.common.allow_print_unaudited）。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Iterator, Optional

from apps.kuaizhizao.services.document_action_policy.types import ActionCapability
from apps.kuaizhizao.services.document_lifecycle_service import (
    _is_approved,
    _is_audited,
    _is_confirmed,
)
from infra.exceptions.exceptions import BusinessLogicError

PRINT_UNAUDITED_DENIED_REASON = "document.print.unaudited_denied"

_allow_print_unaudited_stack: ContextVar[list[bool]] = ContextVar(
    "_allow_print_unaudited_stack", default=[]
)


def _record_field(record: Any, name: str) -> Any:
    if record is None:
        return None
    if isinstance(record, dict):
        return record.get(name)
    return getattr(record, name, None)


def _record_tenant_id(record: Any) -> Optional[int]:
    raw = _record_field(record, "tenant_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def is_document_review_approved_for_print(record: Any) -> bool:
    """审核通过含免审写入的已通过/已审核态。"""
    review_status = _record_field(record, "review_status")
    if _is_approved(review_status):
        return True
    for status_key in ("status_code", "status"):
        status = _record_field(record, status_key)
        if _is_audited(status) or _is_confirmed(status):
            return True
    return False


def apply_allow_print_unaudited_gate(
    print_cap: ActionCapability,
    *,
    allow_print_unaudited: bool,
    is_review_approved: bool,
    reason_code: str = PRINT_UNAUDITED_DENIED_REASON,
) -> ActionCapability:
    if allow_print_unaudited or is_review_approved:
        return print_cap
    return ActionCapability(allowed=False, reason=reason_code)


def apply_print_unaudited_gate_to_capabilities(
    caps: Any,
    record: Any,
    *,
    allow_print_unaudited: bool,
) -> Any:
    if allow_print_unaudited:
        return caps
    if is_document_review_approved_for_print(record):
        return caps
    updates: dict[str, ActionCapability] = {}
    for attr in ("print", "print_formal"):
        cap = getattr(caps, attr, None)
        if cap is None:
            continue
        if cap.allowed:
            updates[attr] = ActionCapability(
                allowed=False,
                reason=PRINT_UNAUDITED_DENIED_REASON,
            )
    if not updates:
        return caps
    if hasattr(caps, "model_copy"):
        return caps.model_copy(update=updates)
    for key, cap in updates.items():
        setattr(caps, key, cap)
    return caps


def resolve_allow_print_unaudited_for_attach(
  record: Any,
  *,
  explicit: Optional[bool],
) -> bool:
    if explicit is not None:
        return explicit
    stack = _allow_print_unaudited_stack.get()
    if stack:
        return bool(stack[-1])
    from infra.services.business_config_service import peek_allow_print_unaudited

    tenant_id = _record_tenant_id(record)
    if tenant_id is not None:
        return peek_allow_print_unaudited(tenant_id)
    return True


@contextmanager
def push_allow_print_unaudited(allow: bool) -> Iterator[None]:
    stack = list(_allow_print_unaudited_stack.get())
    stack.append(bool(allow))
    token: Token = _allow_print_unaudited_stack.set(stack)
    try:
        yield
    finally:
        _allow_print_unaudited_stack.reset(token)


async def assert_allow_print_unaudited_or_raise(
    tenant_id: int,
    record: Any,
    *,
    default_message: str,
) -> None:
    from infra.services.business_config_service import BusinessConfigService

    allow = await BusinessConfigService().get_allow_print_unaudited(tenant_id)
    if allow or is_document_review_approved_for_print(record):
        return
    raise BusinessLogicError(default_message)