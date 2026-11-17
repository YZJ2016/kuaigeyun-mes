"""单据来源类型判定（转单/下推回写共用）。"""

from __future__ import annotations

from typing import Optional


def is_purchase_requisition_source_type(source_type: Optional[str]) -> bool:
    """认 purchase_requisition / PurchaseRequisition 等等价写法。"""
    key = (source_type or "").strip().lower().replace("_", "")
    return key in {"purchaserequest", "purchaserequisition"}


def is_purchase_inquiry_source_type(source_type: Optional[str]) -> bool:
    """认 purchase_inquiry / PurchaseInquiry / PurchaseInquiryItem 等等价写法。"""
    key = (source_type or "").strip().lower().replace("_", "")
    return key in {"purchaseinquiry", "purchaseinquiryitem"}
