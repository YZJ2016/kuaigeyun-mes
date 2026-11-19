"""
金蝶AI苍穹 OpenAPI（kingdee_cosmic）入站常用接口预设。

与金蝶AI星空 WebAPI（ExecuteBillQuery / .kdsvc）不同，标准业务对象查询为：
POST {门户}/kapi/sys/{业务对象标识}/query
（连接器 Base 已含 /ierp 时不要再在路径前加 ierp，否则会变成 /ierp/ierp/kapi 并被容器 404。）
查询参数：select（必填且不可为 *）、filter、orderby、page_no、page_size（可放在 URL 或请求体）。

依据：金蝶开放平台「操作 API / 业务对象 query」说明及标品基础资料、采购订单对象标识。
租户须先在「开放服务云 → OpenAPI」初始化并对第三方应用授权；若 select/filter 与现场字段不一致，请在接口管理中按本环境微调。
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, TypedDict

# 增强型 Token（固定路径，用于联调对照；日常同步由连接器自动带 token）
OAUTH_GET_TOKEN_PATH = "kapi/oauth2/getToken"

# 标品业务对象标识（与 OpenAPI 初始化后的 sys 路径一致）
BIZ_BD_MATERIAL = "bd_material"
BIZ_BD_MATERIALGROUP = "bd_materialgroup"
# 多数租户 OpenAPI 未发布独立 bd_measureunits（调测 404）；单位同步用多计量单位
BIZ_BD_MEASUREUNITS = "bd_measureunits"
BIZ_BD_MULTIMEASUREUNIT = "bd_multimeasureunit"
BIZ_BD_SUPPLIER = "bd_supplier"
BIZ_BD_CUSTOMER = "bd_customer"
BIZ_BD_WAREHOUSE = "bd_warehouse"
BIZ_BD_LOCATION = "bd_location"
# 仓库仓位关系（开放平台「仓库仓位关系详情查询」）
BIZ_BD_WARELOCAREFERENCE = "bd_warelocareference"
BIZ_PM_PURORDERBILL = "pm_purorderbill"
# 库存管理：采购入库单新增（出站）
BIZ_IM_PURINBILL = "im_purinbill"
IM_PURINBILL_ADD_PATH = f"kapi/v2/im/{BIZ_IM_PURINBILL}/add"
IM_PURINBILL_ADD_PRESET_CODE_SUFFIX = "add_im_purinbill"
# 客户扩展：含验收人文本字段 fd81_yanshou（开放平台标品 add 无此字段）
IM_PURINBILL_ADD2_PATH = f"kapi/v2/fd81/im/{BIZ_IM_PURINBILL}/add2"
IM_PURINBILL_ADD2_PRESET_CODE_SUFFIX = "add2_im_purinbill"
IM_PURINBILL_ACCEPTOR_FIELD = "fd81_yanshou"
IM_PURINBILL_BATCH_UPDATE_PATH = f"kapi/v2/im/{BIZ_IM_PURINBILL}/batchUpdate"
IM_PURINBILL_BATCH_UPDATE_PRESET_CODE_SUFFIX = "batch_update_im_purinbill"
IM_PURINBILL_BATCH_UNAUDIT_PATH = f"kapi/v2/im/{BIZ_IM_PURINBILL}/batchUnaudit"
IM_PURINBILL_BATCH_UNSUBMIT_PATH = f"kapi/v2/im/{BIZ_IM_PURINBILL}/batchUnsubmit"
IM_PURINBILL_BATCH_DELETE_PATH = f"kapi/v2/im/{BIZ_IM_PURINBILL}/batchDelete"
# 库存管理：销售出库单批量新增（出站）
BIZ_IM_SALOUTBILL = "im_saloutbill"
IM_SALOUTBILL_BATCH_ADD_PATH = f"kapi/v2/im/{BIZ_IM_SALOUTBILL}/batchAdd"
IM_SALOUTBILL_BATCH_UPDATE_PATH = f"kapi/v2/im/{BIZ_IM_SALOUTBILL}/batchUpdate"
IM_SALOUTBILL_BATCH_UPDATE_PRESET_CODE_SUFFIX = "batch_update_im_saloutbill"
IM_SALOUTBILL_BATCH_SUBMIT_PATH = f"kapi/v2/im/{BIZ_IM_SALOUTBILL}/batchSubmit"
IM_SALOUTBILL_BATCH_AUDIT_PATH = f"kapi/v2/im/{BIZ_IM_SALOUTBILL}/batchAudit"
IM_SALOUTBILL_BATCH_UNAUDIT_PATH = f"kapi/v2/im/{BIZ_IM_SALOUTBILL}/batchUnaudit"
IM_SALOUTBILL_BATCH_UNSUBMIT_PATH = f"kapi/v2/im/{BIZ_IM_SALOUTBILL}/batchUnsubmit"
IM_SALOUTBILL_BATCH_DELETE_PATH = f"kapi/v2/im/{BIZ_IM_SALOUTBILL}/batchDelete"
IM_SALOUTBILL_BATCH_ADD_PRESET_CODE_SUFFIX = "batch_add_im_saloutbill"
# 库存管理：其他出库单批量新增（出站）
BIZ_IM_OTHEROUTBILL = "im_otheroutbill"
IM_OTHEROUTBILL_BATCH_ADD_PATH = f"kapi/v2/im/{BIZ_IM_OTHEROUTBILL}/batchAdd"
IM_OTHEROUTBILL_BATCH_UPDATE_PATH = f"kapi/v2/im/{BIZ_IM_OTHEROUTBILL}/batchUpdate"
IM_OTHEROUTBILL_BATCH_UPDATE_PRESET_CODE_SUFFIX = "batch_update_im_otheroutbill"
IM_OTHEROUTBILL_BATCH_SUBMIT_PATH = f"kapi/v2/im/{BIZ_IM_OTHEROUTBILL}/batchSubmit"
IM_OTHEROUTBILL_BATCH_AUDIT_PATH = f"kapi/v2/im/{BIZ_IM_OTHEROUTBILL}/billbatchAudit"
IM_OTHEROUTBILL_BATCH_UNAUDIT_PATH = f"kapi/v2/im/{BIZ_IM_OTHEROUTBILL}/batchUnaudit"
IM_OTHEROUTBILL_BATCH_UNSUBMIT_PATH = f"kapi/v2/im/{BIZ_IM_OTHEROUTBILL}/batchUnsubmit"
IM_OTHEROUTBILL_BATCH_DELETE_PATH = f"kapi/v2/im/{BIZ_IM_OTHEROUTBILL}/batchDelete"
IM_OTHEROUTBILL_BATCH_ADD_PRESET_CODE_SUFFIX = "batch_add_im_otheroutbill"
IM_OTHEROUTBILL_PRODUCTION_PICKING_BATCH_UPDATE_PRESET_CODE_SUFFIX = (
    "batch_update_im_otheroutbill_production_picking"
)
# 生产领料：同路径 im_otheroutbill/batchAdd，关联单据 production_picking；单据类型须为本环境「生产领料」
IM_OTHEROUTBILL_PRODUCTION_PICKING_BATCH_ADD_PRESET_CODE_SUFFIX = (
    "batch_add_im_otheroutbill_production_picking"
)
# 【自定义】其他出库/生产领料：含领用人 bizuser_*（连枝横 add3；标品 batchAdd 无此写参）
IM_OTHEROUTBILL_ADD3_PATH = f"kapi/v2/fd81/im/{BIZ_IM_OTHEROUTBILL}/add3"
IM_OTHEROUTBILL_ADD3_PRESET_CODE_SUFFIX = "add3_im_otheroutbill"
IM_OTHEROUTBILL_PRODUCTION_PICKING_ADD3_PRESET_CODE_SUFFIX = (
    "add3_im_otheroutbill_production_picking"
)


def is_im_otheroutbill_add3_path(path: Any) -> bool:
    """自定义 add3 保存：单对象 data + bizuser_number 领用人。"""
    hay = str(path or "").lower().replace("\\", "/")
    compact = hay.replace("_", "")
    return "imotheroutbill" in compact and (hay.rstrip("/").endswith("/add3") or "/add3" in hay)
# 库存管理：其他入库单批量新增（出站）
BIZ_IM_OTHERINBILL = "im_otherinbill"
IM_OTHERINBILL_BATCH_ADD_PATH = f"kapi/v2/im/{BIZ_IM_OTHERINBILL}/batchAdd"
IM_OTHERINBILL_BATCH_UPDATE_PATH = f"kapi/v2/im/{BIZ_IM_OTHERINBILL}/batchUpdate"
IM_OTHERINBILL_BATCH_UPDATE_PRESET_CODE_SUFFIX = "batch_update_im_otherinbill"
IM_OTHERINBILL_BATCH_SUBMIT_PATH = f"kapi/v2/im/{BIZ_IM_OTHERINBILL}/batchSubmit"
# 开放平台 API 编码 billbatchAudit（非 im_saloutbill 等使用的 batchAudit）
IM_OTHERINBILL_BATCH_AUDIT_PATH = f"kapi/v2/im/{BIZ_IM_OTHERINBILL}/billbatchAudit"
IM_OTHERINBILL_BATCH_UNAUDIT_PATH = f"kapi/v2/im/{BIZ_IM_OTHERINBILL}/batchUnaudit"
IM_OTHERINBILL_BATCH_UNSUBMIT_PATH = f"kapi/v2/im/{BIZ_IM_OTHERINBILL}/batchUnsubmit"
IM_OTHERINBILL_BATCH_DELETE_PATH = f"kapi/v2/im/{BIZ_IM_OTHERINBILL}/batchDelete"
IM_OTHERINBILL_BATCH_ADD_PRESET_CODE_SUFFIX = "batch_add_im_otherinbill"
# 成品入库：同路径 im_otherinbill/batchAdd，关联单据 finished_goods_receipt；单据类型须为本环境「生产完工入库」
IM_OTHERINBILL_FINISHED_GOODS_BATCH_ADD_PRESET_CODE_SUFFIX = (
    "batch_add_im_otherinbill_finished_goods_receipt"
)
IM_OTHERINBILL_FINISHED_GOODS_BATCH_UPDATE_PRESET_CODE_SUFFIX = (
    "batch_update_im_otherinbill_finished_goods_receipt"
)
# 库存管理：盘盈单批量新增（出站）
BIZ_IM_SURPLUSBILL = "im_surplusbill"
IM_SURPLUSBILL_BATCH_ADD_PATH = f"kapi/v2/im/{BIZ_IM_SURPLUSBILL}/batchAdd"
IM_SURPLUSBILL_BATCH_SUBMIT_PATH = f"kapi/v2/im/{BIZ_IM_SURPLUSBILL}/batchSubmit"
IM_SURPLUSBILL_BATCH_AUDIT_PATH = f"kapi/v2/im/{BIZ_IM_SURPLUSBILL}/batchAudit"
IM_SURPLUSBILL_BATCH_ADD_PRESET_CODE_SUFFIX = "batch_add_im_surplusbill"
# 库存管理：盘亏单批量新增（出站）
BIZ_IM_DEFICITBILL = "im_deficitbill"
IM_DEFICITBILL_BATCH_ADD_PATH = f"kapi/v2/im/{BIZ_IM_DEFICITBILL}/batchAdd"
IM_DEFICITBILL_BATCH_SUBMIT_PATH = f"kapi/v2/im/{BIZ_IM_DEFICITBILL}/batchSubmit"
IM_DEFICITBILL_BATCH_AUDIT_PATH = f"kapi/v2/im/{BIZ_IM_DEFICITBILL}/batchAudit"
IM_DEFICITBILL_BATCH_ADD_PRESET_CODE_SUFFIX = "batch_add_im_deficitbill"
# 库存管理：库存余额 / 即时库存查询（入站）
# 库存余额真源：开放平台 API 编码 getInventoryAvbQty（库存查询接口API）
IM_GET_INVENTORY_AVB_QTY_PATH = "kapi/v2/im/getInventoryAvbQty"
IM_GET_INVENTORY_AVB_QTY_PRESET_CODE_SUFFIX = "query_inventory_balance"
IM_GET_INVENTORY_DETAIL_PATH = "kapi/v2/im/getInventoryDetail"
IM_GET_INVENTORY_DETAIL_PRESET_CODE_SUFFIX = "query_inventory_detail"
# 兼容旧常量名（曾误用 getInventorySum 作余额）
IM_GET_INVENTORY_SUM_PATH = IM_GET_INVENTORY_AVB_QTY_PATH
IM_GET_INVENTORY_SUM_PRESET_CODE_SUFFIX = IM_GET_INVENTORY_AVB_QTY_PRESET_CODE_SUFFIX
INVENTORY_BALANCE_PRESET_CODE_SUFFIX = IM_GET_INVENTORY_AVB_QTY_PRESET_CODE_SUFFIX
INVENTORY_DETAIL_PRESET_CODE_SUFFIX = IM_GET_INVENTORY_DETAIL_PRESET_CODE_SUFFIX
# 仓库 / 仓位列表：开放平台已发布 sbd/getList。basedata query/batchQuery 实调常 404。
WAREHOUSE_GET_LIST_PATH = f"kapi/v2/sbd/{BIZ_BD_WAREHOUSE}/getList"
LOCATION_GET_LIST_PATH = f"kapi/v2/sbd/{BIZ_BD_LOCATION}/getList"
# 仓库仓位关系：开放平台 API 编码 query（非 getList）
WARELOCAREFERENCE_QUERY_PATH = f"kapi/v2/sbd/{BIZ_BD_WARELOCAREFERENCE}/query"

# 入站同步常用过滤：已审核且启用（字段名因版本可能略有差异，可按现场调整）
MASTER_DATA_INBOUND_FILTER = "status EQ 'C' AND enable EQ 1"
PURORDER_INBOUND_FILTER = "billstatus EQ 'C'"


class KingdeeCosmicApiPreset(TypedDict, total=False):
    code_suffix: str
    name: str
    description: str
    path: str
    method: str
    request_body: Dict[str, Any]
    request_params: Dict[str, Any]


WAREHOUSE_PRESET_CODE_SUFFIX = "query_warehouse"
SUPPLIER_PRESET_CODE_SUFFIX = "query_supplier"
# 单据写入类：接口管理须标「出站同步」
KINGDEE_COSMIC_OUTBOUND_PRESET_CODE_SUFFIXES = frozenset(
    {
        IM_PURINBILL_ADD_PRESET_CODE_SUFFIX,
        IM_PURINBILL_ADD2_PRESET_CODE_SUFFIX,
        IM_PURINBILL_BATCH_UPDATE_PRESET_CODE_SUFFIX,
        IM_SALOUTBILL_BATCH_ADD_PRESET_CODE_SUFFIX,
        IM_SALOUTBILL_BATCH_UPDATE_PRESET_CODE_SUFFIX,
        IM_OTHEROUTBILL_BATCH_ADD_PRESET_CODE_SUFFIX,
        IM_OTHEROUTBILL_BATCH_UPDATE_PRESET_CODE_SUFFIX,
        IM_OTHEROUTBILL_PRODUCTION_PICKING_BATCH_UPDATE_PRESET_CODE_SUFFIX,
        IM_OTHEROUTBILL_ADD3_PRESET_CODE_SUFFIX,
        IM_OTHEROUTBILL_PRODUCTION_PICKING_ADD3_PRESET_CODE_SUFFIX,
        IM_OTHERINBILL_BATCH_ADD_PRESET_CODE_SUFFIX,
        IM_OTHERINBILL_BATCH_UPDATE_PRESET_CODE_SUFFIX,
        IM_OTHERINBILL_FINISHED_GOODS_BATCH_ADD_PRESET_CODE_SUFFIX,
        IM_OTHERINBILL_FINISHED_GOODS_BATCH_UPDATE_PRESET_CODE_SUFFIX,
        IM_SURPLUSBILL_BATCH_ADD_PRESET_CODE_SUFFIX,
        IM_DEFICITBILL_BATCH_ADD_PRESET_CODE_SUFFIX,
    }
)
# 历史双预置遗留 code，加载常用接口时会合并为与物料一致的 batchQuery
LEGACY_SUPPLIER_LIST_PRESET_CODE_SUFFIX = "query_supplier_list"
MEASUREUNITS_PRESET_CODE_SUFFIX = "query_measureunits"
MATERIAL_PRESET_CODE_SUFFIX = "query_material"
MATERIAL_GROUP_PRESET_CODE_SUFFIX = "query_material_group"
# 单位同步只取物料编码/名称与基础单位，避免batchQuery默认吐全量列
UNIT_SYNC_MATERIAL_SELECT = "number,name,baseunit.number,baseunit.name"
# 物料同步：编码/名称/规格/基础单位/分组（字段以本环境模型为准，可微调）
MATERIAL_SYNC_SELECT = (
    "number,name,modelnum,baseunit.number,baseunit.name,group.number,group.name"
)
GOODS_CLASS_QUERY_PATH = "kapi/v2/gmc/mdr_goodsclass/getMalGoodsClass"


def build_warehouse_get_list_preset_body() -> Dict[str, Any]:
    """
    仓库列表 getList：组织编码由连接器 org_number 在出站时写入，预设不硬编码。
    """
    return {
        "data": {},
        "pageNo": 1,
        "pageSize": 1000,
    }


build_warehouse_batch_query_preset_body = build_warehouse_get_list_preset_body


def build_warehouse_get_list_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": WAREHOUSE_PRESET_CODE_SUFFIX,
        "name": "苍穹查询仓库",
        "description": (
            "供应链基础资料「仓库列表查询」，API 编码 getList，"
            f"请求地址 /v2/sbd/{BIZ_BD_WAREHOUSE}/getList。"
            "请求体 data、pageNo、pageSize；"
            "data.createorg_number 出站时取连接器组织编码，勿在预设里写死。"
            "网关未注册 /v2/basedata/bd_warehouse/query 与 batchQuery，实调返回 2530 路由未找到。"
            "若返回 612，是连接器代理用户缺少应用 sbd、业务对象 bd_warehouse 的查询功能权限。"
        ),
        "path": WAREHOUSE_GET_LIST_PATH,
        "method": "POST",
        "request_body": build_warehouse_get_list_preset_body(),
    }


def build_inventory_balance_query_preset_body(
    *,
    org_number: str = "BU-00000",
    page_no: int = 1,
    page_size: int = 200,
) -> Dict[str, Any]:
    """
    库存余额 getInventoryAvbQty：请求体为顶层 params + pageNo/pageSize（勿包 data）。
    params.org 为库存组织编码（必填）；还可传 material/warehouse/location/lotnum（多选逗号分隔）。
    """
    return {
        "params": {"org": str(org_number or "BU-00000").strip() or "BU-00000"},
        "pageNo": int(page_no or 1),
        "pageSize": int(page_size or 200),
    }


def build_inventory_balance_query_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": INVENTORY_BALANCE_PRESET_CODE_SUFFIX,
        "name": "苍穹查询库存余额",
        "description": (
            "库存管理「库存查询接口API」（API 编码 getInventoryAvbQty）。"
            f"请求地址 /{IM_GET_INVENTORY_AVB_QTY_PATH}。"
            "请求体为顶层 params、pageNo、pageSize（勿包进 data）；"
            "params.org 为库存组织编码（必填，默认示例 BU-00000，请按本环境修改）；"
            "可选 material / warehouse / location / lotnum（多选逗号分隔）。"
            "返回行含可用量等字段，供即时库存入站同步映射（数量优先 avbqty）。"
            "开放平台说明亦可改用即时库存明细 getInventoryDetail（本包另有预设）。"
        ),
        "path": IM_GET_INVENTORY_AVB_QTY_PATH,
        "method": "POST",
        "request_body": build_inventory_balance_query_preset_body(),
    }


def build_inventory_detail_query_preset_body(
    *,
    org_number: str = "BU-00000",
    page_no: int = 1,
    page_size: int = 200,
) -> Dict[str, Any]:
    """即时库存明细 getInventoryDetail：体形与汇总相同，行上常含批号 lotnum。"""
    return build_inventory_balance_query_preset_body(
        org_number=org_number,
        page_no=page_no,
        page_size=page_size,
    )


def build_inventory_detail_query_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": INVENTORY_DETAIL_PRESET_CODE_SUFFIX,
        "name": "苍穹查询即时库存明细",
        "description": (
            "库存管理「即时库存明细查询」（API 编码 getInventoryDetail）。"
            f"请求地址 /{IM_GET_INVENTORY_DETAIL_PATH}。"
            "请求体同库存余额：顶层 params.org（库存组织编码）+ pageNo/pageSize；"
            "明细行通常含 lotnum 批号，适合按批次同步即时库存。"
        ),
        "path": IM_GET_INVENTORY_DETAIL_PATH,
        "method": "POST",
        "request_body": build_inventory_detail_query_preset_body(),
    }


def build_supplier_query_preset_body(
    *,
    createorg_numbers: Optional[List[str]] = None,
    status_codes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    开放平台「查询供应商信息」POST：默认与物料 batchQuery 一样仅分页（data 空对象）；
    需按组织/状态筛时在 data 内传 createorg_number、status 等字符串数组。
    """
    body: Dict[str, Any] = {
        "data": {},
        "pageNo": 1,
        "pageSize": 500,
    }
    data: Dict[str, Any] = {}
    if createorg_numbers:
        orgs = [str(x).strip() for x in createorg_numbers if str(x).strip()]
        if orgs:
            data["createorg_number"] = orgs
    if status_codes:
        codes = [str(x).strip() for x in status_codes if str(x).strip()]
        if codes:
            data["status"] = codes
    if data:
        body["data"] = data
    return body


