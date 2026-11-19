"""单据头表金额/数量：明细派生字段契约（禁止 API 客户端直写）。"""

from __future__ import annotations

# 采购：未税 + 税额 + 价税 + 合计数量（见 purchase_settlement）
from apps.kuaicaiwu.services.purchase_settlement import (
    PURCHASE_ORDER_COMPUTED_HEADER_FIELDS,
    PURCHASE_RECEIPT_COMPUTED_HEADER_FIELDS,
)

# 销售：行价税合计汇总后的头表数量/金额（整单优惠 discount_amount 仍由用户录入）
SALES_GOODS_DERIVED_HEADER_FIELDS = frozenset({"total_quantity", "total_amount"})

__all__ = [
    "PURCHASE_ORDER_COMPUTED_HEADER_FIELDS",
    "PURCHASE_RECEIPT_COMPUTED_HEADER_FIELDS",
    "SALES_GOODS_DERIVED_HEADER_FIELDS",
]
