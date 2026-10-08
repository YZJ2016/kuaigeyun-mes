"""内部角色职能域（业务配置绑定的稳定标识，与 role code 解耦）。"""

from __future__ import annotations

from typing import FrozenSet, Optional

FUNCTIONAL_DOMAINS: FrozenSet[str] = frozenset({
    "sales",
    "purchase",
    "production",
    "equipment",
    "warehouse",
    "quality",
    "rd",
    "finance",
    "general",
})

PRESET_ROLE_FUNCTIONAL_DOMAIN: dict[str, str] = {
    "SALES_MANAGER": "sales",
    "SALES_PERSON": "sales",
    "PURCHASE_MANAGER": "purchase",
    "PURCHASE_PERSON": "purchase",
    "PRODUCTION_MANAGER": "production",
    "PRODUCTION_STAFF": "production",
    "EQUIPMENT_MANAGER": "equipment",
    "EQUIPMENT_OPERATOR": "equipment",
    "WAREHOUSE_MANAGER": "warehouse",
    "WAREHOUSE_OPERATOR": "warehouse",
    "FINANCE_MANAGER": "finance",
    "FINANCE_OPERATOR": "finance",
    "QUALITY_MANAGER": "quality",
    "QUALITY_OPERATOR": "quality",
    "RD_MANAGER": "rd",
    "RD_STAFF": "rd",
    "ADMIN_OFFICE": "general",
    "EMPLOYEE": "general",
    "STATION_TERMINAL": "production",
}

_PREFIX_FUNCTIONAL_DOMAIN: tuple[tuple[str, str], ...] = (
    ("SALES_", "sales"),
    ("PURCHASE_", "purchase"),
    ("PRODUCTION_", "production"),
    ("EQUIPMENT_", "equipment"),
    ("WAREHOUSE_", "warehouse"),
    ("INVENTORY_", "warehouse"),
    ("QUALITY_", "quality"),
    ("RD_", "rd"),
    ("FINANCE_", "finance"),
)


def normalize_functional_domain(value: object) -> Optional[str]:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if raw not in FUNCTIONAL_DOMAINS:
        raise ValueError(f"职能域仅支持: {', '.join(sorted(FUNCTIONAL_DOMAINS))}")
    return raw


def resolve_functional_domain_from_role_code(code: object) -> Optional[str]:
    normalized = str(code or "").strip().upper()
    if not normalized:
        return None
    direct = PRESET_ROLE_FUNCTIONAL_DOMAIN.get(normalized)
    if direct:
        return direct
    for prefix, domain in _PREFIX_FUNCTIONAL_DOMAIN:
        if normalized.startswith(prefix):
            return domain
    return None