def _supplier_query_body_shape_valid(request_body: Any, request_params: Any = None) -> bool:
    if not isinstance(request_body, dict):
        return False
    if request_body.get("select") or (request_params or {}).get("select"):
        return False
    if request_body.get("pageNo") in (None, "") or request_body.get("pageSize") in (None, ""):
        return False
    data = request_body.get("data")
    if not isinstance(data, dict):
        return False
    co = data.get("createorg_number")
    if co is not None and not (
        isinstance(co, list) and all(isinstance(x, str) for x in co)
    ):
        return False
    st = data.get("status")
    if st is not None and not (isinstance(st, list) and all(isinstance(x, str) for x in st)):
        return False
    return True


def _is_supplier_wang_placeholder_body(request_body: Any) -> bool:
    """联调占位 createorg WANG + status C 易在本环境筛成 0 条，加载/测试时升级为默认空 data。"""
    if not isinstance(request_body, dict):
        return False
    data = request_body.get("data")
    if not isinstance(data, dict):
        return False
    return data.get("createorg_number") == ["WANG"] and data.get("status") == ["C"]


def supplier_preset_needs_upgrade(
    path: Any,
    method: Any = None,
    request_body: Any = None,
    request_params: Any = None,
) -> bool:
    """POST …/bd_supplier/query；合法空 data 分页不升级，占位 WANG 模板须清掉。"""
    if str(method or "").upper() not in ("", "POST"):
        return True
    lower = str(path or "").lower().replace("\\", "/")
    if not lower or lower.endswith("/basedata/b") or lower.endswith("/basedata/bd"):
        return True
    if f"/{BIZ_BD_SUPPLIER}/batchquery" in lower:
        return True
    if not lower.endswith("/bd_supplier/query") and not lower.endswith("/bd_supplier/query/"):
        return True
    if not _supplier_query_body_shape_valid(request_body, request_params):
        return True
    if _is_supplier_wang_placeholder_body(request_body):
        return True
    return False


def kingdee_supplier_api_upgrade_fields() -> Dict[str, Any]:
    """供接口库升级写入，与 build_supplier_query_preset 一致。"""
    preset = build_supplier_query_preset()
    return {
        "path": preset["path"],
        "method": preset["method"],
        "name": preset["name"],
        "description": preset["description"],
        "request_params": preset.get("request_params"),
        "request_body": preset.get("request_body") or {},
    }


