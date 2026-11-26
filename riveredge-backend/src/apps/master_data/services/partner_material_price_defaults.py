"""物料 defaults 售/采单价回落（含阶梯），供 PartnerMaterialPriceResolver 使用。"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Literal, Optional

from apps.master_data.services.partner_price_tier_utils import match_tier_unit_price

Side = Literal["purchase", "sales"]

# 与 material_market_price_service.convert_unit_price / 前端 UNIT_PRICE_CONVERT_PLACES 对齐。
# 禁止压成 4 位：含税 800@13% → 707.9646 → 乘回 799.999998。
_UNIT_PRICE_CONVERT_QUANT = Decimal("0.000001")


def material_default_tax_rate(defaults: Dict[str, Any]) -> Decimal:
    for key in ("tax_rate", "taxRate", "default_tax_rate", "defaultTaxRate"):
        raw = defaults.get(key)
        if raw is not None and str(raw).strip() != "":
            return Decimal(str(raw))
    sales = defaults.get("sales") if isinstance(defaults.get("sales"), dict) else {}
    for key in ("tax_rate", "taxRate"):
        raw = sales.get(key)
        if raw is not None:
            return Decimal(str(raw))
    return Decimal("0")


def normalize_stored_unit_price_to_exclusive(
    unit_price: Decimal,
    tax_rate: Decimal,
    price_type: Optional[str],
) -> Decimal:
    """价本/物料默认/成交价统一：询价出口为未税单价（中间精度 6 位，可与含税录入往返）。"""
    pt = str(price_type or "tax_inclusive").strip() or "tax_inclusive"
    price = Decimal(str(unit_price or 0))
    if pt == "tax_exclusive":
        return price
    if tax_rate <= 0:
        # 含税但无税率时无法剥离；原样返回，调用方不得再用另一税率乘回
        return price
    rate = tax_rate / Decimal("100") if tax_rate > Decimal("1") else tax_rate
    factor = Decimal("1") + rate
    if factor <= 0:
        return price
    return (price / factor).quantize(_UNIT_PRICE_CONVERT_QUANT, rounding=ROUND_HALF_UP)

def convert_purchase_default_to_exclusive(
    price: Decimal,
    container: Dict[str, Any],
    tax_rate: Decimal,
) -> Decimal:
    pt = str(
        container.get("defaultPurchasePriceType")
        or container.get("default_purchase_price_type")
        or "tax_inclusive"
    ).strip()
    return normalize_stored_unit_price_to_exclusive(price, tax_rate, pt)


def convert_sale_default_to_exclusive(
    price: Decimal,
    container: Dict[str, Any],
    tax_rate: Decimal,
) -> Decimal:
    pt = str(
        container.get("defaultSalePriceType")
        or container.get("default_sale_price_type")
        or "tax_inclusive"
    ).strip()
    return normalize_stored_unit_price_to_exclusive(price, tax_rate, pt)


def resolve_material_default_unit_price(
    defaults_raw: Any,
    side: Side,
    quantity: Optional[Decimal],
) -> Optional[Decimal]:
    defaults = defaults_raw if isinstance(defaults_raw, dict) else {}
    tax_rate = material_default_tax_rate(defaults)

    if side == "purchase":
        method = str(
            defaults.get("purchasePriceMethod")
            or defaults.get("purchase_price_method")
            or "fixed"
        ).strip()
        purchase = defaults.get("purchase") if isinstance(defaults.get("purchase"), dict) else {}
        tier_raw = purchase.get("tier_prices") or purchase.get("tierPrices") or defaults.get(
            "purchaseTierPrices"
        )
        if method == "tier" and tier_raw and quantity is not None:
            tier_price = match_tier_unit_price(tier_raw, quantity)
            if tier_price is not None:
                return convert_purchase_default_to_exclusive(
                    tier_price, {**defaults, **purchase}, tax_rate
                )
        for key in (
            "defaultPurchasePrice",
            "default_purchase_price",
            "standard_price",
            "purchase_price",
        ):
            raw = purchase.get(key) if key in purchase else defaults.get(key)
            if raw is not None and str(raw).strip() != "":
                price = Decimal(str(raw))
                if price > 0:
                    return convert_purchase_default_to_exclusive(
                        price, {**defaults, **purchase}, tax_rate
                    )
        return None

    method = str(defaults.get("salePriceMethod") or defaults.get("sale_price_method") or "fixed").strip()
    sales = defaults.get("sales") if isinstance(defaults.get("sales"), dict) else {}
    sale_container = {**defaults, **sales}
    if method == "tier" and quantity is not None:
        tier_raw = sales.get("tier_prices") or sales.get("tierPrices")
        tier_price = match_tier_unit_price(tier_raw, quantity)
        if tier_price is not None:
            return convert_sale_default_to_exclusive(tier_price, sale_container, tax_rate)
    for key in ("defaultSalePrice", "default_sale_price", "standard_price"):
        raw = sales.get(key) if key in sales else defaults.get(key)
        if raw is not None and str(raw).strip() != "":
            price = Decimal(str(raw))
            if price > 0:
                return convert_sale_default_to_exclusive(price, sale_container, tax_rate)
    return None
