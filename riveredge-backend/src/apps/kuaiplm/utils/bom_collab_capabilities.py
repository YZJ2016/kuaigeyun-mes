"""BOM 协同（L59）列表进度勾选。"""

from __future__ import annotations

from typing import Any, Optional


def compute_bom_collab_capabilities(
    row: Any,
    *,
    electronics_line_count: int = 0,
    structure_line_count: int = 0,
) -> dict[str, bool]:
    e_ready = (getattr(row, "electronics_status", None) or "").strip().lower() == "ready"
    s_ready = (getattr(row, "structure_status", None) or "").strip().lower() == "ready"
    if electronics_line_count > 0:
        e_ready = True
    if structure_line_count > 0:
        s_ready = True
    status = (getattr(row, "status", None) or "").strip().lower()
    approved = status in {"approved", "entered"} or getattr(row, "approved_at", None) is not None
    clerk_entered = status == "entered" or getattr(row, "entered_at", None) is not None
    return {
        "electronics_ready": e_ready,
        "structure_ready": s_ready,
        "approved": approved,
        "clerk_entered": clerk_entered,
    }
