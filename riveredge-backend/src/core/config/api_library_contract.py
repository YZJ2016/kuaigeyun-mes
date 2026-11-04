"""接口库扩展属性：关联单据、接口类型（标准/自定义）。"""

from __future__ import annotations

from typing import Literal, Optional, Tuple

ApiInterfaceType = Literal["standard", "custom"]

VALID_API_INTERFACE_TYPES = frozenset({"standard", "custom"})

# code → 中文展示名（与 document_push source_type / 业务单据对齐）
API_RELATED_DOCUMENT_SPECS: Tuple[Tuple[str, str], ...] = (
    ("customer", "客户"),
    ("supplier", "供应商"),
    ("warehouse", "仓库"),
    ("sales_order", "销售订单"),
    ("purchase_order", "采购订单"),
    ("purchase_receipt", "采购入库"),
    ("sales_delivery", "销售出库"),
    ("other_outbound", "其他出库"),
    ("other_inbound", "其他入库"),
    ("finished_goods_receipt", "成品入库"),
    ("production_picking", "生产领料"),
    ("stocktaking", "盘点单"),
    ("work_order", "生产工单"),
    ("reporting_record", "报工记录"),
    ("material", "物料"),
    ("material_batch", "即时库存"),
    ("engineering_bom", "工程 BOM"),
    ("process_operation", "工序"),
)

VALID_API_RELATED_DOCUMENT_CODES = frozenset(code for code, _ in API_RELATED_DOCUMENT_SPECS)


def normalize_api_interface_type(value: Optional[str], *, default: ApiInterfaceType = "custom") -> ApiInterfaceType:
    text = str(value or "").strip().lower()
    if text in VALID_API_INTERFACE_TYPES:
        return text  # type: ignore[return-value]
    return default


