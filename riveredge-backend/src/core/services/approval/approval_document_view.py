"""审批详情关联单据视图：按 instance.data.entity_type + entity_id 取活单据。

与 uni_audit HANDLERS 同一套 entity_type 身份路由；返回已标注的抬头 + 明细，
供手机/PC 审批详情直接展示，禁止用提交时一行 content 代替单据。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Awaitable, Callable, Dict, List, Optional

from core.config.audit_registry import entry_by_entity_type, entry_by_entity_type_and_business
from core.schemas.approval_instance import (
    ApprovalDocumentField,
    ApprovalDocumentLine,
    ApprovalDocumentView,
    ApprovalInstanceResponse,
)
from core.utils.timezone_utils import to_api_isoformat
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User
from loguru import logger

LoaderFn = Callable[[int, int], Awaitable[Any]]

# 内部字段，不进审批抬头
_SKIP_KEYS = frozenset(
    {
        "id",
        "uuid",
        "tenant_id",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
        "deleted_at",
        "items",
        "lines",
        "details",
        "milestones",
        "operations",
        "measure_items",
        "measure_plan",
        "materials",
        "signoffs",
        "capabilities",
        "lifecycle",
        "attachments",
        "is_active",
        "audit",
        "review_status",
        "reviewer_id",
        "reviewer_name",
        "review_time",
        "review_remarks",
        "approval_status",
        "has_approval_instance",
        "released_sales_order_codes",
        "released_quantity",
        "released_amount",
        "enter_line_items",
        "party_type",
        "contract_terms",
        "variant_attributes",
        "selected_approver_user_ids",
        "selected_approver_by_node",
        "selected_approver_snapshot",
        "entity_type",
        "entity_id",
        "entity_uuid",
        "inngest_run_id",
        "permission_codes",
    }
)

# 本单编号（与 GLOBAL_DOC_DETAIL_BASIC_FIELD_RANK 段位 10 对齐）
_CODE_KEYS = (
    "contract_code",
    "order_code",
    "quotation_code",
    "forecast_code",
    "notice_code",
    "change_code",
    "return_code",
    "receipt_code",
    "inquiry_code",
    "requisition_code",
    "work_order_code",
    "rework_code",
    "inspection_code",
    "picking_code",
    "delivery_code",
    "demand_code",
    "report_code",
    "document_code",
    "firmware_code",
    "file_code",
    "drawing_code",
    "ecn_code",
    "trial_code",
    "proposal_code",
    "review_code",
    "complaint_code",
    "eval_code",
    "bill_code",
    "invoice_code",
    "receivable_code",
    "payable_code",
    "application_code",
    "payment_code",
    "expense_code",
    "income_code",
    "transfer_code",
    "statement_code",
    "leave_code",
    "request_code",
    "seal_code",
    "form_code",
    "asset_code",
    "plan_code",
    "code",
)

_FIELD_LABELS: Dict[str, str] = {
    "customer_name": "客户",
    "customer_contact": "联系人",
    "customer_phone": "电话",
    "supplier_name": "供应商",
    "supplier_contact": "联系人",
    "supplier_phone": "电话",
    "salesman_name": "销售人员",
    "buyer_name": "采购员",
    "applicant_name": "申请人",
    "worker_name": "作业人",
    "owner_name": "负责人",
    "contract_date": "签订日期",
    "order_date": "订单日期",
    "quotation_date": "报价日期",
    "inquiry_date": "询价日期",
    "requisition_date": "申请日期",
    "requisition_name": "名称",
    "required_date": "需求日期",
    "delivery_date": "交货日期",
    "planned_delivery_date": "计划交期",
    "estimated_arrival_date": "预计到货",
    "valid_from": "有效期起",
    "valid_to": "有效期止",
    "total_quantity": "数量",
    "quantity": "数量",
    "total_amount": "金额",
    "amount": "金额",
    "total_request_amount": "申请金额",
    "request_amount": "申请金额",
    "discount_amount": "折扣金额",
    "tax_amount": "税额",
    "payable_code": "应付单号",
    "line_kind": "请款类型",
    "price_type": "计价类型",
    "currency_code": "币种",
    "shipping_address": "收货地址",
    "shipping_method": "交货方式",
    "payment_terms": "付款条件",
    "term_group_name": "条款组",
    "quotation_code": "报价单号",
    "source_order_code": "来源订单",
    "source_code": "来源单号",
    "source_type": "来源",
    "contract_code": "合同编号",
    "contract_type": "合同类型",
    "notes": "备注",
    "remark": "备注",
    "reason": "原因",
    "title": "标题",
    "product_name": "产品",
    "product_code": "产品编码",
    "material_name": "物料",
    "material_code": "物料编码",
    "priority": "优先级",
    "demand_type": "需求类型",
    "business_mode": "业务模式",
    "forecast_name": "预测名称",
    "period": "周期",
    "warehouse_name": "仓库",
    "department_name": "部门",
    "project_name": "项目",
    "project_code": "项目编码",
    "carrier_name": "承运商",
    "leave_type": "请假类型",
    "employee_name": "员工",
    "start_at": "开始时间",
    "end_at": "结束时间",
    "deduct_enabled": "是否扣款",
    "deduct_amount": "扣款金额",
    "start_date": "开始日期",
    "end_date": "结束日期",
    "days": "天数",
    "start_time": "开始时间",
    "end_time": "结束时间",
    "seal_name": "印章",
    "copies": "份数",
    "usage": "用途",
    "form_name": "表单",
    "asset_name": "资产",
    "change_type": "变更类型",
    "change_kind": "变更类型",
    "change_reason": "变更原因",
    "remarks": "备注",
    "created_by_name": "创建人",
    "defect_description": "缺陷说明",
    "deviation_description": "偏离说明",
    "operation_name": "工序",
    "source_doc_no": "来源单号",
    "valid_until": "有效期至",
    "erp_ecn_no": "ERP 变更号",
    "delta_amount": "变更金额",
    "new_valid_to": "新有效期至",
    "new_total_amount": "新合同金额",
    "remaining_quantity": "剩余数量",
    "remaining_amount": "剩余金额",
    "inspection_kind": "检验类型",
    "result": "结果",
    "complaint_type": "投诉类型",
    "severity": "严重程度",
    "period_year": "年度",
    "score": "得分",
    "grade": "等级",
    "version_no": "版本",
    "version": "版本",
    "drawing_name": "图纸名称",
    "firmware_name": "固件名称",
    "file_name": "文件名称",
    "deliverable_name": "交付物",
    "trial_name": "试制名称",
    "proposal_title": "立项标题",
    "work_order_name": "工单名称",
    "plan_qty": "计划数量",
    "completed_qty": "完成数量",
    "unit": "单位",
    "material_unit": "单位",
    "unit_price": "单价",
    "tax_rate": "税率",
    "payment_code": "付款单号",
    "invoice_code": "发票号",
    "due_date": "到期日",
    "partner_name": "往来单位",
    "counterparty_name": "往来对象",
    "counterparty_kind": "往来类型",
    "counterparty_account_name": "收款户名",
    "counterparty_bank_name": "收款开户行",
    "counterparty_bank_account": "收款账号",
    "supplier_account_name": "收款户名",
    "supplier_bank_name": "收款开户行",
    "supplier_bank_account": "收款账号",
    "bank_account": "本方账户",
    "advance_payee_name": "领款人",
    "payment_method": "收付方式",
    "payment_reason": "付款事由",
    "application_kind": "请款类型",
    "settlement_type": "结算类型",
    "application_date": "申请日期",
    "expected_payment_date": "期望付款日",
    "business_date": "业务日期",
    "payment_date": "付款日期",
    "receipt_date": "收款日期",
    "paid_amount": "已付金额",
    "transfer_type": "调拨类型",
    "external_account_name": "外部户名",
    "external_bank_name": "外部开户行",
    "external_account_number": "外部账号",
    "statement_period": "对账周期",
    "opening_balance": "期初余额",
    "debit_total": "本期借方",
    "credit_total": "本期贷方",
    "closing_balance": "期末余额",
    "ledger_posting_mode": "立账方式",
    "invoice_number": "发票号码",
    "invoice_date": "开票日期",
    "bill_no": "票号",
    "bill_type": "票据类型",
    "drawer_name": "出票人",
    "acceptor_name": "承兑人",
    "accepting_bank": "承兑行",
    "direction": "票据方向",
    "partner_type": "单位类型",
    "content": "内容",
    "description": "说明",
    "comment": "说明",
    "new_contract_id": "新合同",
}

_HEADER_ORDER = (
    "customer_name",
    "supplier_name",
    "partner_name",
    "counterparty_name",
    "counterparty_kind",
    "payment_method",
    "application_kind",
    "settlement_type",
    "payment_reason",
    "counterparty_account_name",
    "counterparty_bank_name",
    "counterparty_bank_account",
    "supplier_account_name",
    "supplier_bank_name",
    "supplier_bank_account",
    "bank_account",
    "advance_payee_name",
    "business_date",
    "application_date",
    "expected_payment_date",
    "payment_date",
    "receipt_date",
    "customer_contact",
    "supplier_contact",
    "customer_phone",
    "supplier_phone",
    "applicant_name",
    "salesman_name",
    "buyer_name",
    "contract_date",
    "order_date",
    "quotation_date",
    "inquiry_date",
    "requisition_date",
    "requisition_name",
    "forecast_name",
    "work_order_name",
    "product_name",
    "product_code",
    "material_name",
    "material_code",
    "required_date",
    "delivery_date",
    "planned_delivery_date",
    "estimated_arrival_date",
    "valid_from",
    "valid_to",
    "start_date",
    "end_date",
    "start_time",
    "end_time",
    "days",
    "leave_type",
    "quantity",
    "total_quantity",
    "plan_qty",
    "completed_qty",
    "unit_price",
    "discount_amount",
    "tax_amount",
    "total_amount",
    "amount",
    "total_request_amount",
    "request_amount",
    "paid_amount",
    "statement_period",
    "opening_balance",
    "debit_total",
    "credit_total",
    "closing_balance",
    "ledger_posting_mode",
    "transfer_type",
    "external_account_name",
    "external_bank_name",
    "external_account_number",
    "invoice_number",
    "invoice_date",
    "bill_no",
    "bill_type",
    "drawer_name",
    "acceptor_name",
    "accepting_bank",
    "direction",
    "partner_type",
    "remaining_quantity",
    "remaining_amount",
    "delta_amount",
    "new_total_amount",
    "new_valid_to",
    "price_type",
    "currency_code",
    "shipping_method",
    "payment_terms",
    "shipping_address",
    "term_group_name",
    "quotation_code",
    "source_order_code",
    "source_code",
    "source_type",
    "contract_type",
    "change_type",
    "change_kind",
    "change_reason",
    "created_by_name",
    "defect_description",
    "deviation_description",
    "operation_name",
    "source_doc_no",
    "valid_until",
    "erp_ecn_no",
    "remarks",
    "demand_type",
    "business_mode",
    "priority",
    "warehouse_name",
    "department_name",
    "project_name",
    "project_code",
    "carrier_name",
    "seal_name",
    "copies",
    "usage",
    "form_name",
    "asset_name",
    "drawing_name",
    "firmware_name",
    "file_name",
    "deliverable_name",
    "trial_name",
    "proposal_title",
    "inspection_kind",
    "result",
    "complaint_type",
    "severity",
    "period",
    "period_year",
    "score",
    "grade",
    "version_no",
    "version",
    "due_date",
    "reason",
    "title",
    "content",
    "description",
    "comment",
    "notes",
    "remark",
)

_APPLICATION_KIND_LABELS: Dict[str, str] = {
    "prepayment": "预付款",
    "goods": "货款",
    "invoice": "发票请款",
    "mixed": "混合",
}

_SETTLEMENT_TYPE_LABELS: Dict[str, str] = {
    "normal": "普通",
    "prepayment": "预付款",
    "refund": "退款",
}

_COUNTERPARTY_KIND_LABELS: Dict[str, str] = {
    "none": "无",
    "customer": "客户",
    "supplier": "供应商",
    "employee": "员工",
    "other": "其他",
}

_TRANSFER_TYPE_LABELS: Dict[str, str] = {
    "internal": "内部互转",
    "external_out": "对外调出",
    "external_in": "对外调入",
}

_LEDGER_POSTING_MODE_LABELS: Dict[str, str] = {
    "immediate": "即时立账",
    "by_invoice": "按发票立账",
}

_NOTE_DIRECTION_LABELS: Dict[str, str] = {
    "receivable": "应收票据",
    "payable": "应付票据",
}

_PARTNER_TYPE_LABELS: Dict[str, str] = {
    "Customer": "客户",
    "Supplier": "供应商",
    "customer": "客户",
    "supplier": "供应商",
}


def _format_header_scalar(key: str, value: Any) -> Optional[str]:
    if key == "application_kind":
        raw = str(value or "").strip()
        if not raw:
            return None
        return _APPLICATION_KIND_LABELS.get(raw, raw)
    if key == "settlement_type":
        raw = str(value or "").strip()
        if not raw:
            return None
        return _SETTLEMENT_TYPE_LABELS.get(raw, raw)
    if key == "counterparty_kind":
        raw = str(value or "").strip()
        if not raw:
            return None
        return _COUNTERPARTY_KIND_LABELS.get(raw, raw)
    if key == "transfer_type":
        raw = str(value or "").strip()
        if not raw:
            return None
        return _TRANSFER_TYPE_LABELS.get(raw, raw)
    if key == "ledger_posting_mode":
        raw = str(value or "").strip()
        if not raw:
            return None
        return _LEDGER_POSTING_MODE_LABELS.get(raw, raw)
    if key == "direction":
        raw = str(value or "").strip()
        if not raw:
            return None
        return _NOTE_DIRECTION_LABELS.get(raw, raw)
    if key == "partner_type":
        raw = str(value or "").strip()
        if not raw:
            return None
        return _PARTNER_TYPE_LABELS.get(raw, raw)
    if key == "line_kind":
        raw = str(value or "").strip()
        if not raw:
            return None
        return _APPLICATION_KIND_LABELS.get(raw, raw)
    return _jsonable_scalar(value)


def _jsonable_scalar(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, datetime):
        return to_api_isoformat(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        if any(isinstance(item, (dict, list, tuple)) for item in value):
            return None
        parts = [str(item).strip() for item in value if item is not None and str(item).strip()]
        return "、".join(parts) or None
    if isinstance(value, dict):
        return None
    text = str(value).strip()
    return text or None


_LINE_COLLECTION_KEYS = (
    "items",
    "lines",
    "details",
    "materials",
    "measure_items",
    "operations",
    "purchase_detail_lines",
)


def _plain_line_rows(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        return []
    rows: List[Dict[str, Any]] = []
    for item in raw:
        if hasattr(item, "model_dump"):
            dumped = item.model_dump(mode="python")
            if isinstance(dumped, dict):
                rows.append(dumped)
        elif isinstance(item, dict):
            rows.append(item)
        else:
            meta = getattr(item, "_meta", None)
            db_fields = getattr(meta, "db_fields", None) if meta is not None else None
            if db_fields:
                rows.append({name: getattr(item, name, None) for name in db_fields})
    return rows


def _to_plain(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        dumped = obj.model_dump(mode="python")
        if isinstance(dumped, dict):
            # model_construct / model_copy 偶发把明细落成 None 或漏进 dump；从对象属性补回
            for key in _LINE_COLLECTION_KEYS:
                if isinstance(dumped.get(key), list) and dumped.get(key):
                    continue
                attr_rows = _plain_line_rows(getattr(obj, key, None))
                if attr_rows:
                    dumped[key] = attr_rows
            return dumped
    meta = getattr(obj, "_meta", None)
    db_fields = getattr(meta, "db_fields", None) if meta is not None else None
    if db_fields:
        payload = {name: getattr(obj, name, None) for name in db_fields}
        for key in _LINE_COLLECTION_KEYS:
            if key in payload and isinstance(payload.get(key), list) and payload.get(key):
                continue
            attr_rows = _plain_line_rows(getattr(obj, key, None))
            if attr_rows:
                payload[key] = attr_rows
        return payload
    raise ValidationError("无法读取审批关联单据字段")


def _pick_code(payload: Dict[str, Any]) -> str:
    for key in _CODE_KEYS:
        text = _jsonable_scalar(payload.get(key))
        if text:
            return text
    return ""


def _pick_status(payload: Dict[str, Any]) -> Optional[str]:
    return _jsonable_scalar(payload.get("status"))


def _iter_line_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in _LINE_COLLECTION_KEYS:
        rows = _plain_line_rows(payload.get(key))
        if rows:
            return rows
    return []


def _line_title(item: Dict[str, Any], index: int) -> str:
    name = _jsonable_scalar(
        item.get("material_name")
        or item.get("product_name")
        or item.get("item_name")
        or item.get("category_name")
        or item.get("operation_name")
        or item.get("name")
        or item.get("title")
    )
    if name:
        return name
    code = _jsonable_scalar(
        item.get("material_code")
        or item.get("product_code")
        or item.get("item_code")
        or item.get("category_code")
        or item.get("operation_code")
        or item.get("source_code")
        or item.get("payable_code")
    )
    if code:
        return code
    return f"明细 {index + 1}"


def _line_qty_text(item: Dict[str, Any]) -> Optional[str]:
    qty = _jsonable_scalar(
        item.get("contract_quantity")
        or item.get("quantity")
        or item.get("qty")
        or item.get("plan_qty")
        or item.get("request_qty")
    )
    unit = _jsonable_scalar(item.get("material_unit") or item.get("unit"))
    amount = _jsonable_scalar(
        item.get("total_amount")
        or item.get("amount")
        or item.get("line_amount")
        or item.get("request_amount")
    )
    parts: List[str] = []
    if qty:
        parts.append(f"{qty}{(' ' + unit) if unit else ''}".strip())
    if amount:
        parts.append(f"金额 {amount}")
    return "  ".join(parts) or None


def _line_meta(item: Dict[str, Any]) -> Optional[str]:
    delivery = _jsonable_scalar(
        item.get("delivery_date") or item.get("required_date") or item.get("plan_date")
    )
    notes = _jsonable_scalar(item.get("notes") or item.get("remark") or item.get("description"))
    parts: List[str] = []
    if delivery:
        parts.append(f"交期 {delivery}")
    if notes:
        parts.append(notes)
    return "  ".join(parts) or None


_LINE_KIND_LABELS: Dict[str, str] = {
    "prepayment": "预付款",
    "goods": "货款",
    "invoice": "发票请款",
    "mixed": "混合",
}


def _line_fields(item: Dict[str, Any]) -> List[ApprovalDocumentField]:
    """明细行结构化字段：审批详情手机端优先展示这些必要信息。"""
    fields: List[ApprovalDocumentField] = []

    def add(key: str, label: str, value: Optional[str]) -> None:
        text = str(value or "").strip()
        if not text:
            return
        fields.append(ApprovalDocumentField(key=key, label=label, value=text))

    po_code = _jsonable_scalar(item.get("purchase_order_code"))
    code = _jsonable_scalar(
        item.get("material_code")
        or item.get("product_code")
        or item.get("item_code")
        or item.get("category_code")
        or item.get("operation_code")
    )
    source_code = _jsonable_scalar(item.get("source_code"))
    source_type_raw = _jsonable_scalar(item.get("source_type"))
    payable_code = _jsonable_scalar(item.get("payable_code"))
    line_kind_raw = _jsonable_scalar(item.get("line_kind"))
    line_kind = (
        _LINE_KIND_LABELS.get(line_kind_raw, line_kind_raw) if line_kind_raw else None
    )
    spec = _jsonable_scalar(
        item.get("material_spec") or item.get("specification") or item.get("spec")
    )
    qty = _jsonable_scalar(
        item.get("contract_quantity")
        or item.get("quantity")
        or item.get("qty")
        or item.get("plan_qty")
        or item.get("request_qty")
    )
    unit = _jsonable_scalar(item.get("material_unit") or item.get("unit"))
    price = _jsonable_scalar(
        item.get("suggested_unit_price")
        or item.get("unit_price")
        or item.get("price")
    )
    amount = _jsonable_scalar(
        item.get("total_amount")
        or item.get("amount")
        or item.get("line_amount")
        or item.get("total_price")
        or item.get("request_amount")
    )
    delivery = _jsonable_scalar(
        item.get("delivery_date") or item.get("required_date") or item.get("plan_date")
    )
    summary = _jsonable_scalar(item.get("description"))
    notes = _jsonable_scalar(item.get("notes") or item.get("remark"))
    payee = _jsonable_scalar(item.get("payee_name"))
    aux_qty = _jsonable_scalar(item.get("aux_quantity"))
    aux_unit = _jsonable_scalar(item.get("aux_unit"))

    add("code", "编码", code)
    add("purchase_order_code", "采购订单", po_code)
    add("source_code", "来源单号", source_code)
    if source_type_raw:
        add("source_type", "来源类型", source_type_raw)
    add("payable_code", "应付单号", payable_code)
    add("line_kind", "请款类型", line_kind)
    add("spec", "规格", spec)
    if qty:
        add("quantity", "数量", f"{qty}{(' ' + unit) if unit else ''}".strip())
    elif unit:
        add("unit", "单位", unit)
    if aux_qty:
        add(
            "aux_quantity",
            "副数量",
            f"{aux_qty}{(' ' + aux_unit) if aux_unit else ''}".strip(),
        )
    add("unit_price", "单价", price)
    add("amount", "金额", amount)
    add("required_date", "交期", delivery)
    add("description", "摘要", summary)
    add("notes", "备注", notes)
    add("payee_name", "收款人", payee)
    gl_account = _jsonable_scalar(item.get("gl_account_code"))
    add("gl_account_code", "科目", gl_account)
    category_name = _jsonable_scalar(item.get("category_name"))
    add("category_name", "费用类别", category_name)

    if category_name and not _jsonable_scalar(item.get("material_code") or item.get("product_name")):
        by_key = {f.key: f for f in fields}
        ordered: List[ApprovalDocumentField] = []
        for key in (
            "category_name",
            "description",
            "amount",
            "payee_name",
            "gl_account_code",
        ):
            if key in by_key:
                ordered.append(by_key[key])
        seen_keys = {f.key for f in ordered}
        for field in fields:
            if field.key in seen_keys or field.key == "code":
                continue
            ordered.append(field)
        return ordered

    return fields


def _extract_attachments(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """单据附件列表（照片等）；保持结构化，不进抬头文本。"""
    from apps.kuaizhizao.utils.sales_order_attachment_carry import normalize_attachment_entry

    raw = payload.get("attachments")
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            normalized = normalize_attachment_entry(item)
            out.append(normalized if normalized else item)
        elif isinstance(item, str):
            normalized = normalize_attachment_entry(item)
            if normalized:
                out.append(normalized)
        elif hasattr(item, "model_dump"):
            dumped = item.model_dump(mode="python")
            if isinstance(dumped, dict):
                normalized = normalize_attachment_entry(dumped)
                out.append(normalized if normalized else dumped)
    return out


def compose_document_view(
    *,
    entity_type: str,
    entity_name: str,
    payload: Dict[str, Any],
) -> ApprovalDocumentView:
    code = _pick_code(payload)
    used_code_key = next((k for k in _CODE_KEYS if _jsonable_scalar(payload.get(k))), None)
    header: List[ApprovalDocumentField] = []
    seen: set[str] = set()
    if used_code_key:
        seen.add(used_code_key)

    def add_field(key: str) -> None:
        if key in seen or key in _SKIP_KEYS or key.endswith("_id"):
            return
        label = _FIELD_LABELS.get(key)
        if not label:
            return
        value = _format_header_scalar(key, payload.get(key))
        if not value:
            return
        seen.add(key)
        header.append(ApprovalDocumentField(key=key, label=label, value=value))

    for key in _HEADER_ORDER:
        add_field(key)
    for key in payload.keys():
        add_field(str(key))

    line_rows = _iter_line_rows(payload)
    if entity_type == "payment_application":
        detail_rows = _plain_line_rows(payload.get("purchase_detail_lines"))
        if detail_rows:
            payment_rows = _plain_line_rows(payload.get("items"))
            if payment_rows:
                line_rows = list(payment_rows) + list(detail_rows)
            else:
                line_rows = list(detail_rows)

    lines: List[ApprovalDocumentLine] = []
    for index, item in enumerate(line_rows):
        line_id = item.get("id")
        fields = _line_fields(item)
        lines.append(
            ApprovalDocumentLine(
                id=str(line_id if line_id is not None else index),
                title=_line_title(item, index),
                # 有结构化 fields 时不再堆叠 qty/meta，避免与字段重复
                meta=None if fields else _line_meta(item),
                qty_text=None if fields else _line_qty_text(item),
                fields=fields,
            )
        )
    return ApprovalDocumentView(
        entity_type=entity_type,
        entity_name=entity_name,
        code=code,
        status=_pick_status(payload),
        header=header,
        lines=lines,
        attachments=_extract_attachments(payload),
    )


def resolve_current_node_label(instance: Any) -> Optional[str]:
    from core.services.approval.approval_instance_service import ApprovalInstanceService

    return ApprovalInstanceService.node_display_label(instance)


async def resolve_submitter_name(instance: Any) -> Optional[str]:
    submitter_id = getattr(instance, "submitter_id", None)
    if not submitter_id:
        return None
    user = await User.get_or_none(id=int(submitter_id), deleted_at__isnull=True)
    if not user:
        return None
    return (user.full_name or user.username or "").strip() or None


def _entity_display_name(entity_type: str, business_type: Optional[str]) -> str:
    et = (entity_type or "").strip()
    bt = (business_type or "").strip()
    entry = entry_by_entity_type_and_business(et, bt) if bt else None
    if entry is None:
        entry = entry_by_entity_type(et)
    return entry.name if entry else et


def _require_row(row: Any, message: str) -> Any:
    if row is None:
        raise NotFoundError(message)
    return row


# ----- 活单据加载（与 HANDLERS entity_type 一一对应） -----


async def _load_sales_order(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.sales_order_service import SalesOrderService

    return await SalesOrderService().get_sales_order_by_id(
        tenant_id, entity_id, include_items=True
    )


async def _load_sales_order_change(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.sales_order_change_service import SalesOrderChangeService

    return await SalesOrderChangeService().get_by_id(tenant_id, entity_id)


async def _load_sales_forecast(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.sales_service import SalesForecastService

    return await SalesForecastService().get_sales_forecast_by_id(tenant_id, entity_id)


async def _load_sales_contract(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.sales_contract_service import SalesContractService

    return await SalesContractService().get_contract_by_id(
        tenant_id, entity_id, include_items=True
    )


async def _load_quotation(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.quotation_service import QuotationService

    return await QuotationService().get_quotation_by_id(
        tenant_id, entity_id, include_items=True
    )


async def _load_shipment_notice(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.shipment_notice_service import ShipmentNoticeService

    return await ShipmentNoticeService().get_shipment_notice_by_id(tenant_id, entity_id)


async def _load_sales_delivery(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.warehouse_service import SalesDeliveryService

    return await SalesDeliveryService().get_sales_delivery_by_id(tenant_id, entity_id)


async def _load_production_picking(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.warehouse_service import ProductionPickingService

    return await ProductionPickingService().get_production_picking_by_id(tenant_id, entity_id)


async def _load_work_order(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.work_order_service import WorkOrderService

    return await WorkOrderService().get_work_order_by_id(tenant_id, entity_id)


async def _load_sales_return(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.warehouse_service import SalesReturnService

    return await SalesReturnService().get_sales_return_by_id(tenant_id, entity_id)


async def _load_purchase_return(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.warehouse_service import PurchaseReturnService

    return await PurchaseReturnService().get_purchase_return_by_id(tenant_id, entity_id)


async def _load_receipt_notice(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.receipt_notice_service import ReceiptNoticeService

    return await ReceiptNoticeService().get_receipt_notice_by_id(tenant_id, entity_id)


async def _load_purchase_receipt(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.warehouse_service import PurchaseReceiptService

    return await PurchaseReceiptService().get_purchase_receipt_by_id(tenant_id, entity_id)


async def _load_sales_contract_change(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.models.sales_contract_change import SalesContractChange
    from apps.kuaizhizao.services.sales_contract_service import SalesContractService

    row = await SalesContractChange.get_or_none(
        tenant_id=tenant_id, id=entity_id, deleted_at__isnull=True
    )
    return await SalesContractService()._change_to_response(_require_row(row, "合同变更单不存在"))


async def _load_demand(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.demand_service import DemandService

    return await DemandService().get_demand_by_id(tenant_id, entity_id, include_items=True)


async def _load_purchase_order(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.purchase_service import PurchaseService

    return await PurchaseService().get_purchase_order_by_id(tenant_id, entity_id)


async def _load_purchase_order_change(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.purchase_order_change_service import PurchaseOrderChangeService

    return await PurchaseOrderChangeService().get_by_id(tenant_id, entity_id)


async def _load_purchase_arrival_delay(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.purchase_arrival_delay_service import PurchaseArrivalDelayService

    return await PurchaseArrivalDelayService().get_by_id(tenant_id, entity_id)


async def _load_purchase_request(tenant_id: int, entity_id: int) -> Any:
    """审批只读：直接组抬头+明细 dict，避开 service 富化路径上的空明细风险。"""
    from apps.kuaizhizao.models.purchase_requisition import (
        PurchaseRequisition,
        PurchaseRequisitionItem,
    )

    req = await PurchaseRequisition.get_or_none(
        tenant_id=tenant_id, id=entity_id, deleted_at__isnull=True
    )
    if not req:
        raise NotFoundError(f"采购申请不存在: {entity_id}")
    items = await PurchaseRequisitionItem.filter(
        tenant_id=tenant_id, requisition_id=entity_id
    ).all()
    payload = {name: getattr(req, name, None) for name in req._meta.db_fields}
    payload["items"] = [
        {name: getattr(it, name, None) for name in it._meta.db_fields} for it in items
    ]
    return payload


async def _load_payment_application(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.models.payment_application import PaymentApplicationLine
    from apps.kuaizhizao.services.payment_application_purchase_order_sources import (
        load_payment_application_print_purchase_order_items,
    )
    from apps.kuaizhizao.services.payment_application_service import PaymentApplicationService

    resp = await PaymentApplicationService().get_by_id(tenant_id, entity_id)
    payload = resp.model_dump(mode="python", by_alias=False)
    db_lines = await PaymentApplicationLine.filter(
        tenant_id=tenant_id, application_id=entity_id
    ).order_by("line_no")
    payload["purchase_detail_lines"] = await load_payment_application_print_purchase_order_items(
        tenant_id, db_lines
    )
    return payload


async def _load_quality_patrol(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.quality_patrol_service import QualityPatrolService

    return await QualityPatrolService().get_by_id(tenant_id, entity_id)


async def _load_outsource_inspection(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.outsource_inspection_service import OutsourceInspectionService

    return await OutsourceInspectionService().get_by_id(tenant_id, entity_id)


async def _load_partner_statement(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_finance_orm
    from apps.kuaicaiwu.services.partner_statement_service import PartnerStatementService

    require_finance_orm()
    return await PartnerStatementService().get_statement(tenant_id, entity_id)


async def _load_kuaioa_expense(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaioa", "轻办公")
    from apps.kuaioa.services.expense_service import ExpenseRequestService

    return await ExpenseRequestService().get_request(tenant_id, entity_id)


async def _load_purchase_inquiry(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.purchase_inquiry_service import PurchaseInquiryService

    return await PurchaseInquiryService().get_inquiry_by_id(tenant_id, entity_id)


async def _load_reporting_record(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.reporting_service import ReportingService

    return await ReportingService().get_reporting_record_by_id(tenant_id, entity_id)


async def _load_incoming_inspection(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.quality_service import IncomingInspectionService

    return await IncomingInspectionService().get_incoming_inspection_by_id(tenant_id, entity_id)


async def _load_process_inspection(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.quality_service import ProcessInspectionService

    return await ProcessInspectionService().get_process_inspection_by_id(tenant_id, entity_id)


async def _load_finished_goods_inspection(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.quality_service import FinishedGoodsInspectionService

    return await FinishedGoodsInspectionService().get_finished_goods_inspection_by_id(
        tenant_id, entity_id
    )


async def _load_oqc_inspection(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.quality_improvement_service import OQCInspectionService

    return await OQCInspectionService().get_by_id(tenant_id, entity_id)


async def _load_receivable(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_finance_orm

    require_finance_orm()
    from apps.kuaicaiwu.services.finance_service import ReceivableService

    return await ReceivableService().get_receivable_by_id(tenant_id, entity_id)


async def _load_payable(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_finance_orm

    require_finance_orm()
    from apps.kuaicaiwu.services.finance_service import PayableService

    return await PayableService().get_payable_by_id(tenant_id, entity_id)


async def _load_purchase_invoice(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_finance_orm

    require_finance_orm()
    from apps.kuaicaiwu.services.finance_service import PurchaseInvoiceService

    return await PurchaseInvoiceService().get_purchase_invoice_by_id(tenant_id, entity_id)


async def _load_bom_change(tenant_id: int, entity_id: int) -> Any:
    from apps.master_data.services.bom_change_service import BOMChangeService

    return await BOMChangeService._get_change_or_raise(tenant_id, entity_id)


async def _load_process_route_change(tenant_id: int, entity_id: int) -> Any:
    from apps.master_data.services.process_route_change_service import ProcessRouteChangeService

    return await ProcessRouteChangeService._get_change_or_raise(tenant_id, entity_id)


async def _load_drawing_change(tenant_id: int, entity_id: int) -> Any:
    from apps.master_data.services.drawing_change_service import DrawingChangeService

    return await DrawingChangeService._get_change_or_raise(tenant_id, entity_id)


async def _load_product_firmware(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaiplm", "星研发")
    from apps.kuaiplm.models.product_firmware import ProductFirmware
    from apps.kuaiplm.schemas.product_firmware import ProductFirmwareResponse

    row = await ProductFirmware.get_or_none(
        tenant_id=tenant_id, id=entity_id, deleted_at__isnull=True
    )
    return ProductFirmwareResponse.model_validate(_require_row(row, "产品固件不存在"))


async def _load_lab_request(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaiplm", "星研发")
    from apps.kuaiplm.services.lab_request_service import LabRequestService

    return await LabRequestService().get(tenant_id, entity_id)


async def _load_production_file(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaiplm", "星研发")
    from apps.kuaiplm.services.production_file_service import ProductionFileService

    return await ProductionFileService().get(tenant_id, entity_id)


async def _load_engineering_drawing(tenant_id: int, entity_id: int) -> Any:
    from apps.master_data.models.drawing import EngineeringDrawing

    row = await EngineeringDrawing.get_or_none(
        tenant_id=tenant_id, id=entity_id, deleted_at__isnull=True
    )
    return _require_row(row, "工程图纸不存在")


async def _load_trial_flow(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaiplm", "星研发")
    from apps.kuaiplm.services.trial_flow_service import TrialFlowService

    return await TrialFlowService().get(tenant_id, entity_id)


async def _load_rework_order(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.rework_order_service import ReworkOrderService

    return await ReworkOrderService().get_rework_order_by_id(tenant_id, entity_id)


async def _load_quality_complaint(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.quality_complaint_service import QualityComplaintService

    return await QualityComplaintService().get(tenant_id, entity_id)


async def _load_supplier_evaluation(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.supplier_evaluation_service import SupplierEvaluationService

    return await SupplierEvaluationService().get(tenant_id, entity_id)


async def _load_engineering_change(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaiplm", "星研发")
    from apps.kuaiplm.services.engineering_change_service import EngineeringChangeService

    return await EngineeringChangeService().get(tenant_id, entity_id)


async def _load_sample_process(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaiplm", "星研发")
    from apps.kuaiplm.services.sample_process_service import SampleProcessService

    return await SampleProcessService().get(tenant_id, entity_id)


async def _load_prototype_build_sheet(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaiplm", "星研发")
    from apps.kuaiplm.services.prototype_build_sheet_service import PrototypeBuildSheetService

    return await PrototypeBuildSheetService().get(tenant_id, entity_id)


async def _load_qms_system_document(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.quality_qms_service import QmsSystemDocumentService

    return await QmsSystemDocumentService().get_document(tenant_id, entity_id)


async def _load_rd_deliverable(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaiplm", "星研发")
    from apps.kuaiplm.models.rd_project import RdProjectDeliverable
    from apps.kuaiplm.schemas.rd_project import RdProjectDeliverableResponse

    row = await RdProjectDeliverable.get_or_none(
        tenant_id=tenant_id, id=entity_id, deleted_at__isnull=True
    )
    return RdProjectDeliverableResponse.model_validate(_require_row(row, "研发交付物不存在"))


async def _load_material_review(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaiplm", "星研发")
    from apps.kuaiplm.services.material_review_service import MaterialReviewService

    return await MaterialReviewService().get(tenant_id, entity_id)


async def _load_bom_collaboration(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaiplm", "星研发")
    from apps.kuaiplm.services.bom_collaboration_service import BomCollaborationService

    return await BomCollaborationService().get(tenant_id, entity_id)


async def _load_project_proposal(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaiplm", "星研发")
    from apps.kuaiplm.services.project_proposal_service import ProjectProposalService

    return await ProjectProposalService().get(tenant_id, entity_id)


async def _load_mold_sample(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaiplm", "星研发")
    from apps.kuaiplm.services.mold_sample_order_service import MoldSampleOrderService

    return await MoldSampleOrderService().get(tenant_id, entity_id)


async def _load_freight_bill(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaizhizao.services.freight_bill_service import FreightBillService

    return await FreightBillService().get_bill(tenant_id, entity_id)


async def _load_other_income(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaicaiwu.services.other_income_service import OtherIncomeService

    return await OtherIncomeService().get_by_id(tenant_id, entity_id)


async def _load_other_expense(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaicaiwu.services.other_expense_service import OtherExpenseService

    return await OtherExpenseService().get_by_id(tenant_id, entity_id)


async def _load_other_expense_application(tenant_id: int, entity_id: int) -> Any:
    from apps.kuaicaiwu.services.other_expense_application_service import (
        OtherExpenseApplicationService,
    )

    return await OtherExpenseApplicationService().get_by_id(tenant_id, entity_id)


async def _document_payload_from_orm(
    tenant_id: int,
    entity_id: int,
    model: Any,
    *,
    not_found_message: str,
    line_model: Any | None = None,
    line_parent_field: str = "",
) -> Dict[str, Any]:
    row = await model.get_or_none(
        tenant_id=tenant_id, id=entity_id, deleted_at__isnull=True
    )
    if not row:
        raise NotFoundError(not_found_message.format(entity_id=entity_id))
    payload = {name: getattr(row, name, None) for name in row._meta.db_fields}
    if line_model and line_parent_field:
        flt: Dict[str, Any] = {"tenant_id": tenant_id, line_parent_field: entity_id}
        meta = line_model._meta
        if "deleted_at" in meta.db_fields:
            flt["deleted_at__isnull"] = True
        qs = line_model.filter(**flt)
        if "line_no" in meta.db_fields:
            qs = qs.order_by("line_no", "id")
        else:
            qs = qs.order_by("id")
        line_rows = await qs.all()
        payload["items"] = [
            {name: getattr(it, name, None) for name in meta.db_fields} for it in line_rows
        ]
    return payload


async def _load_payment(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_finance_orm
    from apps.kuaicaiwu.models.payment import Payment
    from apps.kuaicaiwu.models.payment_pull_line import PaymentPullLine

    require_finance_orm()
    return await _document_payload_from_orm(
        tenant_id,
        entity_id,
        Payment,
        not_found_message="付款单不存在: {entity_id}",
        line_model=PaymentPullLine,
        line_parent_field="payment_id",
    )


async def _load_payment_refund(tenant_id: int, entity_id: int) -> Any:
    return await _load_payment(tenant_id, entity_id)


async def _load_receipt(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_finance_orm
    from apps.kuaicaiwu.models.receipt import Receipt

    require_finance_orm()
    return await _document_payload_from_orm(
        tenant_id,
        entity_id,
        Receipt,
        not_found_message="收款单不存在: {entity_id}",
    )


async def _load_receipt_refund(tenant_id: int, entity_id: int) -> Any:
    return await _load_receipt(tenant_id, entity_id)


async def _load_fund_transfer(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_finance_orm
    from apps.kuaicaiwu.models.fund_transfer import FundTransfer

    require_finance_orm()
    return await _document_payload_from_orm(
        tenant_id,
        entity_id,
        FundTransfer,
        not_found_message="资金调拨单不存在: {entity_id}",
    )


async def _load_sales_invoice(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_finance_orm
    from apps.kuaicaiwu.models.invoice import Invoice, InvoiceItem

    require_finance_orm()
    return await _document_payload_from_orm(
        tenant_id,
        entity_id,
        Invoice,
        not_found_message="销售发票不存在: {entity_id}",
        line_model=InvoiceItem,
        line_parent_field="invoice_id",
    )


async def _load_finance_note(
    tenant_id: int, entity_id: int, *, direction: str
) -> Dict[str, Any]:
    from apps.common.app_orm import require_finance_orm
    from apps.kuaicaiwu.models.finance_note import FinanceNote

    require_finance_orm()
    row = await FinanceNote.get_or_none(
        tenant_id=tenant_id, id=entity_id, deleted_at__isnull=True
    )
    if not row:
        raise NotFoundError(f"票据不存在: {entity_id}")
    if str(row.direction or "").strip() != direction:
        raise NotFoundError(f"票据方向不匹配: {entity_id}")
    return {name: getattr(row, name, None) for name in row._meta.db_fields}


async def _load_notes_receivable(tenant_id: int, entity_id: int) -> Any:
    return await _load_finance_note(tenant_id, entity_id, direction="receivable")


async def _load_notes_payable(tenant_id: int, entity_id: int) -> Any:
    return await _load_finance_note(tenant_id, entity_id, direction="payable")


async def _load_kuaioa_form_request(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaioa", "轻办公")
    from apps.kuaioa.services.form_service import FormRequestService

    return await FormRequestService().get_request(tenant_id, entity_id)


async def _load_kuaioa_asset_purchase(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaioa", "轻办公")
    from apps.kuaioa.services.asset_service import AssetPurchaseService

    return await AssetPurchaseService().get_purchase(tenant_id, entity_id)


async def _load_kuaioa_leave(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaioa", "轻办公")
    from apps.kuaioa.services.leave_service import LeaveRequestService

    return await LeaveRequestService().get_request(tenant_id, entity_id)


async def _load_kuaioa_seal(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaioa", "轻办公")
    from apps.kuaioa.services.seal_service import SealRequestService

    return await SealRequestService().get_request(tenant_id, entity_id)


async def _load_kuaioa_special_price(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaioa", "轻办公")
    from apps.kuaioa.services.collaboration_service import SpecialPriceRequestService

    return await SpecialPriceRequestService().get_request(tenant_id, entity_id)


async def _load_kuaioa_concession(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaioa", "轻办公")
    from apps.kuaioa.services.collaboration_service import ConcessionRequestService

    return await ConcessionRequestService().get_request(tenant_id, entity_id)


async def _load_kuaioa_process_deviation(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaioa", "轻办公")
    from apps.kuaioa.services.collaboration_service import ProcessDeviationService

    return await ProcessDeviationService().get_request(tenant_id, entity_id)


async def _load_kuaioa_dept_training_application(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaioa", "轻办公")
    from apps.kuaioa.services.training_workflow_service import DeptTrainingApplicationService

    return await DeptTrainingApplicationService().get_request(tenant_id, entity_id)


async def _load_kuaioa_special_work_qualification(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaioa", "轻办公")
    from apps.kuaioa.services.training_workflow_service import SpecialWorkQualificationService

    return await SpecialWorkQualificationService().get_request(tenant_id, entity_id)


async def _load_kuaioa_training_plan(tenant_id: int, entity_id: int) -> Any:
    from apps.common.app_orm import require_app_orm

    require_app_orm("kuaioa", "轻办公")
    from apps.kuaioa.services.training_workflow_service import AnnualTrainingPlanService

    return await AnnualTrainingPlanService().get_plan(tenant_id, entity_id)


DOCUMENT_LOADERS: Dict[str, LoaderFn] = {
    "sales_order": _load_sales_order,
    "sales_order_change": _load_sales_order_change,
    "sales_forecast": _load_sales_forecast,
    "sales_contract": _load_sales_contract,
    "quotation": _load_quotation,
    "shipment_notice": _load_shipment_notice,
    "sales_delivery": _load_sales_delivery,
    "production_picking": _load_production_picking,
    "work_order": _load_work_order,
    "sales_return": _load_sales_return,
    "purchase_return": _load_purchase_return,
    "receipt_notice": _load_receipt_notice,
    "purchase_receipt": _load_purchase_receipt,
    "sales_contract_change": _load_sales_contract_change,
    "demand": _load_demand,
    "purchase_order": _load_purchase_order,
    "purchase_order_change": _load_purchase_order_change,
    "purchase_arrival_delay": _load_purchase_arrival_delay,
    "purchase_request": _load_purchase_request,
    "payment_application": _load_payment_application,
    "purchase_inquiry": _load_purchase_inquiry,
    "reporting_record": _load_reporting_record,
    "incoming_inspection": _load_incoming_inspection,
    "process_inspection": _load_process_inspection,
    "finished_goods_inspection": _load_finished_goods_inspection,
    "oqc_inspection": _load_oqc_inspection,
    "quality_patrol": _load_quality_patrol,
    "outsource_inspection": _load_outsource_inspection,
    "receivable": _load_receivable,
    "payable": _load_payable,
    "receipt": _load_receipt,
    "receipt_refund": _load_receipt_refund,
    "payment": _load_payment,
    "payment_refund": _load_payment_refund,
    "fund_transfer": _load_fund_transfer,
    "sales_invoice": _load_sales_invoice,
    "notes_receivable": _load_notes_receivable,
    "notes_payable": _load_notes_payable,
    "purchase_invoice": _load_purchase_invoice,
    "partner_statement": _load_partner_statement,
    "bom_change": _load_bom_change,
    "process_route_change": _load_process_route_change,
    "drawing_change": _load_drawing_change,
    "product_firmware": _load_product_firmware,
    "lab_request": _load_lab_request,
    "production_file": _load_production_file,
    "engineering_drawing": _load_engineering_drawing,
    "trial_flow": _load_trial_flow,
    "rework_order": _load_rework_order,
    "quality_complaint": _load_quality_complaint,
    "supplier_evaluation": _load_supplier_evaluation,
    "engineering_change": _load_engineering_change,
    "sample_process": _load_sample_process,
    "prototype_build_sheet": _load_prototype_build_sheet,
    "rd_deliverable": _load_rd_deliverable,
    "qms_system_document": _load_qms_system_document,
    "material_review": _load_material_review,
    "bom_collaboration": _load_bom_collaboration,
    "project_proposal": _load_project_proposal,
    "mold_sample": _load_mold_sample,
    "freight_bill": _load_freight_bill,
    "other_income": _load_other_income,
    "other_expense": _load_other_expense,
    "other_expense_application": _load_other_expense_application,
    "kuaioa_form_request": _load_kuaioa_form_request,
    "kuaioa_expense": _load_kuaioa_expense,
    "kuaioa_asset_purchase": _load_kuaioa_asset_purchase,
    "kuaioa_leave": _load_kuaioa_leave,
    "kuaioa_seal": _load_kuaioa_seal,
    "kuaioa_special_price": _load_kuaioa_special_price,
    "kuaioa_concession": _load_kuaioa_concession,
    "kuaioa_process_deviation": _load_kuaioa_process_deviation,
    "kuaioa_dept_training_application": _load_kuaioa_dept_training_application,
    "kuaioa_special_work_qualification": _load_kuaioa_special_work_qualification,
    "kuaioa_training_plan": _load_kuaioa_training_plan,
}


def _assert_loader_coverage() -> None:
    """仅用于测试/启动自检；禁止在 GET 详情热路径抛错，否则缺一个 loader 会拖垮全部单据详情。"""
    from core.services.approval.uni_audit_handlers import HANDLERS

    missing = sorted(set(HANDLERS) - set(DOCUMENT_LOADERS))
    if missing:
        raise ValidationError(f"审批单据详情加载器未覆盖: {', '.join(missing)}")


def _warn_loader_coverage_once() -> None:
    from core.services.approval.uni_audit_handlers import HANDLERS

    missing = sorted(set(HANDLERS) - set(DOCUMENT_LOADERS))
    if missing:
        logger.warning("审批单据详情加载器未覆盖（不影响已有类型）: {}", ", ".join(missing))


_coverage_warned = False


async def build_approval_document_view(
    tenant_id: int,
    instance: Any,
) -> ApprovalDocumentView:
    global _coverage_warned
    if not _coverage_warned:
        _coverage_warned = True
        try:
            _warn_loader_coverage_once()
        except Exception:  # noqa: BLE001 — 自检失败不得阻断详情
            logger.exception("审批单据 loader 覆盖自检失败")

    data = instance.data or {}
    entity_type = str(data.get("entity_type") or "").strip()
    raw_id = data.get("entity_id")
    if not entity_type or raw_id is None or raw_id == "":
        raise ValidationError("审批实例缺少关联单据")
    try:
        entity_id = int(raw_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"审批关联单据 ID 非法: {raw_id}") from exc
    if entity_id <= 0:
        raise ValidationError(f"审批关联单据 ID 非法: {raw_id}")

    loader = DOCUMENT_LOADERS.get(entity_type)
    if loader is None:
        raise ValidationError(f"实体 {entity_type} 尚未提供审批单据详情")

    payload_obj = await loader(tenant_id, entity_id)
    payload = _to_plain(payload_obj)
    business_type = data.get("business_type")
    entity_name = _entity_display_name(entity_type, str(business_type) if business_type else None)
    return compose_document_view(
        entity_type=entity_type,
        entity_name=entity_name,
        payload=payload,
    )


async def attach_document_to_instance_response(
    tenant_id: int,
    instance: Any,
) -> ApprovalInstanceResponse:
    """GET 单条审批实例时附加活单据详情与节点展示名。"""
    if getattr(instance, "process", None) is None:
        await instance.fetch_related("process")
    resp = ApprovalInstanceResponse.model_validate(instance)
    node_label = resolve_current_node_label(instance)
    submitter_name = await resolve_submitter_name(instance)
    document: Optional[ApprovalDocumentView] = None
    document_error: Optional[str] = None
    try:
        document = await build_approval_document_view(tenant_id, instance)
    except (NotFoundError, ValidationError) as exc:
        document_error = str(exc)
        logger.warning(
            "审批关联单据无法加载 uuid={} detail={}",
            getattr(instance, "uuid", None),
            document_error,
        )
    return resp.model_copy(
        update={
            "current_node_label": node_label,
            "submitter_name": submitter_name,
            "document": document,
            "document_error": document_error,
        }
    )
