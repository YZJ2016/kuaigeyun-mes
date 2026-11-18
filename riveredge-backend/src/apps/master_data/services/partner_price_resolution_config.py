"""站点级客商取价：销售/采购在历史成交价与价格本之间二选一，未命中再走物料默认。"""

from __future__ import annotations

from typing import List, Literal

Side = Literal["purchase", "sales"]

PARTNER_PRICE_SOURCE_RECENT = "recent"
PARTNER_PRICE_SOURCE_PRICE_BOOK = "price_book"

_VALID_SOURCES = frozenset({PARTNER_PRICE_SOURCE_RECENT, PARTNER_PRICE_SOURCE_PRICE_BOOK})

# 兼容旧版三元顺序配置（仅读，供未写入新键的租户推导）
_LEGACY_DEFAULT_ORDER: List[str] = ["recent", "book_standard", "book_tier"]
_VALID_LEGACY_STEPS = frozenset({"recent", "book_standard", "book_tier"})


def normalize_partner_price_resolution_order(raw: object) -> List[str]:
    if isinstance(raw, str) and raw.strip():
        raw = [part.strip() for part in raw.split(",") if part.strip()]
    if not isinstance(raw, list) or len(raw) != 3:
        return list(_LEGACY_DEFAULT_ORDER)
    steps: List[str] = []
    for item in raw:
        key = str(item).strip()
        if key not in _VALID_LEGACY_STEPS:
            return list(_LEGACY_DEFAULT_ORDER)
        steps.append(key)
    if len(set(steps)) != 3:
        return list(_LEGACY_DEFAULT_ORDER)
    return steps


def _legacy_source_from_order(order: List[str]) -> str:
    first = order[0] if order else "recent"
    if first == "recent":
        return PARTNER_PRICE_SOURCE_RECENT
    return PARTNER_PRICE_SOURCE_PRICE_BOOK


def normalize_partner_price_source(raw: object) -> str | None:
    if raw is None:
        return None
    key = str(raw).strip()
    if key in _VALID_SOURCES:
        return key
    return None


async def get_partner_price_source_mode(tenant_id: int, side: Side) -> str:
    """sales / purchase 各自：recent=仅历史成交价，price_book=仅价格本（含阶梯）。"""
    category = "sales" if side == "sales" else "purchase"
    try:
        from infra.services.business_config_service import BusinessConfigService

        svc = BusinessConfigService()
        config = await svc.get_business_config(tenant_id)
        params = config.get("parameters") or {}
        bucket = params.get(category) or {}
        if isinstance(bucket, dict):
            raw = bucket.get("partner_price_source") or bucket.get("partnerPriceSource")
            normalized = normalize_partner_price_source(raw)
            if normalized:
                return normalized
        supply = params.get("supply_chain") or {}
        if isinstance(supply, dict):
            legacy_raw = supply.get("partner_price_resolution_order") or supply.get(
                "partnerPriceResolutionOrder"
            )
            return _legacy_source_from_order(normalize_partner_price_resolution_order(legacy_raw))
    except Exception:
        pass
    return _legacy_source_from_order(list(_LEGACY_DEFAULT_ORDER))


async def get_partner_price_resolution_order(tenant_id: int, side: Side) -> List[str]:
    mode = await get_partner_price_source_mode(tenant_id, side)
    if mode == PARTNER_PRICE_SOURCE_RECENT:
        return ["recent"]
    return ["book_standard", "book_tier"]


async def get_partner_price_resolution_order_legacy(tenant_id: int) -> List[str]:
    """仅供兼容测试或诊断；业务取价须带 side。"""
    return await get_partner_price_resolution_order(tenant_id, "sales")