def normalize_api_related_document_code(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    if text not in VALID_API_RELATED_DOCUMENT_CODES:
        raise ValueError(f"关联单据编码无效: {text}")
    return text


IM_BILL_FORM_TO_RELATED_DOCUMENT: dict[str, str] = {
    "im_saloutbill": "sales_delivery",
    "im_purinbill": "purchase_receipt",
    "im_otheroutbill": "other_outbound",
    "im_otherinbill": "other_inbound",
    "im_surplusbill": "stocktaking",
    "im_deficitbill": "stocktaking",
}


def related_document_for_im_bill_form(form_id: str) -> Optional[str]:
    return IM_BILL_FORM_TO_RELATED_DOCUMENT.get(str(form_id or "").strip().lower())


# 预置 code_suffix → 关联单据（与 list_kingdee_cosmic_api_presets 对齐）
PRESET_CODE_SUFFIX_TO_RELATED_DOCUMENT: dict[str, Optional[str]] = {
    "query_warehouse": "warehouse",
    "query_location": "warehouse",
    "query_warelocareference": "warehouse",
    "query_customer": "customer",
    "getcustomer_bd_customer": "customer",
    "query_supplier": "supplier",
    "query_supplier_list": "supplier",
    "getsupplier_bd_supplier": "supplier",
    "query_material": "material",
    "query_material_inventory_info": "material",
    "getmatinfo_bd_materialinventoryinfo": "material",
    "query_material_group": "material",
    "query_measureunits": "material",
    "query_multimeasureunit": "material",
    "query_inventory_detail": "material_batch",
    "batch_add_im_saloutbill": "sales_delivery",
    "batch_update_im_saloutbill": "sales_delivery",
    "batch_submit_im_saloutbill": "sales_delivery",
    "batch_audit_im_saloutbill": "sales_delivery",
    "batch_unaudit_im_saloutbill": "sales_delivery",
    "batch_unsubmit_im_saloutbill": "sales_delivery",
    "batch_delete_im_saloutbill": "sales_delivery",
    "batch_add_im_purinbill": "purchase_receipt",
    "batch_update_im_purinbill": "purchase_receipt",
    "batch_unaudit_im_purinbill": "purchase_receipt",
    "batch_unsubmit_im_purinbill": "purchase_receipt",
    "batch_delete_im_purinbill": "purchase_receipt",
    "add_im_purinbill": "purchase_receipt",
    "add2_im_purinbill": "purchase_receipt",
    "batch_add_im_otheroutbill": "other_outbound",
    "batch_update_im_otheroutbill": "other_outbound",
    "add3_im_otheroutbill": "other_outbound",
    "batch_submit_im_otheroutbill": "other_outbound",
    "billbatch_audit_im_otheroutbill": "other_outbound",
    "batch_unaudit_im_otheroutbill": "other_outbound",
    "batch_unsubmit_im_otheroutbill": "other_outbound",
    "batch_delete_im_otheroutbill": "other_outbound",
    "batch_add_im_otheroutbill_production_picking": "production_picking",
    "batch_update_im_otheroutbill_production_picking": "production_picking",
    "add3_im_otheroutbill_production_picking": "production_picking",
    "batch_unaudit_im_otheroutbill_production_picking": "production_picking",
    "batch_unsubmit_im_otheroutbill_production_picking": "production_picking",
    "batch_delete_im_otheroutbill_production_picking": "production_picking",
    "batch_add_im_otherinbill": "other_inbound",
    "batch_update_im_otherinbill": "other_inbound",
    "batch_submit_im_otherinbill": "other_inbound",
    "billbatch_audit_im_otherinbill": "other_inbound",
    "batch_unaudit_im_otherinbill": "other_inbound",
    "batch_unsubmit_im_otherinbill": "other_inbound",
    "batch_delete_im_otherinbill": "other_inbound",
    "batch_add_im_otherinbill_finished_goods_receipt": "finished_goods_receipt",
    "batch_update_im_otherinbill_finished_goods_receipt": "finished_goods_receipt",
    "batch_unaudit_im_otherinbill_finished_goods_receipt": "finished_goods_receipt",
    "batch_unsubmit_im_otherinbill_finished_goods_receipt": "finished_goods_receipt",
    "batch_delete_im_otherinbill_finished_goods_receipt": "finished_goods_receipt",
    "oauth_get_token": None,
}


def infer_related_document_from_kingdee_api_path(path: str) -> Optional[str]:
    """从苍穹 OpenAPI 路径推断关联 MES 单据（预置加载/回填用）。"""
    hay = str(path or "").lower().replace("_", "")
    if "imsaloutbill" in hay:
        return "sales_delivery"
    if "impurinbill" in hay:
        return "purchase_receipt"
    if "imotheroutbill" in hay:
        return "other_outbound"
    if "imotherinbill" in hay:
        return "other_inbound"
    if "imsurplusbill" in hay:
        return "stocktaking"
    if "imdeficitbill" in hay:
        return "stocktaking"
    if "improdoutbill" in hay or "immaterialreqoutbill" in hay:
        return "production_picking"
    if "immdcproduceinbill" in hay or "improduceinbill" in hay:
        return "finished_goods_receipt"
    if "pmpurorderbill" in hay or "purorderbill" in hay:
        return "purchase_order"
    if "smsalorderbill" in hay or "smsalorder" in hay:
        return "sales_order"
    if "pmprdmo" in hay or "prdmo" in hay:
        return "work_order"
    if "getinventoryavbqty" in hay or "getinventorydetail" in hay:
        return "material_batch"
    if "bdwarehouse" in hay or "warelocareference" in hay:
        return "warehouse"
    if "bdcustomer" in hay:
        return "customer"
    if "bdsupplier" in hay:
        return "supplier"
    if "bdmaterial" in hay or "materialgroup" in hay or "measureunits" in hay:
        return "material"
    return None


def infer_related_document_from_preset_code_suffix(code_suffix: str) -> Optional[str]:
    key = str(code_suffix or "").strip()
    if not key:
        return None
    if key in PRESET_CODE_SUFFIX_TO_RELATED_DOCUMENT:
        return PRESET_CODE_SUFFIX_TO_RELATED_DOCUMENT[key]
    return None


def infer_related_document_from_kingdee_api(
    *,
    path: str = "",
    code: str = "",
    name: str = "",
    preset_code_suffix: str = "",
) -> Optional[str]:
    from_suffix = infer_related_document_from_preset_code_suffix(preset_code_suffix)
    if from_suffix:
        return from_suffix
    from_path = infer_related_document_from_kingdee_api_path(path)
    if from_path:
        return from_path
    hay = f"{code} {name}".lower().replace("_", "")
    if "querypurchaseorder" in hay or "purorder" in hay:
        return "purchase_order"
    if "querycustomer" in hay or "getcustomer" in hay:
        return "customer"
    if "querysupplier" in hay or "getsupplier" in hay:
        return "supplier"
    if "querywarehouse" in hay or "querylocation" in hay or "wareloca" in hay:
        return "warehouse"
    if "querymaterialgroup" in hay or "querymaterial" in hay:
        return "material"
    if "measureunits" in hay or "multimeasureunit" in hay:
        return "material"
    if "inventorybalance" in hay or "inventorydetail" in hay:
        return "material_batch"
    if "saloutbill" in hay:
        return "sales_delivery"
    if "purinbill" in hay:
        return "purchase_receipt"
    return None


def is_kingdee_standard_library_api(
    *,
    path: str = "",
    code: str = "",
    name: str = "",
) -> bool:
    """苍穹接口库预置或 OpenAPI 路径，标为标准 API。"""
    path_l = str(path or "").lower()
    code_l = str(code or "").lower()
    name_l = str(name or "").lower()
    if path_l.startswith("kapi/v2") or "/oauth2/gettoken" in path_l or "gettoken" in path_l:
        return True
    if code_l.startswith("kingdee_") or "_kingdee_" in code_l:
        return True
    if "苍穹" in str(name or ""):
        return True
    if "kingdee" in name_l and ("query" in name_l or "batch" in name_l or "oauth" in name_l):
        return True
    return False
