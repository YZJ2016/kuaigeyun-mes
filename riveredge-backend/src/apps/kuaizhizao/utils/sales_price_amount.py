"""销售行金额拆分。计算只走 document_line_amounts。"""

from __future__ import annotations

from decimal import Decimal

from apps.kuaizhizao.constants.price_type import normalize_price_type
from apps.kuaizhizao.utils.document_line_amounts import calc_document_line_amounts


def calc_sales_line_amounts(
    qty: Decimal,
    unit_price: Decimal,
    tax_rate_percent: Decimal,
    price_type: str | None,
    amount_places: int = 2,
) -> tuple[Decimal, Decimal, Decimal]:
    """返回 (不含税金额, 税额, 价税合计)。单价按价类解释，不先压成 2 位。"""
    return calc_document_line_amounts(
        qty or Decimal("0"),
        unit_price or Decimal("0"),
        tax_rate_percent if tax_rate_percent is not None else Decimal("0"),
        normalize_price_type(price_type),
        amount_places,
    )
