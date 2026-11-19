"""采购申请来源类型判定（下推进度自愈依赖）。"""

from __future__ import annotations

from apps.kuaizhizao.utils.document_source_types import is_purchase_requisition_source_type


def test_accepts_snake_and_pascal_equivalents():
    assert is_purchase_requisition_source_type("purchase_requisition")
    assert is_purchase_requisition_source_type("PurchaseRequisition")
    assert is_purchase_requisition_source_type("  Purchase_Requisition  ")
    assert is_purchase_requisition_source_type("PURCHASE_REQUISITION")


def test_accepts_legacy_purchase_request_alias():
    # lower+去下划线后与 purchaserequest 对齐（历史写路径用过）
    assert is_purchase_requisition_source_type("purchase_request")
    assert is_purchase_requisition_source_type("PurchaseRequest")


def test_rejects_other_document_types_and_empty():
    assert not is_purchase_requisition_source_type(None)
    assert not is_purchase_requisition_source_type("")
    assert not is_purchase_requisition_source_type("purchase_order")
    assert not is_purchase_requisition_source_type("sales_order")
    assert not is_purchase_requisition_source_type("PurchaseOrder")
    # 连字符不会被归一，必须拒绝以免误认
    assert not is_purchase_requisition_source_type("purchase-requisition")
