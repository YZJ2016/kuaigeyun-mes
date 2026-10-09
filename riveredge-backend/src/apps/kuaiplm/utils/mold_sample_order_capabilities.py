"""开模合同/打样订单（L67）列表进度勾选与提交校验。"""

from __future__ import annotations

from typing import Any


def mold_sample_file_ready(row: Any) -> bool:
    return bool(str(getattr(row, "file_uuid", None) or "").strip())


def validate_mold_sample_file_on_submit(row: Any) -> None:
    from infra.exceptions.exceptions import ValidationError

    if not mold_sample_file_ready(row):
        raise ValidationError("提交前须上传合同或订单文件")


def compute_mold_sample_order_capabilities(row: Any) -> dict[str, bool]:
    """L67 列表勾选：文件上传、审过、用印、存档。"""
    status = (getattr(row, "status", None) or "").strip().lower()
    uploaded = mold_sample_file_ready(row)
    submitted = getattr(row, "submitted_at", None) is not None or status not in {
        "draft",
        "rejected",
    }
    approved = status in {"approved", "sealed", "archived"} or getattr(
        row, "approved_at", None
    ) is not None
    sealed = status in {"sealed", "archived"} or getattr(row, "sealed_at", None) is not None
    archived = status == "archived" or getattr(row, "archived_at", None) is not None
    return {
        "file_uploaded": uploaded,
        "submitted": submitted and uploaded,
        "approved": approved and submitted,
        "sealed": sealed,
        "archived": archived,
    }
