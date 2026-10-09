"""项目归档资料（L66）列表进度勾选。"""

from __future__ import annotations

from typing import Any

from apps.kuaiplm.constants.rd_project_system_archive import SYSTEM_ARCHIVE_TOTAL_COUNT


def compute_system_archive_capabilities(summary: Any) -> dict[str, bool]:
    """L66：清单就绪、已有关联或上传、清单齐备、验收通过。"""
    if summary is None:
        return {
            "checklist_ready": False,
            "upload_link_started": False,
            "checklist_complete": False,
            "all_accepted": False,
        }
    if isinstance(summary, dict):
        total = int(summary.get("total") or 0)
        filled = int(summary.get("filled") or 0)
        missing = int(summary.get("missing_marked") or 0)
        complete = bool(summary.get("complete"))
        all_accepted = bool(summary.get("all_accepted"))
    else:
        total = int(getattr(summary, "total", 0) or 0)
        filled = int(getattr(summary, "filled", 0) or 0)
        missing = int(getattr(summary, "missing_marked", 0) or 0)
        complete = bool(getattr(summary, "complete", False))
        all_accepted = bool(getattr(summary, "all_accepted", False))
    checklist_ready = total >= SYSTEM_ARCHIVE_TOTAL_COUNT and total > 0
    started = (filled + missing) > 0
    return {
        "checklist_ready": checklist_ready,
        "upload_link_started": started,
        "checklist_complete": complete and checklist_ready,
        "all_accepted": all_accepted and checklist_ready,
    }
