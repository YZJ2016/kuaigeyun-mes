"""同步运行 trigger_kind 上下文（写入 core_sync_run_logs）。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

SYNC_TRIGGER_KIND_MANUAL = "manual"
SYNC_TRIGGER_KIND_TRIGGER = "trigger"
SYNC_TRIGGER_KIND_SCHEDULED = "scheduled"

SYNC_TRIGGER_KINDS = frozenset(
    {
        SYNC_TRIGGER_KIND_MANUAL,
        SYNC_TRIGGER_KIND_TRIGGER,
        SYNC_TRIGGER_KIND_SCHEDULED,
    }
)

_trigger_kind_var: ContextVar[str] = ContextVar(
    "sync_run_trigger_kind",
    default=SYNC_TRIGGER_KIND_MANUAL,
)


def current_sync_trigger_kind() -> str:
    return _trigger_kind_var.get()


@contextmanager
def sync_run_trigger_kind(kind: str):
    normalized = kind if kind in SYNC_TRIGGER_KINDS else SYNC_TRIGGER_KIND_MANUAL
    token = _trigger_kind_var.set(normalized)
    try:
        yield
    finally:
        _trigger_kind_var.reset(token)
