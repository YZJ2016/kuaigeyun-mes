"""委外结算共享常量与数量口径。"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.kuaizhizao.models.outsource_work_order import OutsourceMaterialReceipt

LINE_TYPE_PROCESSING = "processing"
LINE_TYPE_MATERIAL_DEDUCTION = "material_deduction"
LINE_TYPE_RETURN_CREDIT = "return_credit"

SETTLEMENT_KIND_NORMAL = "normal"
SETTLEMENT_KIND_CREDIT = "credit"

SOURCE_DOC_OUTSOURCE_PRODUCT_RETURN = "outsource_product_return"


def receipt_base_qty(receipt: OutsourceMaterialReceipt) -> Decimal:
    """可结算/可退货基数：合格数量优先，否则收货数量。"""
    qualified = Decimal(str(receipt.qualified_quantity or 0))
    if qualified > 0:
        return qualified
    return Decimal(str(receipt.quantity or 0))
