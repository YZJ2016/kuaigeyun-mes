"""工程变更 ECN（L63）与设计更改申请（L65）列表进度勾选与提交校验。"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

ENTRY_SOURCE_DESIGN_CHANGE_REQUEST = "design_change_request"

DCR_HEADER_KEYS = (
    "content_before",
    "content_after",
    "change_product_type",
    "change_method",
)


def entry_source(row: Any) -> str:
    ext = getattr(row, "extension_payload", None)
    if isinstance(ext, dict):
        return str(ext.get("entry_source") or "engineering_change").strip().lower()
    return "engineering_change"


def is_design_change_request(row: Any) -> bool:
    return entry_source(row) == ENTRY_SOURCE_DESIGN_CHANGE_REQUEST


def rd_issued_at(row: Any) -> Optional[str]:
    ext = getattr(row, "extension_payload", None)
    if not isinstance(ext, dict):
        return None
    raw = str(ext.get("rd_issued_at") or "").strip()
    return raw or None


def dcr_request_ready(row: Any) -> bool:
    if not (getattr(row, "change_reason", None) or "").strip():
        return False
    ext = getattr(row, "extension_payload", None)
    for key in DCR_HEADER_KEYS:
        if not _ext(ext, key):
            return False
    return True


def validate_dcr_on_submit(row: Any) -> None:
    from infra.exceptions.exceptions import ValidationError

    if not dcr_request_ready(row):
        raise ValidationError(
            "设计更改申请须填写变更原因、变更前/后内容、更改产品类型及更改方式"
        )


def _ext(payload: Any, key: str) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get(key) or "").strip()


def ecn_rd_content_ready(row: Any, *, material_line_count: int) -> bool:
    if not (getattr(row, "change_reason", None) or "").strip():
        return False
    if material_line_count < 1:
        return False
    ext = getattr(row, "extension_payload", None)
    kind = (getattr(row, "change_kind", None) or "").strip().lower()
    if kind in {"material", "process", "drawing", "doc_template"}:
        if not _ext(ext, "content_before") or not _ext(ext, "content_after"):
            return False
    return True


def validate_ecn_rd_on_submit(row: Any, *, material_line_count: int) -> None:
    from infra.exceptions.exceptions import ValidationError

    if not ecn_rd_content_ready(row, material_line_count=material_line_count):
        raise ValidationError("研发发起须填写变更原因、变更前/后内容及至少一行变更物料")


def signoffs_complete(signoffs: Sequence[Any]) -> bool:
    if not signoffs:
        return False
    for sign in signoffs:
        status = (getattr(sign, "status", None) or "").strip().lower()
        if status not in {"signed", "skipped"}:
            return False
    return True


def compute_ecn_capabilities(
    row: Any,
    *,
    signoffs: Iterable[Any],
    material_line_count: int = 0,
) -> dict[str, bool]:
    """L63 列表勾选：研发填报、会签完成、审过、ERP 归档。"""
    status = (getattr(row, "status", None) or "").strip().lower()
    signoff_list = list(signoffs)
    rd_ready = ecn_rd_content_ready(row, material_line_count=material_line_count)
    signoffs_done = signoffs_complete(signoff_list)
    approved = status in {"erp_pending", "erp_failed", "closed"} or getattr(
        row, "approved_at", None
    ) is not None
    erp_closed = status == "closed" or getattr(row, "closed_at", None) is not None
    return {
        "is_design_change_request": False,
        "request_ready": False,
        "issued_to_rd": False,
        "rd_ready": rd_ready,
        "signoffs_done": signoffs_done,
        "approved": approved and rd_ready,
        "erp_closed": erp_closed,
    }


def compute_dcr_capabilities(
    row: Any,
    *,
    signoffs: Iterable[Any],
    material_line_count: int = 0,
) -> dict[str, bool]:
    """L65 列表勾选：变更需求、审过、下发研发；下发后叠加 L63 研发/会签/归档态。"""
    status = (getattr(row, "status", None) or "").strip().lower()
    request_ready = dcr_request_ready(row)
    dept_approved = status in {"approved", "erp_pending", "erp_failed", "closed"} or getattr(
        row, "approved_at", None
    ) is not None
    issued = bool(rd_issued_at(row))
    caps: dict[str, bool] = {
        "is_design_change_request": True,
        "request_ready": request_ready,
        "issued_to_rd": issued,
        "approved": dept_approved and request_ready,
        "rd_ready": False,
        "signoffs_done": False,
        "erp_closed": status == "closed" or getattr(row, "closed_at", None) is not None,
    }
    if issued:
        ecn = compute_ecn_capabilities(
            row, signoffs=signoffs, material_line_count=material_line_count
        )
        caps["rd_ready"] = ecn["rd_ready"]
        caps["signoffs_done"] = ecn["signoffs_done"]
        caps["erp_closed"] = ecn["erp_closed"]
        if ecn["approved"]:
            caps["approved"] = True
    return caps


def compute_engineering_change_capabilities(
    row: Any,
    *,
    signoffs: Iterable[Any],
    material_line_count: int = 0,
) -> dict[str, bool]:
    if is_design_change_request(row):
        return compute_dcr_capabilities(
            row, signoffs=signoffs, material_line_count=material_line_count
        )
    return compute_ecn_capabilities(
        row, signoffs=signoffs, material_line_count=material_line_count
    )
