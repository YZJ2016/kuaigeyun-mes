"""付款申请：明细行税率与头表汇总同步。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable


def payment_application_line_tax_percent(raw: Any) -> Decimal:
    return Decimal(str(raw or 0)).quantize(Decimal("0.01"))


def sync_header_tax_rate_from_lines(items: Iterable[Any]) -> Decimal:
    """明细税率一致且非零时写回头表，多税率时头表为 0。"""
    rates: set[Decimal] = set()
    for item in items:
        if isinstance(item, dict):
            raw = item.get("tax_rate")
        else:
            raw = getattr(item, "tax_rate", None)
        pct = payment_application_line_tax_percent(raw)
        if pct > 0:
            rates.add(pct)
    if len(rates) == 1:
        return rates.pop()
    return Decimal("0")