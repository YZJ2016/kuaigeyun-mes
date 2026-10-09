"""样机制作书（L64）列表进度勾选。"""

from __future__ import annotations

from typing import Any, Optional


def _section_ready(requirements: Optional[str], attachments: Any) -> bool:
    if requirements and str(requirements).strip():
        return True
    if isinstance(attachments, list) and len(attachments) > 0:
        return True
    return False


def compute_prototype_build_sheet_capabilities(row: Any) -> dict[str, bool]:
    """L64 列表勾选：项目、电子、结构、审过、下发、会签完成。"""
    status = (getattr(row, "status", None) or "").strip().lower()
    project_ready = _section_ready(
        getattr(row, "project_requirements", None),
        getattr(row, "project_attachments", None),
    )
    electronics_ready = (getattr(row, "electronics_status", None) or "").strip().lower() == "ready"
    structure_ready = (getattr(row, "structure_status", None) or "").strip().lower() == "ready"
    approved = status in {"approved", "issued", "closed"} or getattr(row, "approved_at", None) is not None
    issued = status in {"issued", "closed"} or getattr(row, "issued_at", None) is not None
    mfg = str(getattr(row, "manufacturing_opinion", None) or "").strip()
    qa = str(getattr(row, "quality_opinion", None) or "").strip()
    signoffs_done = bool(mfg and qa)
    closed = status == "closed" or getattr(row, "closed_at", None) is not None
    return {
        "project_ready": project_ready,
        "electronics_ready": electronics_ready,
        "structure_ready": structure_ready,
        "approved": approved and project_ready and electronics_ready and structure_ready,
        "issued": issued,
        "signoffs_done": signoffs_done,
        "closed": closed,
    }
