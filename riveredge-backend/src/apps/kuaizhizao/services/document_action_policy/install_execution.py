"""安装执行业务态 capabilities。"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from infra.exceptions.exceptions import BusinessLogicError

from apps.kuaizhizao.services.document_action_policy.types import (
    CAPABILITY_REASON_MESSAGES,
    ActionCapability,
    InstallExecutionCapabilities,
)

_CLOSED = "已关闭"
_PUSHABLE_STATUSES = frozenset({"待派工", "进行中", "待验收"})


def _cap(allowed: bool, reason: Optional[str] = None) -> ActionCapability:
    return ActionCapability(allowed=allowed, reason=reason if not allowed else None)


def derive_install_execution_capabilities(
    job: Any,
    stages: Optional[Sequence[Any]] = None,
    *,
    existing_dispatch_code: Optional[str] = None,
    existing_settlement_code: Optional[str] = None,
) -> InstallExecutionCapabilities:
    status = str(getattr(job, "status", "") or "").strip()
    closed = status == _CLOSED

    has_stages = bool(stages)
    has_pending_stage = False
    if stages:
        has_pending_stage = any(
            str(getattr(s, "status", "") or "").strip() != "已完成" for s in stages
        )

    def _push_dispatch() -> ActionCapability:
        if closed:
            return _cap(False, "install_execution.push.closed")
        if status not in _PUSHABLE_STATUSES:
            return _cap(False, "install_execution.push_dispatch.not_allowed")
        if existing_dispatch_code:
            return _cap(False, "install_execution.push_dispatch.already_exists")
        return _cap(True)

    def _push_settlement() -> ActionCapability:
        if closed:
            return _cap(False, "install_execution.push.closed")
        if status not in {"进行中", "待验收"}:
            return _cap(False, "install_execution.push_settlement.not_ready")
        if existing_settlement_code:
            return _cap(False, "install_execution.push_settlement.already_exists")
        return _cap(True)

    return InstallExecutionCapabilities(
        update=_cap(not closed, "install_execution.update.closed" if closed else None),
        delete=_cap(not closed, "install_execution.delete.closed" if closed else None),
        close=_cap(not closed, "install_execution.close.already_closed" if closed else None),
        assign_task=_cap(not closed, "install_execution.assign_task.closed" if closed else None),
        advance_stage=_cap(
            not closed and has_stages and has_pending_stage,
            "install_execution.advance_stage.closed"
            if closed
            else (
                "install_execution.advance_stage.no_stages"
                if not has_stages
                else "install_execution.advance_stage.no_pending"
            ),
        ),
        register_cost=_cap(
            not closed,
            "install_execution.register_cost.closed" if closed else None,
        ),
        push_dispatch=_push_dispatch(),
        push_settlement=_push_settlement(),
    )


def assert_install_execution_capability(
    job: Any,
    action: str,
    stages: Optional[Sequence[Any]] = None,
    *,
    existing_dispatch_code: Optional[str] = None,
    existing_settlement_code: Optional[str] = None,
) -> None:
    caps = derive_install_execution_capabilities(
        job,
        stages,
        existing_dispatch_code=existing_dispatch_code,
        existing_settlement_code=existing_settlement_code,
    )
    cap_map = {
        "update": caps.update,
        "delete": caps.delete,
        "close": caps.close,
        "assign_task": caps.assign_task,
        "advance_stage": caps.advance_stage,
        "register_cost": caps.register_cost,
        "push_dispatch": caps.push_dispatch,
        "push_settlement": caps.push_settlement,
    }
    cap = cap_map.get(action)
    if cap is None:
        raise ValueError(f"Unknown install execution capability action: {action}")
    if not cap.allowed:
        msg = CAPABILITY_REASON_MESSAGES.get(cap.reason or "", cap.reason or "操作不允许")
        raise BusinessLogicError(msg)
