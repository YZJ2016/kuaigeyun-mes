"""采购下推共用的税率与小数位。金额只调用 document_line_amounts 计算一次。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

DEFAULT_PURCHASE_TAX_RATE_PERCENT = Decimal("13")


def coalesce_purchase_tax_percent(
    *candidates: Any,
    default: Decimal = DEFAULT_PURCHASE_TAX_RATE_PERCENT,
) -> Decimal:
    """取第一个大于 0 的税率（小数或百分比均可）。都没有时用默认 13%。"""
    from apps.kuaicaiwu.services.purchase_settlement import (
        normalize_po_tax_rate_to_percent,
    )

    for raw in candidates:
        if raw is None or raw == "":
            continue
        pct = normalize_po_tax_rate_to_percent(raw)
        if pct > 0:
            return pct
    return default


async def load_price_amount_places(tenant_id: int) -> tuple[int, int]:
    from infra.services.business_config_service import BusinessConfigService

    svc = BusinessConfigService()
    price_places = await svc.get_price_decimal_places(tenant_id)
    amount_places = await svc.get_amount_decimal_places(tenant_id)
    return price_places, amount_places


def split_purchase_entered_line(
    qty: Any,
    unit_price: Any,
    tax_percent: Any,
    price_type: str | None,
    *,
    price_places: int,
    amount_places: int,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """按录入单价计算一次。返回 (录入单价, 未税, 税额, 价税合计)。

    单价保持录入值，不把未税反除数量后再算一遍。
    """
    from apps.kuaizhizao.constants.price_type import (
        DEFAULT_PURCHASE_PRICE_TYPE,
        normalize_price_type,
    )
    from apps.kuaizhizao.utils.document_line_amounts import calc_document_line_amounts
    from core.utils.price_precision import quantize_business_price

    unit = quantize_business_price(unit_price or 0, price_places)
    pt = normalize_price_type(price_type, fallback=DEFAULT_PURCHASE_PRICE_TYPE)
    excl, tax, incl = calc_document_line_amounts(
        qty, unit, tax_percent or 0, pt, amount_places
    )
    return unit, excl, tax, incl
