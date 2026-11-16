"""物料 defaults 中阶梯价校验与规范化（与价本 tier_prices 同结构）。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional

from apps.master_data.services.partner_price_tier_utils import normalize_tier_prices_for_storage
from infra.exceptions.exceptions import ValidationError


def normalize_and_validate_material_defaults(defaults: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if defaults is None:
        return None
    if not isinstance(defaults, dict):
        raise ValidationError("物料 defaults 须为对象")

    out = deepcopy(defaults)
    sale_method = str(out.get("salePriceMethod") or out.get("sale_price_method") or "fixed").strip()
    if sale_method not in ("fixed", "market", "tier"):
        sale_method = "fixed"
    out["salePriceMethod"] = sale_method

    purchase_method = str(
        out.get("purchasePriceMethod") or out.get("purchase_price_method") or "fixed"
    ).strip()
    if purchase_method not in ("fixed", "tier"):
        purchase_method = "fixed"
    out["purchasePriceMethod"] = purchase_method

    sales = out.get("sales") if isinstance(out.get("sales"), dict) else {}
    purchase = out.get("purchase") if isinstance(out.get("purchase"), dict) else {}

    if sale_method == "tier":
        raw_tiers = (
            out.pop("saleTierPrices", None)
            or out.pop("sale_tier_prices", None)
            or sales.get("tier_prices")
            or sales.get("tierPrices")
        )
        tiers = normalize_tier_prices_for_storage(raw_tiers)
        if not tiers:
            raise ValidationError("销售定价方式为阶梯售价时须维护至少一档阶梯价")
        sales = {**sales, "tier_prices": tiers}
    else:
        if isinstance(sales, dict):
            sales.pop("tier_prices", None)
            sales.pop("tierPrices", None)
        out.pop("saleTierPrices", None)
        out.pop("sale_tier_prices", None)

    if purchase_method == "tier":
        raw_tiers = (
            out.pop("purchaseTierPrices", None)
            or out.pop("purchase_tier_prices", None)
            or purchase.get("tier_prices")
            or purchase.get("tierPrices")
        )
        tiers = normalize_tier_prices_for_storage(raw_tiers)
        if not tiers:
            raise ValidationError("采购定价方式为阶梯采购价时须维护至少一档阶梯价")
        purchase = {**purchase, "tier_prices": tiers}
    else:
        if isinstance(purchase, dict):
            purchase.pop("tier_prices", None)
            purchase.pop("tierPrices", None)
        out.pop("purchaseTierPrices", None)
        out.pop("purchase_tier_prices", None)

    if sales:
        out["sales"] = sales
    if purchase:
        out["purchase"] = purchase
    return out
