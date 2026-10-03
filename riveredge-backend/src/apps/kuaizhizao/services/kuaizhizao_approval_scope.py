"""快制造审批实例判定（与 mobile kuaizhizaoApprovalFilter 一致）。"""

from __future__ import annotations

from typing import Any

KUAIZHIZAO_APPROVAL_ENTITY_TYPES = frozenset(
    {
        "sales_order",
        "sales_order_change",
        "sales_forecast",
        "sales_contract",
        "quotation",
        "shipment_notice",
        "sales_delivery",
        "freight_bill",
        "sales_return",
        "sales_contract_change",
        "demand",
        "purchase_order",
        "purchase_order_change",
        "purchase_arrival_delay",
        "purchase_request",
        "receipt_notice",
        "purchase_inquiry",
        "purchase_return",
        "reporting_record",
        "incoming_inspection",
        "process_inspection",
        "finished_goods_inspection",
        "oqc_inspection",
        "rework_order",
        "work_order",
        "production_picking",
        "supplier_evaluation",
        "quality_complaint",
    }
)


def is_kuaizhizao_approval_data(data: dict[str, Any]) -> bool:
    entity_type = str(data.get("entity_type") or "").strip().lower()
    if entity_type and entity_type in KUAIZHIZAO_APPROVAL_ENTITY_TYPES:
        return True
    app = str(data.get("app") or data.get("app_code") or "").strip().lower()
    if app == "kuaizhizao":
        return True
    path = str(data.get("detail_path") or "").lower()
    if "/apps/kuaizhizao/" in path:
        return True
    if "kuaioa" in path or "kuaiplm" in path or "master-data" in path:
        return False
    return False
