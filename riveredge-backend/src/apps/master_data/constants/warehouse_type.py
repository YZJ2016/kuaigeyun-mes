"""仓库类型常量（与 Warehouse.warehouse_type / 前端 WAREHOUSE_TYPE_OPTIONS 对齐）。"""

from __future__ import annotations

from typing import FrozenSet, Optional

WAREHOUSE_TYPE_NORMAL = "normal"
WAREHOUSE_TYPE_LINE_SIDE = "line_side"
WAREHOUSE_TYPE_WIP = "wip"
WAREHOUSE_TYPE_OUTSOURCING = "outsourcing"
WAREHOUSE_TYPE_CONSIGNMENT = "consignment"
WAREHOUSE_TYPE_VMI = "vmi"
WAREHOUSE_TYPE_DEFECT = "defect"
WAREHOUSE_TYPE_SCRAP = "scrap"
WAREHOUSE_TYPE_QUARANTINE = "quarantine"
WAREHOUSE_TYPE_GIFT = "gift"

WAREHOUSE_TYPE_CHOICES = (
    WAREHOUSE_TYPE_NORMAL,
    WAREHOUSE_TYPE_LINE_SIDE,
    WAREHOUSE_TYPE_WIP,
    WAREHOUSE_TYPE_OUTSOURCING,
    WAREHOUSE_TYPE_CONSIGNMENT,
    WAREHOUSE_TYPE_VMI,
    WAREHOUSE_TYPE_DEFECT,
    WAREHOUSE_TYPE_SCRAP,
    WAREHOUSE_TYPE_QUARANTINE,
    WAREHOUSE_TYPE_GIFT,
)

# 赠品仓等：出入库只记数量，不参与移动加权/出库成本/库存金额
QUANTITY_ONLY_WAREHOUSE_TYPES: FrozenSet[str] = frozenset({WAREHOUSE_TYPE_GIFT})


def is_quantity_only_warehouse_type(warehouse_type: Optional[str]) -> bool:
    if not warehouse_type:
        return False
    return str(warehouse_type).strip().lower() in QUANTITY_ONLY_WAREHOUSE_TYPES
