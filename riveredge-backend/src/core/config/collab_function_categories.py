"""
协同配置（审批流程 / 消息模板 / 打印模板）功能域分类真源。

分类 code 与 manifest.audit.config_category、配置中心审核侧栏一致。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional, Sequence

from core.config.audit_registry import VALID_CONFIG_CATEGORIES, entry_by_node_key

# 与 riveredge-frontend configTree AUDIT_CATEGORIES + BASE_MODULES 对齐
FUNCTION_CATEGORY_PRESETS: Sequence[tuple[str, str, int, str]] = (
    ("common", "通用配置", 0, "跨模块审批与平台通知"),
    ("office", "办公管理", 10, "请假、用章、培训等办公协同"),
    ("plm", "研发管理", 20, "工程变更、实验与文控"),
    ("sales", "销售管理", 30, "销售订单、发货与退货"),
    ("planning", "计划管理", 40, "需求、MRP 与排产"),
    ("procurement", "采购管理", 50, "请购、采购订单与到货"),
    ("production", "生产执行", 60, "工单、报工与委外"),
    ("quality", "质量管理", 70, "检验、异常与客户投诉"),
    ("equipment", "设备管理", 80, "设备、模具、点检与 IoT"),
    ("warehouse", "仓储管理", 90, "出入库、盘点与库存"),
    ("finance", "财务管理", 100, "应收应付与收付款"),
)


@dataclass(frozen=True)
class FunctionCategoryDef:
    code: str
    name: str
    sort_order: int
    description: str


def all_function_category_defs() -> list[FunctionCategoryDef]:
    out: list[FunctionCategoryDef] = []
    for code, name, sort_order, description in FUNCTION_CATEGORY_PRESETS:
        if code not in VALID_CONFIG_CATEGORIES:
            continue
        out.append(
            FunctionCategoryDef(
                code=code,
                name=name,
                sort_order=sort_order,
                description=description,
            )
        )
    return out


def normalize_function_category_code(raw: Optional[str]) -> str:
    code = str(raw or "").strip() or "common"
    if code not in VALID_CONFIG_CATEGORIES:
        return "common"
    return code


def resolve_function_category_for_approval_process(code: Optional[str]) -> str:
    normalized = str(code or "").strip()
    if not normalized or normalized == "personal_task":
        return "common"
    entry = entry_by_node_key(normalized)
    if entry is not None:
        return normalize_function_category_code(entry.config_category)
    return "common"


_MESSAGE_CODE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^approval_", re.I), "common"),
    (re.compile(r"^PLM_", re.I), "plm"),
    (re.compile(r"^(KUAIOA_|OA_)", re.I), "office"),
    (re.compile(r"^KZ_SALES_|^KZ_SO_|^KZ_SHIP_", re.I), "sales"),
    (re.compile(r"^KZ_PO_|^KZ_POC_|^KZ_SUPPLIER_", re.I), "procurement"),
    (re.compile(r"^KZ_WO_", re.I), "production"),
    (re.compile(r"^KZ_QUALITY_|^KZ_QE_", re.I), "quality"),
    (re.compile(r"^KZ_EQUIPMENT_|^KZ_EQ_|^KZ_MOLD_|^KZ_SPOT_|^KZ_LINE_", re.I), "equipment"),
    (re.compile(r"^KZ_INVENTORY_|^KZ_INV_", re.I), "warehouse"),
    (re.compile(r"^(IOT_|VISION_)", re.I), "equipment"),
    (re.compile(r"^HAOLIGO_", re.I), "equipment"),
    (re.compile(r"^KUAICAIWU_", re.I), "finance"),
    (re.compile(r"^MASTER_DATA_", re.I), "common"),
)


def resolve_function_category_for_message_template(code: Optional[str]) -> str:
    normalized = str(code or "").strip()
    if not normalized:
        return "common"
    for pattern, category in _MESSAGE_CODE_RULES:
        if pattern.search(normalized):
            return category
    return "common"


_KUAIZHIZAO_PRINT_DOC_CATEGORY: Dict[str, str] = {
    "demand": "planning",
    "demand_computation": "planning",
    "sales_forecast": "planning",
    "sales_order": "sales",
    "quotation": "sales",
    "sales_contract": "sales",
    "sales_delivery": "sales",
    "shipment_notice": "sales",
    "delivery_notice": "sales",
    "sales_return": "sales",
    "purchase_order": "procurement",
    "purchase_requisition": "procurement",
    "purchase_receipt": "procurement",
    "purchase_return": "procurement",
    "receipt_notice": "procurement",
    "work_order": "production",
    "rework_order": "production",
    "outsource_order": "production",
    "outsource_work_order": "production",
    "reporting_record": "production",
    "reporting_timeline": "production",
    "production_picking": "warehouse",
    "production_return": "warehouse",
    "finished_goods_receipt": "warehouse",
    "semi_finished_goods_receipt": "warehouse",
    "other_outbound": "warehouse",
    "other_inbound": "warehouse",
    "material_return": "warehouse",
    "material_borrow": "warehouse",
    "packing_binding": "warehouse",
    "incoming_inspection": "quality",
    "process_inspection": "quality",
    "finished_goods_inspection": "quality",
    "product_quality_certificate": "quality",
    "equipment": "equipment",
    "equipment_fault": "equipment",
    "maintenance_plan": "equipment",
    "maintenance_reminder": "equipment",
    "mold": "equipment",
    "tool": "equipment",
}


def _build_print_document_type_category_map() -> Dict[str, str]:
    from core.services.system.installed_feature_scope import (
        _PRINT_DOC_GLOBAL,
        _PRINT_DOC_HAOLIGO,
        _PRINT_DOC_KUAICAIWU,
        _PRINT_DOC_KUAIZHIZAO,
        _PRINT_DOC_MASTER_DATA,
    )

    mapping: Dict[str, str] = {}
    for dt in _PRINT_DOC_GLOBAL:
        mapping[dt] = "common"
    for dt in _PRINT_DOC_MASTER_DATA:
        mapping[dt] = "common"
    for dt in _PRINT_DOC_KUAICAIWU:
        mapping[dt] = "finance"
    for dt in _PRINT_DOC_HAOLIGO:
        mapping[dt] = "equipment"
    for dt in _PRINT_DOC_KUAIZHIZAO:
        mapping[dt] = _KUAIZHIZAO_PRINT_DOC_CATEGORY.get(dt, "common")
    return mapping


_PRINT_DOC_CATEGORY_CACHE: Optional[Dict[str, str]] = None


def print_document_type_function_category_map() -> Dict[str, str]:
    global _PRINT_DOC_CATEGORY_CACHE
    if _PRINT_DOC_CATEGORY_CACHE is None:
        _PRINT_DOC_CATEGORY_CACHE = _build_print_document_type_category_map()
    return _PRINT_DOC_CATEGORY_CACHE


def resolve_function_category_for_print_template(
    *,
    document_type: Optional[str],
    code: Optional[str] = None,
) -> str:
    dt = str(document_type or "").strip()
    if dt:
        return normalize_function_category_code(
            print_document_type_function_category_map().get(dt, "common")
        )
    code_upper = str(code or "").strip().upper()
    if code_upper.startswith("HAOLIGO_"):
        return "equipment"
    if code_upper.startswith("KUAICAIWU_"):
        return "finance"
    return "common"
