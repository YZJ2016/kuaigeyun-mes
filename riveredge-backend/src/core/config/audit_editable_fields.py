"""审核中可编辑字段注册表（按 entity_type）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

EditableFieldsSpec = Union[List[str], str]

EditableFieldMeta = Dict[str, Any]

_FIELD_META: Dict[str, EditableFieldMeta] = {
    "delivery_date": {"label": "交货日期", "type": "string"},
    "customer_contact": {"label": "联系人", "type": "string"},
    "customer_phone": {"label": "电话", "type": "string"},
    "total_amount": {"label": "金额", "type": "number"},
    "discount_amount": {"label": "折扣金额", "type": "number"},
    "salesman_name": {"label": "销售人员", "type": "string"},
    "shipping_address": {"label": "收货地址", "type": "text"},
    "shipping_method": {"label": "交货方式", "type": "string"},
    "payment_terms": {"label": "付款条件", "type": "string"},
    "notes": {"label": "备注", "type": "text"},
    "items": {"label": "明细", "type": "json"},
    "required_date": {"label": "需求日期", "type": "string"},
    "requisition_name": {"label": "名称", "type": "string"},
    "requisition_date": {"label": "申请日期", "type": "string"},
    "applicant_id": {"label": "申请人", "type": "number"},
    "applicant_name": {"label": "申请人", "type": "string"},
    "attachments": {"label": "附件", "type": "json"},
    "total_quantity": {"label": "数量", "type": "number"},
    "priority": {"label": "优先级", "type": "string"},
    "demand_date": {"label": "需求日期", "type": "string"},
    "milestones": {"label": "里程碑", "type": "json"},
    "valid_from": {"label": "有效期起", "type": "string"},
    "valid_to": {"label": "有效期止", "type": "string"},
    "forecast_name": {"label": "预测名称", "type": "string"},
    "start_date": {"label": "开始日期", "type": "string"},
    "end_date": {"label": "结束日期", "type": "string"},
    "change_reason": {"label": "变更原因", "type": "text"},
    "effective_date": {"label": "生效日期", "type": "string"},
    "header_changes": {"label": "表头变更", "type": "json"},
    "change_category": {"label": "变更分类", "type": "string"},
    "vendors": {"label": "供应商", "type": "json"},
    "inquiry_name": {"label": "询价名称", "type": "string"},
    "inquiry_date": {"label": "询价日期", "type": "string"},
    "quote_deadline": {"label": "报价截止", "type": "string"},
    "deduct_enabled": {"label": "是否扣款", "type": "boolean"},
    "deduct_amount": {"label": "扣款金额", "type": "number"},
}


def _catalog(keys: List[str]) -> List[EditableFieldMeta]:
    out: List[EditableFieldMeta] = []
    for key in keys:
        meta = _FIELD_META.get(key) or {"label": key, "type": "string"}
        out.append({"field": key, "label": meta["label"], "type": meta["type"]})
    return out


_EDITABLE_CATALOG: Dict[str, List[EditableFieldMeta]] = {
    "sales_order": _catalog(
        [
            "delivery_date",
            "customer_contact",
            "customer_phone",
            "total_amount",
            "discount_amount",
            "salesman_name",
            "shipping_address",
            "shipping_method",
            "payment_terms",
            "notes",
            "items",
        ]
    ),
    "purchase_order": _catalog(["delivery_date", "total_amount", "notes", "items"]),
    "quotation": _catalog(
        ["notes", "items", "total_amount", "total_quantity", "delivery_date", "discount_amount"]
    ),
    "demand": _catalog(["priority", "notes", "delivery_date", "demand_date", "items"]),
    "sales_contract": _catalog(
        [
            "notes",
            "items",
            "milestones",
            "customer_contact",
            "customer_phone",
            "shipping_address",
            "shipping_method",
            "payment_terms",
            "valid_from",
            "valid_to",
            "attachments",
            "discount_amount",
        ]
    ),
    "purchase_request": _catalog(
        [
            "notes",
            "items",
            "required_date",
            "requisition_name",
            "requisition_date",
            "applicant_id",
            "applicant_name",
            "attachments",
        ]
    ),
    "sales_forecast": _catalog(["notes", "items", "forecast_name", "start_date", "end_date", "attachments"]),
    "sales_order_change": _catalog(
        ["change_reason", "items", "effective_date", "header_changes", "notes", "attachments", "change_category"]
    ),
    "purchase_order_change": _catalog(
        ["change_reason", "items", "effective_date", "header_changes", "notes", "attachments", "change_category"]
    ),
    "purchase_inquiry": _catalog(
        ["notes", "items", "vendors", "inquiry_name", "inquiry_date", "quote_deadline"]
    ),
    "kuaioa_leave": _catalog(["deduct_amount"]),
}

_DEFAULT_EDITABLE_KEYS: Dict[str, List[str]] = {
    k: [item["field"] for item in v] for k, v in _EDITABLE_CATALOG.items()
}

_LOCKED_FIELDS = frozenset({"status", "review_status", "id", "uuid", "tenant_id"})


def editable_fields_catalog_for_entity(entity_type: str) -> List[EditableFieldMeta]:
    key = (entity_type or "").strip()
    return list(_EDITABLE_CATALOG.get(key, []))


def editable_fields_for_entity(entity_type: str) -> EditableFieldsSpec:
    key = (entity_type or "").strip()
    return list(_DEFAULT_EDITABLE_KEYS.get(key, []))


def is_field_editable(
    entity_type: str,
    field: str,
    node_editable: Optional[List[str]] = None,
) -> bool:
    if field in _LOCKED_FIELDS:
        return False
    if node_editable:
        if node_editable == "*" or (isinstance(node_editable, list) and "*" in node_editable):
            return field not in _LOCKED_FIELDS
        return field in node_editable
    spec = editable_fields_for_entity(entity_type)
    if spec == "*":
        return field not in _LOCKED_FIELDS
    if isinstance(spec, list):
        return field in spec
    return False
