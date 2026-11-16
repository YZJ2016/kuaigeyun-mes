"""站点级客商取价顺序（默认与现网等价：先标准后阶梯，不含最近价直到配置开启）。"""

from __future__ import annotations

from typing import List

DEFAULT_RESOLUTION_ORDER: List[str] = ["recent", "book_standard", "book_tier"]

_VALID_STEPS = frozenset({"recent", "book_standard", "book_tier"})


def normalize_partner_price_resolution_order(raw: object) -> List[str]:
    if isinstance(raw, str) and raw.strip():
        raw = [part.strip() for part in raw.split(",") if part.strip()]
    if not isinstance(raw, list) or len(raw) != 3:
        return list(DEFAULT_RESOLUTION_ORDER)
    steps: List[str] = []
    for item in raw:
        key = str(item).strip()
        if key not in _VALID_STEPS:
            return list(DEFAULT_RESOLUTION_ORDER)
        steps.append(key)
    if len(set(steps)) != 3:
        return list(DEFAULT_RESOLUTION_ORDER)
    return steps


async def get_partner_price_resolution_order(tenant_id: int) -> List[str]:
    """读取租户 parameters.supply_chain.partner_price_resolution_order；缺省为 DEFAULT。"""
    try:
        from infra.services.business_config_service import BusinessConfigService

        svc = BusinessConfigService()
        config = await svc.get_business_config(tenant_id)
        supply = (config.get("parameters") or {}).get("supply_chain") or {}
        if isinstance(supply, dict):
            raw = supply.get("partner_price_resolution_order") or supply.get("partnerPriceResolutionOrder")
            return normalize_partner_price_resolution_order(raw)
    except Exception:
        pass
    return list(DEFAULT_RESOLUTION_ORDER)
