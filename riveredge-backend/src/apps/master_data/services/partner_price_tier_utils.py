"""数量阶梯价：校验与命中（价本行、物料 defaults 共用结构）。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


def normalize_tier_prices_for_storage(raw: Any) -> Optional[List[Dict[str, Any]]]:
    if not raw:
        return None
    if not isinstance(raw, list):
        raise ValueError("tier_prices 须为数组")
    out: List[Dict[str, Any]] = []
    for line in raw:
        if isinstance(line, dict):
            min_q = line.get("min_quantity") if "min_quantity" in line else line.get("minQuantity")
            max_q = line.get("max_quantity") if "max_quantity" in line else line.get("maxQuantity")
            up = line.get("unit_price") if "unit_price" in line else line.get("unitPrice")
        else:
            min_q = getattr(line, "min_quantity", None) or getattr(line, "minQuantity", None)
            max_q = getattr(line, "max_quantity", None) or getattr(line, "maxQuantity", None)
            up = getattr(line, "unit_price", None) or getattr(line, "unitPrice", None)
        if min_q is None or up is None:
            raise ValueError("阶梯价须填写起订量与单价")
        min_dec = Decimal(str(min_q))
        max_dec = Decimal(str(max_q)) if max_q is not None and str(max_q).strip() != "" else None
        price_dec = Decimal(str(up))
        if min_dec <= 0:
            raise ValueError("阶梯起订量须大于 0")
        if max_dec is not None and max_dec < min_dec:
            raise ValueError("阶梯截止量不能小于起订量")
        if price_dec <= 0:
            raise ValueError("阶梯单价须大于 0")
        out.append(
            {
                "minQuantity": float(min_dec) if min_dec == min_dec.to_integral_value() else str(min_dec),
                "maxQuantity": (
                    None
                    if max_dec is None
                    else (float(max_dec) if max_dec == max_dec.to_integral_value() else str(max_dec))
                ),
                "unitPrice": str(price_dec),
            }
        )
    validate_tier_intervals(out)
    return out


def validate_tier_intervals(tiers: List[Dict[str, Any]]) -> None:
    if not tiers:
        return
    parsed: List[Tuple[Decimal, Optional[Decimal], int]] = []
    for idx, line in enumerate(tiers):
        min_q = Decimal(str(line.get("minQuantity") or line.get("min_quantity")))
        max_raw = line.get("maxQuantity") if "maxQuantity" in line else line.get("max_quantity")
        max_q = Decimal(str(max_raw)) if max_raw is not None and str(max_raw).strip() != "" else None
        parsed.append((min_q, max_q, idx))
    parsed.sort(key=lambda x: x[0])
    for i in range(len(parsed) - 1):
        cur_min, cur_max, _ = parsed[i]
        next_min, _, _ = parsed[i + 1]
        if cur_max is None:
            raise ValueError("阶梯区间重叠：存在无上限档时不能再有更高起订量档")
        if cur_max >= next_min:
            raise ValueError("阶梯数量区间重叠或相邻冲突")


def match_tier_unit_price(
    tiers: Optional[List[Dict[str, Any]]],
    quantity: Optional[Decimal],
) -> Optional[Decimal]:
    if not tiers or quantity is None:
        return None
    qty = Decimal(str(quantity))
    if qty <= 0:
        return None
    best_min = Decimal("-1")
    best_price: Optional[Decimal] = None
    for line in tiers:
        min_q = Decimal(str(line.get("minQuantity") or line.get("min_quantity")))
        max_raw = line.get("maxQuantity") if "maxQuantity" in line else line.get("max_quantity")
        max_q = Decimal(str(max_raw)) if max_raw is not None and str(max_raw).strip() != "" else None
        if qty < min_q:
            continue
        if max_q is not None and qty > max_q:
            continue
        if min_q >= best_min:
            best_min = min_q
            best_price = Decimal(str(line.get("unitPrice") or line.get("unit_price")))
    return best_price
