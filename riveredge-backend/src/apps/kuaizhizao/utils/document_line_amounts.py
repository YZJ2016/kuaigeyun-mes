"""单据明细行价税拆分（与前端 documentLineAmounts.calcDocumentLineAmounts 同源，整数金额单位）。"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

PriceType = Literal["tax_inclusive", "tax_exclusive"]


def _amount_scale(amount_places: int) -> int:
    places = max(0, min(6, int(amount_places)))
    return 10**places


def calc_document_line_amounts(
    qty: Decimal | int | float | str,
    unit_price: Decimal | int | float | str,
    tax_rate_percent: Decimal | int | float | str,
    price_type: PriceType | str = "tax_exclusive",
    amount_places: int = 2,
) -> tuple[Decimal, Decimal, Decimal]:
    """返回 (excl, tax, incl)。"""
    scale = _amount_scale(amount_places)
    factor = Decimal(scale)
    q = Decimal(str(qty or 0))
    unit = Decimal(str(unit_price or 0))
    rate = Decimal(str(tax_rate_percent or 0))
    pt = price_type if price_type in ("tax_inclusive", "tax_exclusive") else "tax_exclusive"

    if pt == "tax_inclusive":
        incl_units = int((q * unit * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        divisor = Decimal("1") + rate / Decimal("100")
        excl_units = int(
            (Decimal(incl_units) / divisor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        tax_units = incl_units - excl_units
    else:
        excl_units = int((q * unit * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        tax_units = int(
            (Decimal(excl_units) * rate / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        incl_units = excl_units + tax_units

    return (
        Decimal(excl_units) / factor,
        Decimal(tax_units) / factor,
        Decimal(incl_units) / factor,
    )


def _money_triplet(excl_units: int, tax_units: int, incl_units: int, scale: int) -> tuple[Decimal, Decimal, Decimal]:
    factor = Decimal(scale)
    return (
        Decimal(excl_units) / factor,
        Decimal(tax_units) / factor,
        Decimal(incl_units) / factor,
    )


def calc_document_amounts_from_excl_total(
    excl_total: Decimal | int | float | str,
    tax_rate_percent: Decimal | int | float | str,
    amount_places: int = 2,
) -> tuple[Decimal, Decimal, Decimal]:
    """未税金额为真源，正算税额与价税合计。"""
    scale = _amount_scale(amount_places)
    factor = Decimal(scale)
    excl_units = int((Decimal(str(excl_total or 0)) * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    rate = Decimal(str(tax_rate_percent or 0))
    tax_units = int(
        (Decimal(excl_units) * rate / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    return _money_triplet(excl_units, tax_units, excl_units + tax_units, scale)


def calc_document_amounts_from_incl_total(
    incl_total: Decimal | int | float | str,
    tax_rate_percent: Decimal | int | float | str,
    amount_places: int = 2,
) -> tuple[Decimal, Decimal, Decimal]:
    """价税合计为真源，拆未税与税额。"""
    scale = _amount_scale(amount_places)
    factor = Decimal(scale)
    incl_units = int((Decimal(str(incl_total or 0)) * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    rate = Decimal(str(tax_rate_percent or 0))
    divisor = Decimal("1") + rate / Decimal("100")
    excl_units = (
        int((Decimal(incl_units) / divisor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if divisor > 0
        else incl_units
    )
    return _money_triplet(excl_units, incl_units - excl_units, incl_units, scale)
