"""
附属只读 GET 白名单（宿主:read OR 模块:read）。

新增 OR 须在此登记并在 PR 说明 reason；禁止在 *_route_access.py 内联多码 return。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from core.config.permission_contract import build_permission_code

_MASTER_DATA_APP = "master-data"

# GET 物料头下 BOM 版本列表（无更深子路径）
_BOM_BY_MATERIAL_LIST_RE = re.compile(r"/materials/bom/material/\d+/?$", re.IGNORECASE)

# 单位目录 / 换算只读（物料编辑下拉）
_UNIT_CATALOG_PATH_RE = re.compile(
    r"/materials/(?:units|unit-conversions)(?:/|$)",
    re.IGNORECASE,
)

# 物料主档列表检索（单据行选料 / 移动端关键字查询，不含子资源）
_MATERIAL_LIST_SEARCH_RE = re.compile(r"/materials/?(?:\?|$)", re.IGNORECASE)


@dataclass(frozen=True)
class AffiliateReadEntry:
    id: str
    app_code: str
    method: str
    path_pattern: re.Pattern[str]
    permission_codes: tuple[str, ...]
    reason: str


AFFILIATE_READ_ENTRIES: tuple[AffiliateReadEntry, ...] = (
    AffiliateReadEntry(
        id="master_data_bom_by_material_list",
        app_code=_MASTER_DATA_APP,
        method="GET",
        path_pattern=_BOM_BY_MATERIAL_LIST_RE,
        permission_codes=(
            build_permission_code(_MASTER_DATA_APP, "material", "read"),
            build_permission_code(_MASTER_DATA_APP, "process:engineering-bom", "read"),
            build_permission_code("kuaizhizao", "work-order", "read"),
            build_permission_code("kuaizhizao", "work-order", "create"),
            build_permission_code("kuaizhizao", "work-order", "update"),
        ),
        reason="物料编辑与工单选成品时回显 BOM 版本列表",
    ),
    AffiliateReadEntry(
        id="master_data_unit_catalog_read",
        app_code=_MASTER_DATA_APP,
        method="GET",
        path_pattern=_UNIT_CATALOG_PATH_RE,
        permission_codes=(
            build_permission_code(_MASTER_DATA_APP, "material-unit", "read"),
            build_permission_code(_MASTER_DATA_APP, "material", "read"),
        ),
        reason="物料表单单位下拉与单位目录只读",
    ),
    AffiliateReadEntry(
        id="master_data_material_list_document_line_pick",
        app_code=_MASTER_DATA_APP,
        method="GET",
        path_pattern=_MATERIAL_LIST_SEARCH_RE,
        permission_codes=(
            build_permission_code(_MASTER_DATA_APP, "material", "read"),
            build_permission_code(_MASTER_DATA_APP, "material", "display"),
            build_permission_code("kuaizhizao", "purchase-requisition", "read"),
            build_permission_code("kuaizhizao", "purchase-requisition", "create"),
            build_permission_code("kuaizhizao", "purchase-order", "read"),
            build_permission_code("kuaizhizao", "purchase-inquiry", "read"),
            build_permission_code("kuaizhizao", "inbound", "read"),
            build_permission_code("kuaizhizao", "outbound", "read"),
            build_permission_code("kuaizhizao", "other-inbound", "read"),
            build_permission_code("kuaizhizao", "other-outbound", "read"),
            build_permission_code("kuaizhizao", "quotation", "read"),
            build_permission_code("kuaizhizao", "sales-order", "read"),
            build_permission_code("kuaizhizao", "delivery-notice", "read"),
            build_permission_code(
                "kuaizhizao",
                "warehouse-management-inventory-transfer",
                "read",
            ),
            build_permission_code("kuaizhizao", "work-order", "read"),
            build_permission_code(
                "kuaizhizao",
                "quality-management-nonconforming-ledger",
                "read",
            ),
        ),
        reason="单据行选料与移动端物料检索：宿主单据读或物料展示即可",
    ),
    # 出入库选仓走 warehouse 引用下拉（:read/:display）；库位却直打
    # /storage-locations，缺 storage-location:read 时生产表现为「仓库有、库位暂无数据」。
    AffiliateReadEntry(
        id="master_data_storage_location_list_with_warehouse_read",
        app_code=_MASTER_DATA_APP,
        method="GET",
        path_pattern=re.compile(r"/storage-locations(?:/|$)", re.IGNORECASE),
        permission_codes=(
            build_permission_code(_MASTER_DATA_APP, "warehouse:storage-location", "read"),
            build_permission_code(_MASTER_DATA_APP, "warehouse:warehouse", "read"),
            build_permission_code(_MASTER_DATA_APP, "warehouse:warehouse", "display"),
        ),
        reason="有仓库读/展示权限即可拉库位下拉（出入库选库位）",
    ),
    AffiliateReadEntry(
        id="master_data_storage_area_list_with_warehouse_read",
        app_code=_MASTER_DATA_APP,
        method="GET",
        path_pattern=re.compile(r"/storage-areas(?:/|$)", re.IGNORECASE),
        permission_codes=(
            build_permission_code(_MASTER_DATA_APP, "warehouse:storage-area", "read"),
            build_permission_code(_MASTER_DATA_APP, "warehouse:warehouse", "read"),
            build_permission_code(_MASTER_DATA_APP, "warehouse:warehouse", "display"),
        ),
        reason="按仓库过滤库位时需库区列表，与仓库读权限对齐",
    ),
    AffiliateReadEntry(
        id="kuaizhizao_demands_work_order_pull_lines",
        app_code="kuaizhizao",
        method="GET",
        path_pattern=re.compile(r"/demands/work-order-pull-lines(?:/|$)", re.IGNORECASE),
        permission_codes=(
            build_permission_code(
                "kuaizhizao", "plan-management-demand-management", "read"
            ),
            build_permission_code(
                "kuaizhizao", "plan-management-demand-management", "display"
            ),
            build_permission_code("kuaizhizao", "work-order", "create"),
            build_permission_code("kuaizhizao", "work-order", "read"),
        ),
        reason="工单从计划生产取开口行：工单新建/查看或计划生产读/展示",
    ),
    AffiliateReadEntry(
        id="kuaizhizao_demand_computations_work_order_pull",
        app_code="kuaizhizao",
        method="GET",
        path_pattern=re.compile(
            r"/demand-computations/(?:work-order-pull-computations|"
            r"\d+/push-preview|"
            r"\d+/push-options)(?:/|$)",
            re.IGNORECASE,
        ),
        permission_codes=(
            build_permission_code(
                "kuaizhizao", "plan-management-demand-computation", "read"
            ),
            build_permission_code(
                "kuaizhizao", "plan-management-demand-computation", "display"
            ),
            build_permission_code("kuaizhizao", "work-order", "create"),
            build_permission_code("kuaizhizao", "work-order", "read"),
        ),
        reason="工单从需求计算取单及预览：工单新建/查看或需求计算读/展示",
    ),
    AffiliateReadEntry(
        id="kuaizhizao_sales_orders_work_order_pull_lines",
        app_code="kuaizhizao",
        method="GET",
        path_pattern=re.compile(r"/sales-orders/work-order-pull-lines(?:/|$)", re.IGNORECASE),
        permission_codes=(
            build_permission_code("kuaizhizao", "sales-order", "read"),
            build_permission_code("kuaizhizao", "sales-order", "display"),
            build_permission_code("kuaizhizao", "work-order", "create"),
            build_permission_code("kuaizhizao", "work-order", "read"),
        ),
        reason="工单从销售订单取开口行：工单新建/查看或销售订单读/展示",
    ),
    AffiliateReadEntry(
        id="kuaizhizao_sales_orders_purchase_requisition_pull",
        app_code="kuaizhizao",
        method="GET",
        path_pattern=re.compile(
            r"/sales-orders/purchase-requisition-pull-(?:lines|orders)(?:/|$)",
            re.IGNORECASE,
        ),
        permission_codes=(
            build_permission_code("kuaizhizao", "sales-order", "read"),
            build_permission_code("kuaizhizao", "sales-order", "display"),
            build_permission_code("kuaizhizao", "purchase-requisition", "create"),
            build_permission_code("kuaizhizao", "purchase-requisition", "read"),
        ),
        reason="采购申请从销售订单取单：申请新建/查看或销售订单读/展示",
    ),
    AffiliateReadEntry(
        id="kuaizhizao_purchase_requisitions_sales_order_pull_lines",
        app_code="kuaizhizao",
        method="GET",
        path_pattern=re.compile(
            r"/purchase-requisitions/(?:pull/)?sales-order-pull-lines(?:/|$)",
            re.IGNORECASE,
        ),
        permission_codes=(
            build_permission_code("kuaizhizao", "sales-order", "read"),
            build_permission_code("kuaizhizao", "sales-order", "display"),
            build_permission_code("kuaizhizao", "purchase-requisition", "create"),
            build_permission_code("kuaizhizao", "purchase-requisition", "read"),
        ),
        reason="采购申请从销售订单取开口行：申请新建/查看或销售订单读/展示",
    ),
    AffiliateReadEntry(
        id="kuaizhizao_purchase_requisitions_sales_order_pull_orders",
        app_code="kuaizhizao",
        method="GET",
        path_pattern=re.compile(
            r"/purchase-requisitions/(?:pull/)?sales-order-pull-orders(?:/|$)",
            re.IGNORECASE,
        ),
        permission_codes=(
            build_permission_code("kuaizhizao", "sales-order", "read"),
            build_permission_code("kuaizhizao", "sales-order", "display"),
            build_permission_code("kuaizhizao", "purchase-requisition", "create"),
            build_permission_code("kuaizhizao", "purchase-requisition", "read"),
        ),
        reason="采购申请从销售订单取单来源筛选：申请新建/查看或销售订单读/展示",
    ),
    AffiliateReadEntry(
        id="kuaizhizao_document_line_material_attachment_sources",
        app_code="kuaizhizao",
        method="GET",
        path_pattern=re.compile(
            r"/document-relations/material-line-attachment-sources(?:/|$)",
            re.IGNORECASE,
        ),
        permission_codes=(
            build_permission_code("kuaizhizao", "purchase-requisition", "read"),
            build_permission_code("kuaizhizao", "purchase-order", "read"),
            build_permission_code("kuaizhizao", "inbound", "read"),
            build_permission_code("kuaizhizao", "quotation", "read"),
            build_permission_code("kuaizhizao", "sales-order", "read"),
            build_permission_code("kuaizhizao", "outbound", "read"),
            build_permission_code(_MASTER_DATA_APP, "material", "read"),
            build_permission_code(_MASTER_DATA_APP, "material", "display"),
            build_permission_code(_MASTER_DATA_APP, "process:drawing", "read"),
        ),
        reason="六类单据行「物料附件」弹窗：宿主单据读或物料/图纸读",
    ),
)


def resolve_affiliate_read_codes(
    app_code: str,
    method: str,
    path: str,
) -> list[str] | None:
    """匹配白名单则返回 OR 权限码列表；否则 None。"""
    app = (app_code or "").strip().lower()
    m = (method or "").upper()
    p = path or ""
    for entry in AFFILIATE_READ_ENTRIES:
        if entry.app_code != app:
            continue
        if entry.method != m:
            continue
        if entry.path_pattern.search(p):
            return list(entry.permission_codes)
    return None


def permission_codes_for_entry_id(entry_id: str) -> tuple[str, ...]:
    for entry in AFFILIATE_READ_ENTRIES:
        if entry.id == entry_id:
            return entry.permission_codes
    raise KeyError(f"Unknown affiliate read entry: {entry_id!r}")


__all__ = [
    "AffiliateReadEntry",
    "AFFILIATE_READ_ENTRIES",
    "resolve_affiliate_read_codes",
    "permission_codes_for_entry_id",
]
