"""项目建议书（L62）列表进度勾选与提交校验。"""

from __future__ import annotations

from typing import Any, List, Optional

from apps.kuaiplm.constants.project_proposal_template import (
    DEV_REQ_TYPES_NEED_SUPPLIER,
    SUPPLIER_ASSESSMENT_MATERIAL_KEYS,
)


def _needs_supplier_assessment(dev_req_types: Optional[List[str]]) -> bool:
    normalized = {str(x).strip().upper() for x in (dev_req_types or []) if str(x).strip()}
    return bool(normalized & DEV_REQ_TYPES_NEED_SUPPLIER)


def _supplier_assessment_ready(lines: Optional[List[Any]]) -> bool:
    if not lines:
        return False
    for line in lines:
        if isinstance(line, dict):
            text = str(line.get("suppliers_text") or "").strip()
        else:
            text = str(getattr(line, "suppliers_text", None) or "").strip()
        if not text:
            return False
    return True


def sales_content_ready(row: Any) -> bool:
    code = str(getattr(row, "project_code", None) or "").strip()
    name = str(getattr(row, "project_name", None) or "").strip()
    if not code or not name:
        return False
    customer = str(getattr(row, "customer_name", None) or "").strip()
    summary = str(getattr(row, "summary", None) or "").strip()
    product_lines = getattr(row, "product_lines", None) or []
    proposer = str(getattr(row, "proposer_name", None) or "").strip()
    return bool(customer or summary or product_lines or proposer)


def supplier_fill_ready(row: Any) -> bool:
    dev_req = list(getattr(row, "dev_req_types", None) or [])
    if _needs_supplier_assessment(dev_req):
        if not str(getattr(row, "summary", None) or "").strip():
            return False
        return _supplier_assessment_ready(list(getattr(row, "supplier_assessment_lines", None) or []))
    return bool(str(getattr(row, "supplier_name", None) or "").strip())


def validate_sales_content_on_submit(row: Any) -> None:
    from infra.exceptions.exceptions import ValidationError

    if not sales_content_ready(row):
        raise ValidationError("销售发起须填写客户、摘要、产品类型或提出人至少一项")


def validate_supplier_on_submit(row: Any) -> None:
    from infra.exceptions.exceptions import ValidationError

    if not supplier_fill_ready(row):
        dev_req = list(getattr(row, "dev_req_types", None) or [])
        if _needs_supplier_assessment(dev_req):
            raise ValidationError("开发要求为 D/E/F 类时，采购须完整填写供应商评审表")
        raise ValidationError("提交前须由采购填写供应商")


def compute_project_proposal_capabilities(row: Any) -> dict[str, bool]:
    """L62 列表勾选：销售发起、采购填供应商、审过、下发研发。"""
    status = (getattr(row, "status", None) or "").strip().lower()
    sales_ready = sales_content_ready(row)
    supplier_filled = supplier_fill_ready(row)
    approved = status in {"approved", "issued"} or getattr(row, "approved_at", None) is not None
    issued = status == "issued" or getattr(row, "issued_at", None) is not None
    return {
        "sales_ready": sales_ready,
        "supplier_filled": supplier_filled,
        "approved": approved and supplier_filled and sales_ready,
        "issued": issued,
    }
