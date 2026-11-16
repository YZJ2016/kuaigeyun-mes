"""物料 defaults 售/采单价回落（含阶梯），供 PartnerMaterialPriceResolver 使用。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Literal, Optional

from apps.master_data.services.partner_price_tier_utils import match_tier_unit_price

Side = Literal["purchase", "sales"]


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
    if pt == "tax_exclusive":
        return price
    if tax_rate <= 0:
        return price
    rate = tax_rate / Decimal("100") if tax_rate > Decimal("1") else tax_rate
    factor = Decimal("1") + rate
    if factor <= 0:
        return price
    return (price / factor).quantize(Decimal("0.0001"))


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
    if method == "tier" and quantity is not None:
        tier_raw = sales.get("tier_prices") or sales.get("tierPrices")
        tier_price = match_tier_unit_price(tier_raw, quantity)
        if tier_price is not None:
            return tier_price
    for key in ("defaultSalePrice", "default_sale_price", "standard_price"):
        raw = sales.get(key) if key in sales else defaults.get(key)
        if raw is not None and str(raw).strip() != "":
            price = Decimal(str(raw))
            if price > 0:
                return price
    return None