def inventory_balance_preset_needs_upgrade(
    path: Any,
    request_body: Any = None,
    method: Any = None,
) -> bool:
    """须为 POST …/im/getInventoryAvbQty，且 body 为顶层 params + 分页（勿包 data）。"""
    if str(method or "").upper() not in ("", "POST"):
        return True
    lower = str(path or "").lower().replace("\\", "/")
    if "getinventoryavbqty" not in lower:
        return True
    if not isinstance(request_body, dict):
        return True
    if request_body.get("pageNo") in (None, "") or request_body.get("pageSize") in (None, ""):
        return True
    params = request_body.get("params")
    if not isinstance(params, dict):
        return True
    if request_body.get("data") not in (None, {}, []):
        return True
    return False


def kingdee_inventory_balance_api_upgrade_fields() -> Dict[str, Any]:
    preset = build_inventory_balance_query_preset()
    return {
        "path": preset["path"],
        "method": preset["method"],
        "name": preset["name"],
        "description": preset["description"],
        "request_params": preset.get("request_params"),
        "request_body": preset.get("request_body") or {},
    }


def warehouse_preset_needs_upgrade(
    path: Any,
    request_body: Any = None,
    method: Any = None,
    description: Any = None,
) -> bool:
    """须为 POST …/sbd/bd_warehouse/getList；组织由连接器填充，库内勿残留硬编码示例。"""
    if str(method or "").upper() not in ("", "POST"):
        return True
    lower = str(path or "").lower().replace("\\", "/")
    if "/sbd/bd_warehouse/getlist" not in lower:
        return True
    if not isinstance(request_body, dict):
        return True
    if request_body.get("pageNo") in (None, "") or request_body.get("pageSize") in (None, ""):
        return True
    data = request_body.get("data")
    if not isinstance(data, dict):
        return True
    # 历史预设把 BU-00000 写死在库里，须升级为 data 空对象由连接器注入
    if str(data.get("createorg_number") or "").strip().upper() == "BU-00000":
        return True
    if "连接器组织" not in str(description or ""):
        return True
    return False


def warehouse_batch_query_preset_needs_upgrade(
    request_body: Any,
    path: Any = None,
    method: Any = None,
    description: Any = None,
) -> bool:
    """兼容旧调用：无 path 时仅看 body；有 path 时按 getList 契约判定。"""
    if path is not None:
        return warehouse_preset_needs_upgrade(path, request_body, method, description)
    if not isinstance(request_body, dict):
        return True
    data = request_body.get("data")
    if not isinstance(data, dict):
        return True
    if request_body.get("pageNo") in (None, "") or request_body.get("pageSize") in (None, ""):
        return True
    return False


def kingdee_warehouse_api_upgrade_fields() -> Dict[str, Any]:
    preset = build_warehouse_get_list_preset()
    return {
        "path": preset["path"],
        "method": preset["method"],
        "name": preset["name"],
        "description": preset["description"],
        "request_params": preset.get("request_params"),
        "request_body": preset.get("request_body") or {},
    }


def _resolve_request_select(request_body: Any = None, request_params: Any = None) -> str:
    if isinstance(request_params, dict):
        raw = request_params.get("select")
        if raw not in (None, ""):
            return str(raw).strip()
    if isinstance(request_body, dict):
        raw = request_body.get("select")
        if raw not in (None, ""):
            return str(raw).strip()
        data = request_body.get("data")
        if isinstance(data, dict) and data.get("select") not in (None, ""):
            return str(data.get("select")).strip()
    return ""


def measureunits_preset_needs_upgrade(
    path: Any,
    request_body: Any = None,
    request_params: Any = None,
) -> bool:
    """
    旧预置常指向网关未挂通的单位对象，或未带精简 select，
    须升级为物料 batchQuery + 仅基础单位字段。
    """
    lower = str(path or "").lower().replace("\\", "/")
    if not lower:
        return True
    on_material = f"/{BIZ_BD_MATERIAL}/batchquery" in lower
    if not on_material:
        return True
    select = _resolve_request_select(request_body, request_params).lower().replace(" ", "")
    return "baseunit.number" not in select or "baseunit.name" not in select


def _material_batchquery_data_has_createorg_filter(request_body: Any) -> bool:
    if not isinstance(request_body, dict):
        return False
    data = request_body.get("data")
    if not isinstance(data, dict):
        return False
    from core.services.integration.kingdee_cosmic_paths import _is_createorg_filter_key

    return any(_is_createorg_filter_key(k) for k in data)


def _material_batchquery_data_has_blank_filters(request_body: Any) -> bool:
    """开放平台勾选未填会留下 id/number=''，出站前虽会剥离，入库预置仍应清掉。"""
    if not isinstance(request_body, dict):
        return False
    data = request_body.get("data")
    if not isinstance(data, dict) or not data:
        return False
    from core.services.integration.kingdee_cosmic_paths import (
        _is_blank_material_batchquery_filter_value,
    )

    return any(_is_blank_material_batchquery_filter_value(v) for v in data.values())


def material_preset_needs_upgrade(
    path: Any,
    request_body: Any = None,
    request_params: Any = None,
) -> bool:
    """物料预置缺 select 或未带基础单位/分组字段时升级，便于同步映射自动对齐。"""
    lower = str(path or "").lower().replace("\\", "/")
    if f"/{BIZ_BD_MATERIAL}/batchquery" not in lower:
        return False
    if _material_batchquery_data_has_createorg_filter(request_body):
        return True
    if _material_batchquery_data_has_blank_filters(request_body):
        return True
    select = _resolve_request_select(request_body, request_params).lower().replace(" ", "")
    if not select:
        return True
    return "baseunit.number" not in select or "baseunit.name" not in select


def build_supplier_query_preset() -> KingdeeCosmicApiPreset:
    """
    开放平台「查询供应商信息」：POST kapi/v2/basedata/bd_supplier/query。
    返回 number/name/status/enable 等；同步映射编码←number、名称←name。
    """
    return {
        "code_suffix": SUPPLIER_PRESET_CODE_SUFFIX,
        "name": "苍穹查询供应商",
        "description": (
            "开放平台已发布：查询供应商信息，接口编码 query，"
            "POST /v2/basedata/bd_supplier/query。"
            "请求体 data 内 createorg_number、number、status 等为数组（均可选）；"
            "pageNo、pageSize 与 data 同级。"
            "默认与物料一致：data 为空仅分页；需筛组织/状态再在 data 内加数组。"
            "按编码查可在 data.number 传 [\"编码\"]。勿使用未发布的 …/batchQuery。"
        ),
        "path": f"kapi/v2/basedata/{BIZ_BD_SUPPLIER}/query",
        "method": "POST",
        "request_body": build_supplier_query_preset_body(),
    }


def build_material_batch_query_preset() -> KingdeeCosmicApiPreset:
    """物料同步：batchQuery + select，返回列可自动映射主编码/名称/单位/分组。"""
    return {
        "code_suffix": MATERIAL_PRESET_CODE_SUFFIX,
        "name": "苍穹查询物料",
        "description": (
            "基础资料物料批量查询 /v2/basedata/bd_material/batchQuery。"
            f"请求 select={MATERIAL_SYNC_SELECT}，便于同步自动映射："
            "主编码←number，名称←name，规格←modelnum，"
            "基础单位←baseunit.number/name，分组←group.number/name。"
            "字段名若与本环境模型不一致，请在接口管理中微调 select。"
        ),
        "path": f"kapi/v2/basedata/{BIZ_BD_MATERIAL}/batchQuery",
        "method": "POST",
        "request_params": {
            "select": MATERIAL_SYNC_SELECT,
        },
        "request_body": {
            "data": {},
            "pageNo": 1,
            "pageSize": 100,
            "select": MATERIAL_SYNC_SELECT,
        },
    }


def kingdee_material_api_upgrade_fields() -> Dict[str, Any]:
    preset = build_material_batch_query_preset()
    return {
        "path": preset["path"],
        "method": preset["method"],
        "name": preset["name"],
        "description": preset["description"],
        "request_params": preset.get("request_params") or {},
        "request_body": preset.get("request_body") or {},
    }


