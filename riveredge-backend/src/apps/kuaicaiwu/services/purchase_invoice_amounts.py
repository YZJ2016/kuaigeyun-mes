"""采购发票：票面金额 vs 源单占用金额（含税）。"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

_TWOPLACES = Decimal("0.01")


def _q(value: Any) -> Decimal:
    return Decimal(str(value if value is not None else 0)).quantize(
        _TWOPLACES, rounding=ROUND_HALF_UP
    )


def purchase_invoice_face_total(invoice: Any) -> Decimal:
    """票面价税合计 I（用于税务、生应付）。"""
    return _q(getattr(invoice, "total_amount", None))


def purchase_invoice_discount(invoice: Any) -> Decimal:
    """优惠金额 D（可正可负，含税口径）。"""
    return _q(getattr(invoice, "discount_amount", None))


def purchase_invoice_occupancy_amount(invoice: Any) -> Decimal:
    """源单已开票占用 W = I + D。"""
    return _q(purchase_invoice_face_total(invoice) + purchase_invoice_discount(invoice))
