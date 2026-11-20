"""台账双计量 API 字段（主/副单位与主/副数量）。"""

from typing import Any, Optional

from pydantic import Field

from apps.kuaizhizao.utils.inventory_posting_utils import InventoryPostingQuantities
from apps.kuaizhizao.utils.ledger_dual_quantity_utils import (
    apply_ledger_fields_to_inventory_row,
    ledger_quantities_from_posting,
    resolve_ledger_units,
)
from core.schemas.base import BaseSchema


class LedgerDualQuantityReadMixin(BaseSchema):
    """即时库存/余额等读模型。"""

    primary_unit: Optional[str] = Field(None, description="主单位（原库存单位）")
    secondary_unit: Optional[str] = Field(
        None, description="副单位（物料配置的第一个辅助单位；无固定换算时仅回显名称）"
    )
    primary_quantity: float = Field(0, description="主数量（库存单位量）")
    secondary_quantity: float = Field(0, description="副数量（辅助单位量）")


class LedgerDualQuantityConfirmMixin(BaseSchema):
    """出入库确认时可改实收/实发台账数量。"""

    primary_quantity: Optional[float] = Field(
        None, gt=0, description="确认主数量（台账库存单位）"
    )
    secondary_quantity: Optional[float] = Field(
        None, ge=0, description="确认副数量（辅助单位）；有固定辅助单位时必填"
    )


def inventory_row_to_ledger_api(row: dict[str, Any], material: Any = None) -> dict[str, Any]:
    """dict 行 → 仅含 primary/secondary 对外字段（就地转换副本）。"""
    out = dict(row)
    return apply_ledger_fields_to_inventory_row(out, material)


def posting_to_ledger_dict(posting: InventoryPostingQuantities, material: Any) -> dict[str, Any]:
    units = resolve_ledger_units(material)
    body = ledger_quantities_from_posting(posting, material)
    return body