def build_material_group_batch_query_preset_body(
    *,
    createorg_numbers: Optional[List[str]] = None,
    status_codes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    与供应商/物料一致：默认 data 空对象 + 分页；
    需筛组织/状态时在 data 内传 createorg_number、status 等字符串数组。
    """
    body: Dict[str, Any] = {
        "data": {},
        "pageNo": 1,
        "pageSize": 500,
    }
    data: Dict[str, Any] = {}
    if createorg_numbers:
        orgs = [str(x).strip() for x in createorg_numbers if str(x).strip()]
        if orgs:
            data["createorg_number"] = orgs
    if status_codes:
        codes = [str(x).strip() for x in status_codes if str(x).strip()]
        if codes:
            data["status"] = codes
    if data:
        body["data"] = data
    return body


def _material_group_query_body_shape_valid(request_body: Any) -> bool:
    if not isinstance(request_body, dict):
        return False
    if request_body.get("pageNo") in (None, "") or request_body.get("pageSize") in (None, ""):
        return False
    data = request_body.get("data")
    if not isinstance(data, dict):
        return False
    co = data.get("createorg_number")
    if co is not None and not (
        isinstance(co, list) and all(isinstance(x, str) for x in co)
    ):
        return False
    st = data.get("status")
    if st is not None and not (isinstance(st, list) and all(isinstance(x, str) for x in st)):
        return False
    return True


def _is_material_group_wang_placeholder_body(request_body: Any) -> bool:
    if not isinstance(request_body, dict):
        return False
    data = request_body.get("data")
    if not isinstance(data, dict):
        return False
    return data.get("createorg_number") == ["WANG"] and data.get("status") == ["C"]


def material_group_preset_needs_upgrade(
    path: Any,
    method: Any = None,
    request_body: Any = None,
) -> bool:
    """POST …/bd_materialgroup/batchQuery；合法空 data 不升级；createorg/空筛/WANG 须清掉。"""
    lower = str(path or "").lower().replace("\\", "/")
    if not lower:
        return True
    if "getmalgoodsclass" in lower or "mdr_goodsclass" in lower:
        return True
    if f"/{BIZ_BD_MATERIALGROUP}/batchquery" not in lower:
        return True
    if str(method or "").upper() not in ("", "POST"):
        return True
    if not _material_group_query_body_shape_valid(request_body):
        return True
    if _is_material_group_wang_placeholder_body(request_body):
        return True
    # 与物料 batchQuery 同契约：createorg / 勾选未填空项会导致 fetched=0
    if _material_batchquery_data_has_createorg_filter(request_body):
        return True
    if _material_batchquery_data_has_blank_filters(request_body):
        return True
    return False


def kingdee_material_group_api_upgrade_fields() -> Dict[str, Any]:
    preset = build_material_group_batch_query_preset()
    return {
        "path": preset["path"],
        "method": preset["method"],
        "name": preset["name"],
        "description": preset["description"],
        "request_body": preset.get("request_body") or {},
    }


def build_material_group_batch_query_preset() -> KingdeeCosmicApiPreset:
    """开放平台已发布：物料分类批量查询 POST …/bd_materialgroup/batchQuery。"""
    return {
        "code_suffix": MATERIAL_GROUP_PRESET_CODE_SUFFIX,
        "name": "苍穹查询物料分类",
        "description": (
            "开放平台已发布：物料分类批量查询，接口编码 batchQuery，"
            "POST /v2/basedata/bd_materialgroup/batchQuery。"
            "默认与「苍穹查询物料/供应商」一致：data 为空对象，仅 pageNo/pageSize 分页；"
            "可选筛选（createorg_number、status 等数组）请在接口库 data 内按需添加。"
            "加载常用接口或接口测试会自动去掉占位 WANG 模板。"
            "同步映射：编码←number，名称←name；启用/状态可在同步时勾选仅有效数据。"
        ),
        "path": f"kapi/v2/basedata/{BIZ_BD_MATERIALGROUP}/batchQuery",
        "method": "POST",
        "request_body": build_material_group_batch_query_preset_body(),
    }


def build_material_group_goods_class_preset() -> KingdeeCosmicApiPreset:
    """GMC 商品分类（与基础资料物料分类 batchQuery 不同对象）。"""
    return {
        "code_suffix": "query_goods_class",
        "name": "苍穹查询商品分类（GMC）",
        "description": (
            f"GMC 商品分类 {GOODS_CLASS_QUERY_PATH}；"
            "与基础资料「物料分类 batchQuery」不是同一路径。"
            "pageSize 必填，筛选项与分页同级（勿包 data）。"
        ),
        "path": GOODS_CLASS_QUERY_PATH,
        "method": "POST",
        "request_body": {
            "pageNo": 1,
            "pageSize": 100,
        },
    }


def build_measureunits_batch_query_preset() -> KingdeeCosmicApiPreset:
    """
    单位目录同步（苍穹）。

    现场网关常对独立计量单位 / 多计量单位返回「路由未找到」；
    物料 batchQuery 已探活。请求带 select，只拉编码/名称与基础单位。
    """
    return {
        "code_suffix": MEASUREUNITS_PRESET_CODE_SUFFIX,
        "name": "苍穹单位同步（从物料基础单位）",
        "description": (
            "本环境开放平台常未挂通 bd_measureunits / bd_multimeasureunit（网关 404）。"
            f"单位目录请用已探活的物料批量查询 /v2/basedata/{BIZ_BD_MATERIAL}/batchQuery，"
            f"请求 select={UNIT_SYNC_MATERIAL_SELECT}（只拉需要的列）。"
            "字段映射：编码←baseunit.number / baseunit_number，名称←baseunit.name / baseunit_name；"
            "按编码去重写入单位管理。"
        ),
        "path": f"kapi/v2/basedata/{BIZ_BD_MATERIAL}/batchQuery",
        "method": "POST",
        "request_params": {
            "select": UNIT_SYNC_MATERIAL_SELECT,
        },
        "request_body": {
            "data": {},
            "pageNo": 1,
            # 按物料翻页抽单位；单页太小且物料单位单一时，测试去重后会误以为「只有一个单位」
            "pageSize": 500,
            "select": UNIT_SYNC_MATERIAL_SELECT,
        },
    }


def kingdee_measureunits_api_upgrade_fields() -> Dict[str, Any]:
    preset = build_measureunits_batch_query_preset()
    return {
        "path": preset["path"],
        "method": preset["method"],
        "name": preset["name"],
        "description": preset["description"],
        "request_params": preset.get("request_params") or {},
        "request_body": preset.get("request_body") or {},
    }


def _basedata_batch_query_preset(
    *,
    code_suffix: str,
    name: str,
    biz_object: str,
    usage: str,
    request_body: Optional[Dict[str, Any]] = None,
) -> KingdeeCosmicApiPreset:
    """与基础资料API服务中物料批量查询同一拼法：/v2/basedata/{对象}/batchQuery。"""
    body = request_body if isinstance(request_body, dict) else {
        "data": {},
        "pageNo": 1,
        "pageSize": 100,
    }
    return {
        "code_suffix": code_suffix,
        "name": name,
        "description": (
            f"基础资料API服务里的{usage}批量查询。"
            f"请求地址 /v2/basedata/{biz_object}/batchQuery，"
            "请求体为 data、pageNo、pageSize。筛选字段放在 data 内。"
        ),
        "path": f"kapi/v2/basedata/{biz_object}/batchQuery",
        "method": "POST",
        "request_body": body,
    }


def _sys_query_path(biz_object: str) -> str:
    return f"kapi/sys/{biz_object}/query"


def build_sys_query_params(
    *,
    select: str,
    filter_expr: str = "",
    page_no: int = 1,
    page_size: int = 500,
    orderby: str = "",
) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "select": select,
        "page_no": page_no,
        "page_size": page_size,
    }
    if filter_expr.strip():
        params["filter"] = filter_expr.strip()
    if orderby.strip():
        params["orderby"] = orderby.strip()
    return params


def build_get_token_preset_body() -> Dict[str, Any]:
    """与官方增强型 Token 请求体一致；联调时须换成连接器同款凭证。"""
    return {
        "client_id": "<系统编码 client_id>",
        "client_secret": "<AccessToken认证密钥>",
        "username": "<代理用户登录名>",
        "accountId": "<数据中心 accountId>",
        "language": "zh_CN",
        "nonce": "<10分钟内不重复的随机串>",
        "timestamp": "<YYYY-MM-DD HH:MM:SS，前后5分钟内>",
    }


def resolve_preset_api_code(connection_code: str, code_suffix: str) -> str:
    """租户内唯一：连接器 code + 后缀，截断至 50 字符。"""
    base = str(connection_code or "kingdee").strip() or "kingdee"
    suffix = str(code_suffix or "").strip()
    raw = f"{base}_{suffix}" if suffix else base
    return raw[:50]


def build_im_purinbill_add_sample_body() -> Dict[str, Any]:
    """
    采购入库单新增最小可编辑样例（开放平台 im_purinbill/add）。
    组织/单据类型/库存事务等编码须按本环境替换；物料明细必填 material_number、qty、
    invstatus_number、invtype_number、linetype_number。
    """
    return {
        "data": {
            "biztime": "2026-01-01",
            "exratedate": "2026-01-01",
            "paymode": "CREDIT",
            "org_number": "REPLACE_ORG",
            "billtype_number": "im_PurInBill_STD_BT_S",
            "bizorg_number": "REPLACE_ORG",
            "biztype_number": "110",
            "invscheme_number": "110",
            "supplier_number": "REPLACE_SUPPLIER",
            "trdbillno": "LOCAL-PR-SAMPLE",
            "comment": "快格云采购入库出站样例",
            "billentry": [
                {
                    "material_number": "REPLACE_MATERIAL",
                    "qty": 1,
"unit_number": "pcs",
                    "baseqty": 1,
                    "unit2nd_number": "REPLACE_AUX_UNIT",
                    "qtyunit2nd": 1,
                    "warehouse_number": "REPLACE_WAREHOUSE",
                    # 可用 / 普通 / 标准行；组织仍须按账套替换 REPLACE_ORG
                    "invstatus_number": "110",
                    "invtype_number": "110",
                    "linetype_number": "010",
                }
            ],
        }
    }


def kingdee_cosmic_path_is_outbound_write(path: Any) -> bool:
    """苍穹单据写入路径：…/add、…/add2、…/batchAdd、…/batchUpdate（不含 query/getList 等入站）。"""
    lower = str(path or "").lower().replace("\\", "/").split("?", 1)[0].rstrip("/")
    return bool(
        re.search(r"/batchadd$", lower)
        or re.search(r"/batchupdate$", lower)
        or re.search(r"/add\d*$", lower)
    )


def _im_batch_update_sample_from_add_body(
    add_body: Dict[str, Any],
    *,
    bill_id: str = "REPLACE_BILL_ID",
    entry_id: str = "REPLACE_ENTRY_ID",
) -> Dict[str, Any]:
    """
    由新增样例生成 batchUpdate 样例：data 统一为单据数组；头/分录均带候选键 id。
    """
    raw = copy.deepcopy(add_body.get("data"))
    if isinstance(raw, list):
        rows = [row for row in raw if isinstance(row, dict)]
    elif isinstance(raw, dict):
        rows = [raw]
    else:
        rows = [{}]
    for row in rows:
        row["id"] = bill_id
        entries = row.get("billentry")
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    entry["id"] = entry_id
    return {"data": rows}


def resolve_preset_sync_direction(preset: Dict[str, Any]) -> str:
    """预设同步方向：显式字段优先；写入类后缀或 add/batchAdd 路径为 push，其余 pull。"""
    raw = str(preset.get("sync_direction") or "").strip().lower()
    if raw in ("pull", "push", "bidirectional"):
        return raw
    suffix = str(preset.get("code_suffix") or "").strip()
    if suffix in KINGDEE_COSMIC_OUTBOUND_PRESET_CODE_SUFFIXES:
        return "push"
    if kingdee_cosmic_path_is_outbound_write(preset.get("path")):
        return "push"
    return "pull"


def outbound_preset_sync_direction_needs_upgrade(
    code_suffix: Any,
    sync_direction: Any,
    path: Any = None,
) -> bool:
    """已落库的新增/批量新增类若仍标入站，须升为出站。"""
    is_outbound = (
        str(code_suffix or "").strip() in KINGDEE_COSMIC_OUTBOUND_PRESET_CODE_SUFFIXES
        or kingdee_cosmic_path_is_outbound_write(path)
    )
    if not is_outbound:
        return False
    return str(sync_direction or "pull").strip().lower() != "push"


def build_im_purinbill_add_preset() -> KingdeeCosmicApiPreset:
    from core.services.integration.outbound_field_mappings import (
        default_purchase_receipt_outbound_mappings,
    )

    return {
        "code_suffix": IM_PURINBILL_ADD_PRESET_CODE_SUFFIX,
        "name": "苍穹采购入库单新增",
        "description": (
            f"库存管理采购入库单新增（API 编码 add）。"
            f"请求地址 /v2/im/{BIZ_IM_PURINBILL}/add。"
            "请求体为 data；头必填含 biztime、exratedate、paymode、org_number、"
            "billtype_number、bizorg_number、biztype_number、invscheme_number、supplier_number、billentry；"
            "明细必填 material_number、qty、invstatus_number、invtype_number、linetype_number。"
            "样例中 REPLACE_* 请改为本环境真实编码后联调；trdbillno 可写本地入库单号。"
            "出站字段映射可在接口管理中维护（本地字段→对方字段）；标品 add 无验收人；"
            "需验收人请加载「【自定义】苍穹采购入库单新增(含验收人)」add2。"
        ),
        "path": IM_PURINBILL_ADD_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": build_im_purinbill_add_sample_body(),
        "outbound_field_mappings": default_purchase_receipt_outbound_mappings(),
    }


def build_im_purinbill_add2_sample_body() -> Dict[str, Any]:
    """【自定义】扩展 add2：在标品样例上增加验收人文本 fd81_yanshou。"""
    body = build_im_purinbill_add_sample_body()
    data = body.get("data")
    if isinstance(data, dict):
        data = dict(data)
        data[IM_PURINBILL_ACCEPTOR_FIELD] = "测试"
        data["bizoperator_operatornumber"] = "REPLACE_BUYER"
        data["bizoperatorgroup_number"] = "REPLACE_BUYER_GROUP"
        body = {**body, "data": data}
    return body


IM_PURINBILL_ADD2_PRESET_NAME = "【自定义】苍穹采购入库单新增(含验收人)"


def im_purinbill_add2_preset_needs_upgrade(name: Any, path: Any) -> bool:
    """已落库的自定义 add2 若未带【自定义】标识或路径偏差，须升级。"""
    name_s = str(name or "").strip()
    path_s = str(path or "").lower().replace("\\", "/").split("?", 1)[0].rstrip("/")
    if "【自定义】" not in name_s:
        return True
    return not path_s.endswith("/fd81/im/im_purinbill/add2")


def build_im_purinbill_add2_preset() -> KingdeeCosmicApiPreset:
    from core.services.integration.outbound_field_mappings import (
        default_purchase_receipt_outbound_mappings,
    )

    return {
        "code_suffix": IM_PURINBILL_ADD2_PRESET_CODE_SUFFIX,
        "name": IM_PURINBILL_ADD2_PRESET_NAME,
        "description": (
            "【自定义】客户扩展采购入库单新增（API 编码 add2；非标品）。"
            f"请求地址 /{IM_PURINBILL_ADD2_PATH}。"
            f"相对标品 add 增加验收人文本字段 {IM_PURINBILL_ACCEPTOR_FIELD}（必填）；"
            "采购员仍为 bizoperator_operatornumber（供应链业务员编码）；库管员非必填。"
            "样例中 REPLACE_* 与验收人文本请按本环境修改后联调。"
            "推送配置须将 save_path / save_api_uuid 指向本接口，并设 acceptor_field。"
            "出站字段映射同标品 add，可在接口管理中调整。"
        ),
        "path": IM_PURINBILL_ADD2_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": build_im_purinbill_add2_sample_body(),
        "outbound_field_mappings": default_purchase_receipt_outbound_mappings(),
    }


def build_im_purinbill_batch_unaudit_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": "batch_unaudit_im_purinbill",
        "name": "苍穹采购入库单批量反审核",
        "description": (
            f"库存管理采购入库单批量反审核（开放平台 API 编码 batchUnaudit）。"
            f"请求地址 /v2/im/{BIZ_IM_PURINBILL}/batchUnaudit。"
            "请求体 data 为 Map，含 id/ids/billno；MES 撤回入库时调用。"
        ),
        "path": IM_PURINBILL_BATCH_UNAUDIT_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": _build_im_batch_operate_sample_body(billno="LOCAL-PR-BILLNO"),
    }


def build_im_purinbill_batch_unsubmit_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": "batch_unsubmit_im_purinbill",
        "name": "苍穹采购入库单批量撤销提交",
        "description": (
            f"库存管理采购入库单批量撤销提交（开放平台 API 编码 batchUnsubmit）。"
            f"请求地址 /v2/im/{BIZ_IM_PURINBILL}/batchUnsubmit。"
            "请求体 data 为 Map，含 id/ids/billno；MES 撤回入库时在反审核后调用。"
        ),
        "path": IM_PURINBILL_BATCH_UNSUBMIT_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": _build_im_batch_operate_sample_body(billno="LOCAL-PR-BILLNO"),
    }


def build_im_purinbill_batch_delete_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": "batch_delete_im_purinbill",
        "name": "苍穹采购入库单批量删除",
        "description": (
            f"库存管理采购入库单批量删除（开放平台 API 编码 batchDelete）。"
            f"请求地址 /v2/im/{BIZ_IM_PURINBILL}/batchDelete。"
            "请求体 data 为 Map，含 id/ids/billno；MES 删除本地入库单时调用。"
        ),
        "path": IM_PURINBILL_BATCH_DELETE_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": _build_im_batch_operate_sample_body(billno="LOCAL-PR-BILLNO"),
    }


def build_im_purinbill_batch_update_preset() -> KingdeeCosmicApiPreset:
    from core.services.integration.outbound_field_mappings import (
        default_purchase_receipt_outbound_mappings,
    )

    return {
        "code_suffix": IM_PURINBILL_BATCH_UPDATE_PRESET_CODE_SUFFIX,
        "name": "苍穹采购入库单批量更新",
        "description": (
            f"库存管理采购入库单批量更新（开放平台 API 编码 batchUpdate）。"
            f"请求地址 /v2/im/{BIZ_IM_PURINBILL}/batchUpdate。"
            "请求体 data 为单据数组；头必填 id（候选键）及 biztime、exratedate、paymode、"
            "org_number、billtype_number、bizorg_number、biztype_number、invscheme_number、"
            "supplier_number、billentry；分录候选键 billentry.id。"
            "金蝶已存在同号单据时勿再 batchAdd/add，改绑本接口更新后补提交/审核。"
            "样例中 REPLACE_* / REPLACE_BILL_ID 请改为本环境真实值。"
        ),
        "path": IM_PURINBILL_BATCH_UPDATE_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": _im_batch_update_sample_from_add_body(
            build_im_purinbill_add_sample_body()
        ),
        "outbound_field_mappings": default_purchase_receipt_outbound_mappings(),
    }


def build_im_saloutbill_batch_add_sample_body() -> Dict[str, Any]:
    """
    销售出库单批量新增最小可编辑样例（开放平台 im_saloutbill/batchAdd）。
    请求体 data 为单据数组；头/明细必填见开放平台参数表。
    """
    return {
        "data": [
            {
                "biztime": "2026-01-01",
                "exratedate": "2026-01-01",
                "exchangerate": 1,
                "paymode": "CREDIT",
                "istax": True,
                "isredbill": False,
                "currency_number": "CNY",
                "settlecurrency_number": "CNY",
                # 系统预置汇率表（本环境实测 ERT-01）；销售部门非必填，样例不传 bizdept_number
                "exratetable_number": "ERT-01",
                "org_number": "REPLACE_ORG",
                "bizorg_number": "REPLACE_ORG",
                "billtype_number": "im_SalOutBill_STD_BT_S",
                "biztype_number": "210",
                "invscheme_number": "210",
                "customer_number": "REPLACE_CUSTOMER",
                "billno": "LOCAL-SD-SAMPLE",
                "comment": "快格云销售出库出站样例",
                "billentry": [
                    {
                        "material_number": "REPLACE_MATERIAL",
                        "qty": 1,
                        "unit_number": "pcs",
                        "warehouse_number": "REPLACE_WAREHOUSE",
                        "linetype_number": "REPLACE_LINETYPE",
                        "entrysettleorg_number": "REPLACE_ORG",
                        "discounttype": "NULL",
                    }
                ],
            }
        ]
    }


def build_im_saloutbill_batch_add_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": IM_SALOUTBILL_BATCH_ADD_PRESET_CODE_SUFFIX,
        "name": "苍穹销售出库单批量新增",
        "description": (
            f"库存管理销售出库单批量新增（API 编码 batchAdd）。"
            f"请求地址 /v2/im/{BIZ_IM_SALOUTBILL}/batchAdd。"
            "请求体 data 为单据数组；头必填含 org_number、billtype_number、biztype_number、"
            "invscheme_number、biztime、customer_number、bizorg_number、"
            "settlecurrency_number、exratetable_number、exratedate、exchangerate、"
            "paymode、istax、billentry（currency_number 可与结算币别同传；bizdept_number 销售部门非必填）；"
            "明细必填 linetype_number、material_number、qty、warehouse_number、"
            "entrysettleorg_number、discounttype；提交/审核还需明细价税字段。"
            "快格云外推默认：batchAdd 保存成功后自动 batchSubmit → batchAudit（与采购入库一致）。"
            "样例中 REPLACE_* 请改为本环境真实编码后联调；billno 可写本地出库单号。"
        ),
        "path": IM_SALOUTBILL_BATCH_ADD_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": build_im_saloutbill_batch_add_sample_body(),
    }


def build_im_saloutbill_batch_submit_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": "batch_submit_im_saloutbill",
        "name": "苍穹销售出库单批量提交",
        "description": (
            f"库存管理销售出库单批量提交（开放平台 API 编码 batchSubmit）。"
            f"请求地址 /v2/im/{BIZ_IM_SALOUTBILL}/batchSubmit。"
            "请求体 data 为 Map，含 id、ids、billno（与 batchAdd 返回内码/单号一致）；"
            "快格云外推 batchAdd 保存成功后自动调用，再 batchAudit。"
            "返回 data.failCount / successCount 非 0 时视为失败。"
        ),
        "path": IM_SALOUTBILL_BATCH_SUBMIT_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": _build_im_batch_operate_sample_body(billno="LOCAL-SO-BILLNO"),
    }


def build_im_saloutbill_batch_audit_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": "batch_audit_im_saloutbill",
        "name": "苍穹销售出库单批量审核",
        "description": (
            f"库存管理销售出库单批量审核（开放平台 API 编码 batchAudit）。"
            f"请求地址 /v2/im/{BIZ_IM_SALOUTBILL}/batchAudit。"
            "请求体 data 为 Map，含 id、ids、billno（与 batchSubmit 相同形态）。"
        ),
        "path": IM_SALOUTBILL_BATCH_AUDIT_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": _build_im_batch_operate_sample_body(billno="LOCAL-SO-BILLNO"),
    }


def build_im_otheroutbill_batch_add_sample_body() -> Dict[str, Any]:
    """
    其他出库单批量新增最小可编辑样例（开放平台 im_otheroutbill/batchAdd）。
    请求体 data 为单据数组；头/明细必填见开放平台参数表。
    """
    return {
        "data": [
            {
                "biztime": "2026-01-01",
                "org_number": "REPLACE_ORG",
                "billtype_number": "REPLACE_BILLTYPE",
                "biztype_number": "REPLACE_BIZTYPE",
                "invscheme_number": "REPLACE_INVSCHEME",
                "billno": "LOCAL-OO-SAMPLE",
                "comment": "快格云其他出库出站样例",
                "bizdept_number": "REPLACE_PICKDEPT",
                "pickdept_number": "REPLACE_PICKDEPT",
                "pickeroperator_operatornumber": "REPLACE_PICKER",
                "pickeroperator_number": "REPLACE_PICKER",
                "customer_number": "REPLACE_CUSTOMER",
                "billentry": [
                    {
                        "material_number": "REPLACE_MATERIAL",
                        "qty": 1,
                        "unit_number": "pcs",
                        "warehouse_number": "REPLACE_WAREHOUSE",
                        "linetype_number": "REPLACE_LINETYPE",
                    }
                ],
            }
        ]
    }


def build_im_otherinbill_batch_add_sample_body() -> Dict[str, Any]:
    return {
        "data": [
            {
                "biztime": "2026-01-01",
                "bookdate": "2026-01-01",
                "org_number": "REPLACE_ORG",
                "billtype_number": "im_OtherInBill_STD_BT_S",
                "biztype_number": "354",
                "invscheme_number": "354",
                "billno": "LOCAL-OI-SAMPLE",
                "comment": "快格云其他入库出站样例",
                "bizdept_number": "REPLACE_DEPT",
                "operator_operatornumber": "REPLACE_OPERATOR",
                "bizoperator_operatornumber": "REPLACE_OPERATOR",
                "billentry": [
                    {
                        "material_number": "REPLACE_MATERIAL",
                        "linetype_number": "010",
                        "invstatus_number": "110",
                        "invtype_number": "110",
                        "outinvstatus_number": "110",
                        "outinvtype_number": "110",
                        "ownertype": "bos_org",
                        "keepertype": "bos_org",
                        "owner_number": "REPLACE_ORG",
                        "keeper_number": "REPLACE_ORG",
                        "outownertype": "bos_org",
                        "outkeepertype": "bos_org",
                        "outowner_number": "REPLACE_ORG",
                        "outkeeper_number": "REPLACE_ORG",
                        "warehouse_number": "REPLACE_WAREHOUSE",
                        "unit_number": "pcs",
                        "qty": 1,
                    }
                ],
            }
        ]
    }


def build_im_otherinbill_batch_add_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": IM_OTHERINBILL_BATCH_ADD_PRESET_CODE_SUFFIX,
        "name": "苍穹其他入库单批量新增",
        "description": (
            f"库存管理其他入库单批量新增（API 编码 batchAdd）。"
            f"请求地址 /v2/im/{BIZ_IM_OTHERINBILL}/batchAdd。"
            "请求体 data 为单据数组；头必填含 org_number、billtype_number、biztype_number、"
            "invscheme_number、biztime、billentry；"
            "明细必填 linetype_number、material_number、unit_number、qty、warehouse_number、"
            "invstatus_number、invtype_number、outinvstatus_number、outinvtype_number、"
            "ownertype、keepertype、owner_number、keeper_number。"
            "样例中 REPLACE_* 请改为本环境真实编码后联调；billno 可写本地入库单号。"
            "外推保存后自动提交 batchSubmit、审核 billbatchAudit（非 batchAudit）。"
            "成品入库请改用「苍穹成品入库其他入库批量新增」，勿把标准其他入库单据类型用于完工入库。"
        ),
        "path": IM_OTHERINBILL_BATCH_ADD_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": build_im_otherinbill_batch_add_sample_body(),
    }


def build_im_otherinbill_finished_goods_batch_add_sample_body() -> Dict[str, Any]:
    """成品入库 → 其他入库：路径与 batchAdd 相同，单据类型须为「生产完工入库」。"""
    body = build_im_otherinbill_batch_add_sample_body()
    rows = body.get("data")
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        rows[0]["billtype_number"] = "REPLACE_BILLTYPE_FINISHED_GOODS_RECEIPT"
        rows[0]["biztype_number"] = "REPLACE_BIZTYPE_FINISHED_GOODS_RECEIPT"
        rows[0]["invscheme_number"] = "REPLACE_INVSCHEME_FINISHED_GOODS_RECEIPT"
        rows[0]["billno"] = "LOCAL-FG-SAMPLE"
        rows[0]["comment"] = "快格云成品入库→苍穹其他入库（单据类型=生产完工入库）"
    return body


def build_im_otherinbill_finished_goods_batch_add_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": IM_OTHERINBILL_FINISHED_GOODS_BATCH_ADD_PRESET_CODE_SUFFIX,
        "name": "苍穹成品入库其他入库批量新增",
        "description": (
            "MES 成品入库单外推专用：写入库存管理其他入库单（API 编码 batchAdd），"
            f"请求地址 /v2/im/{BIZ_IM_OTHERINBILL}/batchAdd。"
            "单据类型 billtype_number 必须为本环境「生产完工入库」编码"
            "（勿填标准其他入库单）；biztype_number / invscheme_number 与该单据类型配套。"
            "头/明细必填同其他入库。"
            "样例 REPLACE_*_FINISHED_GOODS_RECEIPT 请改为本账套真实编码后挂到成品入库推送绑定。"
            "保存后仍走同对象 batchSubmit / billbatchAudit。"
        ),
        "path": IM_OTHERINBILL_BATCH_ADD_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": build_im_otherinbill_finished_goods_batch_add_sample_body(),
    }


def _build_im_batch_operate_sample_body(*, billno: str) -> Dict[str, Any]:
    """batchSubmit / billbatchAudit：data 为 Map，含 id/ids/billno。"""
    return {
        "data": {
            "id": "REPLACE_BILL_ID",
            "ids": "REPLACE_BILL_ID",
            "billno": billno,
        }
    }


def _build_im_batch_operate_preset(
    *,
    code_suffix: str,
    name: str,
    description: str,
    path: str,
    billno: str,
) -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": code_suffix,
        "name": name,
        "description": description,
        "path": path,
        "method": "POST",
        "sync_direction": "push",
        "request_body": _build_im_batch_operate_sample_body(billno=billno),
    }


def build_im_saloutbill_batch_unaudit_preset() -> KingdeeCosmicApiPreset:
    return _build_im_batch_operate_preset(
        code_suffix="batch_unaudit_im_saloutbill",
        name="苍穹销售出库单批量反审核",
        description=(
            f"库存管理销售出库单批量反审核（开放平台 API 编码 batchUnaudit）。"
            f"请求地址 /v2/im/{BIZ_IM_SALOUTBILL}/batchUnaudit。"
            "请求体 data 为 Map，含 id/ids/billno。"
        ),
        path=IM_SALOUTBILL_BATCH_UNAUDIT_PATH,
        billno="LOCAL-SO-BILLNO",
    )


def build_im_saloutbill_batch_unsubmit_preset() -> KingdeeCosmicApiPreset:
    return _build_im_batch_operate_preset(
        code_suffix="batch_unsubmit_im_saloutbill",
        name="苍穹销售出库单批量撤销提交",
        description=(
            f"库存管理销售出库单批量撤销提交（开放平台 API 编码 batchUnsubmit）。"
            f"请求地址 /v2/im/{BIZ_IM_SALOUTBILL}/batchUnsubmit。"
            "请求体 data 为 Map，含 id/ids/billno。"
        ),
        path=IM_SALOUTBILL_BATCH_UNSUBMIT_PATH,
        billno="LOCAL-SO-BILLNO",
    )


def build_im_saloutbill_batch_delete_preset() -> KingdeeCosmicApiPreset:
    return _build_im_batch_operate_preset(
        code_suffix="batch_delete_im_saloutbill",
        name="苍穹销售出库单批量删除",
        description=(
            f"库存管理销售出库单批量删除（开放平台 API 编码 batchDelete）。"
            f"请求地址 /v2/im/{BIZ_IM_SALOUTBILL}/batchDelete。"
            "请求体 data 为 Map，含 id/ids/billno。"
        ),
        path=IM_SALOUTBILL_BATCH_DELETE_PATH,
        billno="LOCAL-SO-BILLNO",
    )


def build_im_saloutbill_batch_update_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": IM_SALOUTBILL_BATCH_UPDATE_PRESET_CODE_SUFFIX,
        "name": "苍穹销售出库单批量更新",
        "description": (
            f"库存管理销售出库单批量更新（开放平台 API 编码 batchUpdate）。"
            f"请求地址 /v2/im/{BIZ_IM_SALOUTBILL}/batchUpdate。"
            "请求体 data 为单据数组；头必填 id（候选键），字段口径与 batchAdd 一致；"
            "分录须带 billentry.id。金蝶已存在同 billno 时改绑本接口，勿再 batchAdd。"
        ),
        "path": IM_SALOUTBILL_BATCH_UPDATE_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": _im_batch_update_sample_from_add_body(
            build_im_saloutbill_batch_add_sample_body()
        ),
    }


def build_im_otheroutbill_batch_unaudit_preset() -> KingdeeCosmicApiPreset:
    return _build_im_batch_operate_preset(
        code_suffix="batch_unaudit_im_otheroutbill",
        name="苍穹其他出库单批量反审核",
        description=(
            f"库存管理其他出库单批量反审核（开放平台 API 编码 batchUnaudit）。"
            f"请求地址 /v2/im/{BIZ_IM_OTHEROUTBILL}/batchUnaudit。"
            "请求体 data 为 Map，含 id/ids/billno。"
        ),
        path=IM_OTHEROUTBILL_BATCH_UNAUDIT_PATH,
        billno="LOCAL-OO-BILLNO",
    )


def build_im_otheroutbill_batch_unsubmit_preset() -> KingdeeCosmicApiPreset:
    return _build_im_batch_operate_preset(
        code_suffix="batch_unsubmit_im_otheroutbill",
        name="苍穹其他出库单批量撤销提交",
        description=(
            f"库存管理其他出库单批量撤销提交（开放平台 API 编码 batchUnsubmit）。"
            f"请求地址 /v2/im/{BIZ_IM_OTHEROUTBILL}/batchUnsubmit。"
            "请求体 data 为 Map，含 id/ids/billno。"
        ),
        path=IM_OTHEROUTBILL_BATCH_UNSUBMIT_PATH,
        billno="LOCAL-OO-BILLNO",
    )


def build_im_otheroutbill_batch_delete_preset() -> KingdeeCosmicApiPreset:
    return _build_im_batch_operate_preset(
        code_suffix="batch_delete_im_otheroutbill",
        name="苍穹其他出库单批量删除",
        description=(
            f"库存管理其他出库单批量删除（开放平台 API 编码 batchDelete）。"
            f"请求地址 /v2/im/{BIZ_IM_OTHEROUTBILL}/batchDelete。"
            "请求体 data 为 Map，含 id/ids/billno。"
        ),
        path=IM_OTHEROUTBILL_BATCH_DELETE_PATH,
        billno="LOCAL-OO-BILLNO",
    )


def build_im_otheroutbill_production_picking_batch_unaudit_preset() -> KingdeeCosmicApiPreset:
    return _build_im_batch_operate_preset(
        code_suffix="batch_unaudit_im_otheroutbill_production_picking",
        name="苍穹生产领料其他出库批量反审核",
        description=(
            "MES 生产领料外推专用：其他出库单 batchUnaudit，"
            f"请求地址 /v2/im/{BIZ_IM_OTHEROUTBILL}/batchUnaudit。"
            "与标准其他出库同路径，关联单据 production_picking。"
        ),
        path=IM_OTHEROUTBILL_BATCH_UNAUDIT_PATH,
        billno="LOCAL-PP-BILLNO",
    )


def build_im_otheroutbill_production_picking_batch_unsubmit_preset() -> KingdeeCosmicApiPreset:
    return _build_im_batch_operate_preset(
        code_suffix="batch_unsubmit_im_otheroutbill_production_picking",
        name="苍穹生产领料其他出库批量撤销提交",
        description=(
            "MES 生产领料外推专用：其他出库单 batchUnsubmit，"
            f"请求地址 /v2/im/{BIZ_IM_OTHEROUTBILL}/batchUnsubmit。"
            "与标准其他出库同路径，关联单据 production_picking。"
        ),
        path=IM_OTHEROUTBILL_BATCH_UNSUBMIT_PATH,
        billno="LOCAL-PP-BILLNO",
    )


def build_im_otheroutbill_production_picking_batch_delete_preset() -> KingdeeCosmicApiPreset:
    return _build_im_batch_operate_preset(
        code_suffix="batch_delete_im_otheroutbill_production_picking",
        name="苍穹生产领料其他出库批量删除",
        description=(
            "MES 生产领料外推专用：其他出库单 batchDelete，"
            f"请求地址 /v2/im/{BIZ_IM_OTHEROUTBILL}/batchDelete。"
            "与标准其他出库同路径，关联单据 production_picking。"
        ),
        path=IM_OTHEROUTBILL_BATCH_DELETE_PATH,
        billno="LOCAL-PP-BILLNO",
    )


def build_im_otheroutbill_batch_update_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": IM_OTHEROUTBILL_BATCH_UPDATE_PRESET_CODE_SUFFIX,
        "name": "苍穹其他出库单批量更新",
        "description": (
            f"库存管理其他出库单批量更新（开放平台 API 编码 batchUpdate）。"
            f"请求地址 /v2/im/{BIZ_IM_OTHEROUTBILL}/batchUpdate。"
            "请求体 data 为单据数组；头/分录均须带候选键 id；字段口径与 batchAdd 一致。"
            "金蝶已存在同号时改绑本接口。生产领料请用专用更新预置。"
        ),
        "path": IM_OTHEROUTBILL_BATCH_UPDATE_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": _im_batch_update_sample_from_add_body(
            build_im_otheroutbill_batch_add_sample_body()
        ),
    }


def build_im_otheroutbill_production_picking_batch_update_preset() -> KingdeeCosmicApiPreset:
    body = _im_batch_update_sample_from_add_body(
        build_im_otheroutbill_batch_add_sample_body()
    )
    rows = body.get("data") if isinstance(body.get("data"), list) else []
    if rows and isinstance(rows[0], dict):
        rows[0]["billno"] = "LOCAL-PP-SAMPLE"
        rows[0]["comment"] = "快格云生产领料其他出库更新样例"
    return {
        "code_suffix": IM_OTHEROUTBILL_PRODUCTION_PICKING_BATCH_UPDATE_PRESET_CODE_SUFFIX,
        "name": "苍穹生产领料其他出库批量更新",
        "description": (
            "MES 生产领料外推专用：其他出库单 batchUpdate，"
            f"请求地址 /v2/im/{BIZ_IM_OTHEROUTBILL}/batchUpdate。"
            "关联单据 production_picking；单据类型须为本环境「生产领料」。"
            "头/分录候选键 id 必填。"
        ),
        "path": IM_OTHEROUTBILL_BATCH_UPDATE_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": body,
    }


def build_im_otherinbill_batch_unaudit_preset() -> KingdeeCosmicApiPreset:
    return _build_im_batch_operate_preset(
        code_suffix="batch_unaudit_im_otherinbill",
        name="苍穹其他入库单批量反审核",
        description=(
            f"库存管理其他入库单批量反审核（开放平台 API 编码 batchUnaudit）。"
            f"请求地址 /v2/im/{BIZ_IM_OTHERINBILL}/batchUnaudit。"
            "请求体 data 为 Map，含 id/ids/billno。"
        ),
        path=IM_OTHERINBILL_BATCH_UNAUDIT_PATH,
        billno="LOCAL-OI-BILLNO",
    )


def build_im_otherinbill_batch_unsubmit_preset() -> KingdeeCosmicApiPreset:
    return _build_im_batch_operate_preset(
        code_suffix="batch_unsubmit_im_otherinbill",
        name="苍穹其他入库单批量撤销提交",
        description=(
            f"库存管理其他入库单批量撤销提交（开放平台 API 编码 batchUnsubmit）。"
            f"请求地址 /v2/im/{BIZ_IM_OTHERINBILL}/batchUnsubmit。"
            "请求体 data 为 Map，含 id/ids/billno。"
        ),
        path=IM_OTHERINBILL_BATCH_UNSUBMIT_PATH,
        billno="LOCAL-OI-BILLNO",
    )


def build_im_otherinbill_batch_delete_preset() -> KingdeeCosmicApiPreset:
    return _build_im_batch_operate_preset(
        code_suffix="batch_delete_im_otherinbill",
        name="苍穹其他入库单批量删除",
        description=(
            f"库存管理其他入库单批量删除（开放平台 API 编码 batchDelete）。"
            f"请求地址 /v2/im/{BIZ_IM_OTHERINBILL}/batchDelete。"
            "请求体 data 为 Map，含 id/ids/billno。"
        ),
        path=IM_OTHERINBILL_BATCH_DELETE_PATH,
        billno="LOCAL-OI-BILLNO",
    )


def build_im_otherinbill_finished_goods_batch_unaudit_preset() -> KingdeeCosmicApiPreset:
    return _build_im_batch_operate_preset(
        code_suffix="batch_unaudit_im_otherinbill_finished_goods_receipt",
        name="苍穹成品入库其他入库批量反审核",
        description=(
            "MES 成品入库外推专用：其他入库单 batchUnaudit，"
            f"请求地址 /v2/im/{BIZ_IM_OTHERINBILL}/batchUnaudit。"
            "与标准其他入库同路径，关联单据 finished_goods_receipt。"
        ),
        path=IM_OTHERINBILL_BATCH_UNAUDIT_PATH,
        billno="LOCAL-FG-BILLNO",
    )


def build_im_otherinbill_finished_goods_batch_unsubmit_preset() -> KingdeeCosmicApiPreset:
    return _build_im_batch_operate_preset(
        code_suffix="batch_unsubmit_im_otherinbill_finished_goods_receipt",
        name="苍穹成品入库其他入库批量撤销提交",
        description=(
            "MES 成品入库外推专用：其他入库单 batchUnsubmit，"
            f"请求地址 /v2/im/{BIZ_IM_OTHERINBILL}/batchUnsubmit。"
            "与标准其他入库同路径，关联单据 finished_goods_receipt。"
        ),
        path=IM_OTHERINBILL_BATCH_UNSUBMIT_PATH,
        billno="LOCAL-FG-BILLNO",
    )


def build_im_otherinbill_finished_goods_batch_delete_preset() -> KingdeeCosmicApiPreset:
    return _build_im_batch_operate_preset(
        code_suffix="batch_delete_im_otherinbill_finished_goods_receipt",
        name="苍穹成品入库其他入库批量删除",
        description=(
            "MES 成品入库外推专用：其他入库单 batchDelete，"
            f"请求地址 /v2/im/{BIZ_IM_OTHERINBILL}/batchDelete。"
            "与标准其他入库同路径，关联单据 finished_goods_receipt。"
        ),
        path=IM_OTHERINBILL_BATCH_DELETE_PATH,
        billno="LOCAL-FG-BILLNO",
    )


def build_im_otherinbill_batch_update_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": IM_OTHERINBILL_BATCH_UPDATE_PRESET_CODE_SUFFIX,
        "name": "苍穹其他入库单批量更新",
        "description": (
            f"库存管理其他入库单批量更新（开放平台 API 编码 batchUpdate）。"
            f"请求地址 /v2/im/{BIZ_IM_OTHERINBILL}/batchUpdate。"
            "请求体 data 为单据数组；头/分录均须带候选键 id；字段口径与 batchAdd 一致。"
            "成品入库请用专用更新预置。"
        ),
        "path": IM_OTHERINBILL_BATCH_UPDATE_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": _im_batch_update_sample_from_add_body(
            build_im_otherinbill_batch_add_sample_body()
        ),
    }


def build_im_otherinbill_finished_goods_batch_update_preset() -> KingdeeCosmicApiPreset:
    body = _im_batch_update_sample_from_add_body(
        build_im_otherinbill_batch_add_sample_body()
    )
    rows = body.get("data") if isinstance(body.get("data"), list) else []
    if rows and isinstance(rows[0], dict):
        rows[0]["billno"] = "LOCAL-FG-SAMPLE"
        rows[0]["comment"] = "快格云成品入库其他入库更新样例"
    return {
        "code_suffix": IM_OTHERINBILL_FINISHED_GOODS_BATCH_UPDATE_PRESET_CODE_SUFFIX,
        "name": "苍穹成品入库其他入库批量更新",
        "description": (
            "MES 成品入库外推专用：其他入库单 batchUpdate，"
            f"请求地址 /v2/im/{BIZ_IM_OTHERINBILL}/batchUpdate。"
            "关联单据 finished_goods_receipt；单据类型须为本环境「生产完工入库」。"
            "头/分录候选键 id 必填。"
        ),
        "path": IM_OTHERINBILL_BATCH_UPDATE_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": body,
    }


def build_im_otherinbill_batch_submit_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": "batch_submit_im_otherinbill",
        "name": "苍穹其他入库单批量提交",
        "description": (
            f"库存管理其他入库单批量提交（开放平台 API 编码 batchSubmit）。"
            f"请求地址 /v2/im/{BIZ_IM_OTHERINBILL}/batchSubmit。"
            "请求体 data 为 Map，含 id/ids/billno；快格云外推保存成功后自动调用。"
            "审核须用 billbatchAudit，勿与 batchAudit 混用。"
        ),
        "path": IM_OTHERINBILL_BATCH_SUBMIT_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": _build_im_batch_operate_sample_body(billno="LOCAL-OI-BILLNO"),
    }


def build_im_otherinbill_billbatch_audit_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": "billbatch_audit_im_otherinbill",
        "name": "苍穹其他入库单批量审核",
        "description": (
            f"库存管理其他入库单批量审核（开放平台 API 编码 billbatchAudit）。"
            f"请求地址 /v2/im/{BIZ_IM_OTHERINBILL}/billbatchAudit。"
            "请求体 data 为 Map，含 id/ids/billno（与 batchSubmit 相同 wrap_operate 形态）。"
            "勿使用 batchAudit（连枝横等环境对该路径返回 HTTP 404）。"
        ),
        "path": IM_OTHERINBILL_BATCH_AUDIT_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": _build_im_batch_operate_sample_body(billno="LOCAL-OI-BILLNO"),
    }


def build_im_otheroutbill_batch_add_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": IM_OTHEROUTBILL_BATCH_ADD_PRESET_CODE_SUFFIX,
        "name": "苍穹其他出库单批量新增",
        "description": (
            f"库存管理其他出库单批量新增（API 编码 batchAdd）。"
            f"请求地址 /v2/im/{BIZ_IM_OTHEROUTBILL}/batchAdd。"
            "请求体 data 为单据数组；头必填含 org_number、billtype_number、biztype_number、"
            "invscheme_number、biztime、billentry；"
            "头必填含领用部门 bizdept_number（表单可标为领用部门；仅写 pickdept_number 会被忽略）、"
            "领用人 pickeroperator_operatornumber（Operator 写键；仅写 *_number 会被忽略）；"
            "领用部门与客户 customer_number 不能同时为空。"
            "明细必填 linetype_number、material_number、unit_number、qty、warehouse_number。"
            "样例中 REPLACE_* 请改为本环境真实编码后联调；billno 可写本地出库单号。"
            "外推保存后自动提交 batchSubmit、审核 billbatchAudit（非 batchAudit）。"
            "生产领料请改用「苍穹生产领料其他出库批量新增」，勿把标准其他出库单据类型用于领料。"
        ),
        "path": IM_OTHEROUTBILL_BATCH_ADD_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": build_im_otheroutbill_batch_add_sample_body(),
    }


def build_im_otheroutbill_production_picking_batch_add_sample_body() -> Dict[str, Any]:
    """生产领料 → 其他出库：路径与 batchAdd 相同，单据类型须为「生产领料」（勿用标准其他出库）。"""
    body = build_im_otheroutbill_batch_add_sample_body()
    rows = body.get("data")
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        rows[0]["billtype_number"] = "REPLACE_BILLTYPE_PRODUCTION_PICKING"
        rows[0]["biztype_number"] = "REPLACE_BIZTYPE_PRODUCTION_PICKING"
        rows[0]["invscheme_number"] = "REPLACE_INVSCHEME_PRODUCTION_PICKING"
        rows[0]["billno"] = "LOCAL-PP-SAMPLE"
        rows[0]["comment"] = "快格云生产领料→苍穹其他出库（单据类型=生产领料）"
    return body


def build_im_otheroutbill_production_picking_batch_add_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": IM_OTHEROUTBILL_PRODUCTION_PICKING_BATCH_ADD_PRESET_CODE_SUFFIX,
        "name": "苍穹生产领料其他出库批量新增",
        "description": (
            "MES 生产领料单外推专用：写入库存管理其他出库单（API 编码 batchAdd），"
            f"请求地址 /v2/im/{BIZ_IM_OTHEROUTBILL}/batchAdd。"
            "单据类型 billtype_number 必须为本环境「生产领料」编码"
            "（勿填标准其他出库单）；biztype_number / invscheme_number 与该单据类型配套。"
            "头/明细必填同其他出库；领用部门 bizdept_number、领用人 pickeroperator_operatornumber。"
            "样例 REPLACE_*_PRODUCTION_PICKING 请改为本账套真实编码后挂到生产领料推送绑定。"
            "保存后仍走同对象 batchSubmit / billbatchAudit。"
            "若标品 batchAdd 落不了领用人，请改绑「【自定义】苍穹生产领料其他出库新增(含领用人)」add3。"
        ),
        "path": IM_OTHEROUTBILL_BATCH_ADD_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": build_im_otheroutbill_production_picking_batch_add_sample_body(),
    }


def build_im_otheroutbill_add3_sample_body() -> Dict[str, Any]:
    """【自定义】add3：单对象 data；领用人走 bizuser_number（工号，如 ID-000081）。"""
    batch = build_im_otheroutbill_batch_add_sample_body()
    rows = batch.get("data")
    row = dict(rows[0]) if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}
    row["bizuser_number"] = "REPLACE_PICKER_EMPNO"
    row["bizuser_name"] = "REPLACE_PICKER_NAME"
    row["pickeroperator_operatornumber"] = "REPLACE_PICKER_EMPNO"
    return {"data": row}


def build_im_otheroutbill_production_picking_add3_sample_body() -> Dict[str, Any]:
    body = build_im_otheroutbill_add3_sample_body()
    data = body.get("data")
    if isinstance(data, dict):
        data = dict(data)
        data["billtype_number"] = "REPLACE_BILLTYPE_PRODUCTION_PICKING"
        data["biztype_number"] = "REPLACE_BIZTYPE_PRODUCTION_PICKING"
        data["invscheme_number"] = "REPLACE_INVSCHEME_PRODUCTION_PICKING"
        data["billno"] = "LOCAL-PP-ADD3"
        data["comment"] = "快格云生产领料→苍穹自定义 add3（含领用人 bizuser）"
        body = {**body, "data": data}
    return body


def build_im_otheroutbill_add3_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": IM_OTHEROUTBILL_ADD3_PRESET_CODE_SUFFIX,
        "name": "【自定义】苍穹其他出库单新增(含领用人)",
        "description": (
            "【自定义】其他出库单保存（API 编码 add3；非标品 batchAdd）。"
            f"请求地址 /{IM_OTHEROUTBILL_ADD3_PATH}。"
            "请求体 data 为单对象 Map（非数组）。"
            "领用人须传 bizuser_number=人员工号（连枝横实测 ID-000081 可提交审核；"
            "登录名 yangzhiwei/lifuyue1、中文姓名均不是工号）。"
            "可选 bizuser_name；bizuser_id 可不传。"
            "保存后仍走标品 batchSubmit / billbatchAudit。"
        ),
        "path": IM_OTHEROUTBILL_ADD3_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": build_im_otheroutbill_add3_sample_body(),
    }


def build_im_otheroutbill_production_picking_add3_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": IM_OTHEROUTBILL_PRODUCTION_PICKING_ADD3_PRESET_CODE_SUFFIX,
        "name": "【自定义】苍穹生产领料其他出库新增(含领用人)",
        "description": (
            "MES 生产领料外推专用自定义保存（API 编码 add3）。"
            f"请求地址 /{IM_OTHEROUTBILL_ADD3_PATH}；data 单对象。"
            "单据类型须为「生产领料」；领用人 bizuser_number=工号（如 ID-000081）。"
            "标品 batchAdd 无法落领用人时改绑本接口。"
            "保存后 batchSubmit / billbatchAudit。"
        ),
        "path": IM_OTHEROUTBILL_ADD3_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": build_im_otheroutbill_production_picking_add3_sample_body(),
    }


def build_im_otheroutbill_batch_submit_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": "batch_submit_im_otheroutbill",
        "name": "苍穹其他出库单批量提交",
        "description": (
            f"库存管理其他出库单批量提交（开放平台 API 编码 batchSubmit）。"
            f"请求地址 /v2/im/{BIZ_IM_OTHEROUTBILL}/batchSubmit。"
            "请求体 data 为 Map，含 id/ids/billno；快格云外推保存成功后自动调用。"
            "须先满足领用人等必填校验；审核须用 billbatchAudit。"
        ),
        "path": IM_OTHEROUTBILL_BATCH_SUBMIT_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": _build_im_batch_operate_sample_body(billno="LOCAL-OO-BILLNO"),
    }


def build_im_otheroutbill_billbatch_audit_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": "billbatch_audit_im_otheroutbill",
        "name": "苍穹其他出库单批量审核",
        "description": (
            f"库存管理其他出库单批量审核（开放平台 API 编码 billbatchAudit）。"
            f"请求地址 /v2/im/{BIZ_IM_OTHEROUTBILL}/billbatchAudit。"
            "请求体 data 为 Map，含 id/ids/billno（与 batchSubmit 相同 wrap_operate 形态）。"
            "勿使用 batchAudit（连枝横等环境对该路径返回 HTTP 404）。"
        ),
        "path": IM_OTHEROUTBILL_BATCH_AUDIT_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": _build_im_batch_operate_sample_body(billno="LOCAL-OO-BILLNO"),
    }


def build_im_surplusbill_batch_add_sample_body() -> Dict[str, Any]:
    """
    盘盈单批量新增最小可编辑样例（开放平台 im_surplusbill/batchAdd）。
    请求体 data 为单据数组；头/明细必填见开放平台参数表。
    """
    return {
        "data": [
            {
                "biztime": "2026-01-01",
                "bookdate": "2026-01-01",
                "org_number": "REPLACE_ORG",
                "billtype_number": "REPLACE_BILLTYPE",
                "biztype_number": "REPLACE_BIZTYPE",
                "invscheme_number": "REPLACE_INVSCHEME",
                "billno": "LOCAL-ST-SURPLUS-SAMPLE",
                "comment": "快格云盘盈出站样例",
                "billentry": [
                    {
                        "material_number": "REPLACE_MATERIAL",
                        "linetype_number": "REPLACE_LINETYPE",
                        "invstatus_number": "REPLACE_INVSTATUS",
                        "invtype_number": "REPLACE_INVTYPE",
                        "ownertype": "bos_org",
                        "keepertype": "bos_org",
                        "owner_number": "REPLACE_ORG",
                        "keeper_number": "REPLACE_ORG",
                        "warehouse_number": "REPLACE_WAREHOUSE",
                        "unit_number": "pcs",
                        "qty": 1,
                        "invgainqty": 1,
                        "invqtyacc": 0,
                    }
                ],
            }
        ]
    }


def build_im_surplusbill_batch_add_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": IM_SURPLUSBILL_BATCH_ADD_PRESET_CODE_SUFFIX,
        "name": "苍穹盘盈单批量新增",
        "description": (
            f"库存管理盘盈单批量新增（API 编码 batchAdd）。"
            f"请求地址 /v2/im/{BIZ_IM_SURPLUSBILL}/batchAdd。"
            "请求体 data 为单据数组；头必填含 biztime、bookdate、billtype_number、biztype_number、"
            "invscheme_number、org_number、billentry；"
            "明细必填 linetype_number、material_number、invstatus_number、invtype_number、"
            "owner_number、keeper_number、ownertype、keepertype、warehouse_number、"
            "qty、invgainqty、invqtyacc。"
            "样例中 REPLACE_* 请改为本环境真实编码后联调；billno 可写本地盘点单号。"
        ),
        "path": IM_SURPLUSBILL_BATCH_ADD_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": build_im_surplusbill_batch_add_sample_body(),
    }


def build_im_deficitbill_batch_add_sample_body() -> Dict[str, Any]:
    """
    盘亏单批量新增最小可编辑样例（开放平台 im_deficitbill/batchAdd）。
    请求体 data 为单据数组；头/明细必填见开放平台参数表。
    """
    return {
        "data": [
            {
                "biztime": "2026-01-01",
                "bookdate": "2026-01-01",
                "org_number": "REPLACE_ORG",
                "billtype_number": "REPLACE_BILLTYPE",
                "biztype_number": "REPLACE_BIZTYPE",
                "invscheme_number": "REPLACE_INVSCHEME",
                "billno": "LOCAL-ST-DEFICIT-SAMPLE",
                "comment": "快格云盘亏出站样例",
                "billentry": [
                    {
                        "material_number": "REPLACE_MATERIAL",
                        "linetype_number": "REPLACE_LINETYPE",
                        "outinvstatus_number": "REPLACE_OUTINVSTATUS",
                        "outinvtype_number": "REPLACE_OUTINVTYPE",
                        "outownertype": "bos_org",
                        "outkeepertype": "bos_org",
                        "outowner_number": "REPLACE_ORG",
                        "outkeeper_number": "REPLACE_ORG",
                        "warehouse_number": "REPLACE_WAREHOUSE",
                        "unit_number": "pcs",
                        "qty": 0,
                        "invlossqty": 1,
                        "invqtyacc": 1,
                    }
                ],
            }
        ]
    }


def build_im_deficitbill_batch_add_preset() -> KingdeeCosmicApiPreset:
    return {
        "code_suffix": IM_DEFICITBILL_BATCH_ADD_PRESET_CODE_SUFFIX,
        "name": "苍穹盘亏单批量新增",
        "description": (
            f"库存管理盘亏单批量新增（API 编码 batchAdd）。"
            f"请求地址 /v2/im/{BIZ_IM_DEFICITBILL}/batchAdd。"
            "请求体 data 为单据数组；头必填含 biztime、bookdate、billtype_number、biztype_number、"
            "invscheme_number、org_number、billentry；"
            "明细必填 linetype_number、material_number、outinvstatus_number、outinvtype_number、"
            "outowner_number、outkeeper_number、outownertype、outkeepertype、warehouse_number、"
            "qty、invlossqty、invqtyacc。"
            "样例中 REPLACE_* 请改为本环境真实编码后联调；billno 可写本地盘点单号。"
        ),
        "path": IM_DEFICITBILL_BATCH_ADD_PATH,
        "method": "POST",
        "sync_direction": "push",
        "request_body": build_im_deficitbill_batch_add_sample_body(),
    }


def list_kingdee_cosmic_api_presets() -> List[KingdeeCosmicApiPreset]:
    """
    入站优先：主数据与采购订单查询。
    已精简：去掉占位符通用模板、令牌检测/撤回、文档演示接口（生产极少用）。
    """
    return [
        {
            "code_suffix": "oauth_get_token",
            "name": "苍穹获取access_token",
            "description": (
                "增强型 Token 联调接口，路径固定。"
                "日常业务调用无需单独测本条，连接器「测试连接」与接口测试会自动获取 token。"
            ),
            "path": OAUTH_GET_TOKEN_PATH,
            "method": "POST",
            "request_body": build_get_token_preset_body(),
        },
        build_material_batch_query_preset(),
        build_measureunits_batch_query_preset(),
        build_material_group_batch_query_preset(),
        build_material_group_goods_class_preset(),
        build_supplier_query_preset(),
        _basedata_batch_query_preset(
            code_suffix="query_customer",
            name="苍穹查询客户",
            biz_object=BIZ_BD_CUSTOMER,
            usage="客户",
        ),
        build_im_purinbill_add_preset(),
        build_im_purinbill_add2_preset(),
        build_im_purinbill_batch_update_preset(),
        build_im_purinbill_batch_unaudit_preset(),
        build_im_purinbill_batch_unsubmit_preset(),
        build_im_purinbill_batch_delete_preset(),
        build_im_saloutbill_batch_add_preset(),
        build_im_saloutbill_batch_update_preset(),
        build_im_saloutbill_batch_submit_preset(),
        build_im_saloutbill_batch_audit_preset(),
        build_im_saloutbill_batch_unaudit_preset(),
        build_im_saloutbill_batch_unsubmit_preset(),
        build_im_saloutbill_batch_delete_preset(),
        build_im_otheroutbill_batch_add_preset(),
        build_im_otheroutbill_batch_update_preset(),
        build_im_otheroutbill_production_picking_batch_add_preset(),
        build_im_otheroutbill_production_picking_batch_update_preset(),
        build_im_otheroutbill_add3_preset(),
        build_im_otheroutbill_production_picking_add3_preset(),
        build_im_otheroutbill_batch_submit_preset(),
        build_im_otheroutbill_billbatch_audit_preset(),
        build_im_otheroutbill_batch_unaudit_preset(),
        build_im_otheroutbill_batch_unsubmit_preset(),
        build_im_otheroutbill_batch_delete_preset(),
        build_im_otheroutbill_production_picking_batch_unaudit_preset(),
        build_im_otheroutbill_production_picking_batch_unsubmit_preset(),
        build_im_otheroutbill_production_picking_batch_delete_preset(),
        build_im_otherinbill_batch_add_preset(),
        build_im_otherinbill_batch_update_preset(),
        build_im_otherinbill_finished_goods_batch_add_preset(),
        build_im_otherinbill_finished_goods_batch_update_preset(),
        build_im_otherinbill_batch_submit_preset(),
        build_im_otherinbill_billbatch_audit_preset(),
        build_im_otherinbill_batch_unaudit_preset(),
        build_im_otherinbill_batch_unsubmit_preset(),
        build_im_otherinbill_batch_delete_preset(),
        build_im_otherinbill_finished_goods_batch_unaudit_preset(),
        build_im_otherinbill_finished_goods_batch_unsubmit_preset(),
        build_im_otherinbill_finished_goods_batch_delete_preset(),
        build_im_surplusbill_batch_add_preset(),
        build_im_deficitbill_batch_add_preset(),
        build_inventory_balance_query_preset(),
        build_inventory_detail_query_preset(),
        build_warehouse_get_list_preset(),
        {
            "code_suffix": "query_purchase_order",
            "name": "苍穹查询采购订单",
            "description": (
                f"业务对象 {BIZ_PM_PURORDERBILL} 分页查询（含分录字段时返回平铺行）。"
                f"默认 filter：{PURORDER_INBOUND_FILTER}（已审核）。"
                "select 含供应商与行物料、数量、单位；字段名请按本环境单据模型核对。"
            ),
            "path": _sys_query_path(BIZ_PM_PURORDERBILL),
            "method": "POST",
            "request_params": build_sys_query_params(
                select=(
                    "id,billno,billdate,supplier.number,supplier.name,"
                    "billentry.id,billentry.material.number,billentry.material.name,"
                    "billentry.qty,billentry.unit.number,billstatus,closestatus"
                ),
                filter_expr=PURORDER_INBOUND_FILTER,
                orderby="billdate desc",
                page_size=200,
            ),
            "request_body": {},
        },
    ]
