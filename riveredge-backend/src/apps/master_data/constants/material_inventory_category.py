"""
物料存货类别（系统预置编码，如 CHLB01_SYS）。
"""

from typing import Optional

from infra.exceptions.exceptions import ValidationError

# 系统预置存货类别编码
INVENTORY_CATEGORY_RAW = "CHLB01_SYS"
INVENTORY_CATEGORY_AUXILIARY = "CHLB02_SYS"
INVENTORY_CATEGORY_SELF_SEMI = "CHLB03_SYS"
INVENTORY_CATEGORY_OUTSOURCE_SEMI = "CHLB04_SYS"
INVENTORY_CATEGORY_FINISHED = "CHLB05_SYS"
INVENTORY_CATEGORY_TRADING_GOODS = "CHLB06_SYS"
INVENTORY_CATEGORY_SERVICE = "CHLB07_SYS"
INVENTORY_CATEGORY_ASSET = "CHLB08_SYS"
INVENTORY_CATEGORY_EXPENSE = "CHLB09_SYS"
INVENTORY_CATEGORY_LABOR = "CHLB10_SYS"

INVENTORY_CATEGORY_PRINT_LABELS: dict[str, str] = {
    INVENTORY_CATEGORY_RAW: "原材料",
    INVENTORY_CATEGORY_AUXILIARY: "辅料",
    INVENTORY_CATEGORY_SELF_SEMI: "自制半成品",
    INVENTORY_CATEGORY_OUTSOURCE_SEMI: "委外半成品",
    INVENTORY_CATEGORY_FINISHED: "产成品",
    INVENTORY_CATEGORY_TRADING_GOODS: "商品",
    INVENTORY_CATEGORY_SERVICE: "服务",
    INVENTORY_CATEGORY_ASSET: "资产",
    INVENTORY_CATEGORY_EXPENSE: "费用",
    INVENTORY_CATEGORY_LABOR: "劳务",
}


def inventory_category_print_label(value: Optional[str]) -> str:
    code = normalize_material_inventory_category(value)
    if not code:
        return ""
    return INVENTORY_CATEGORY_PRINT_LABELS.get(code, code)


CANONICAL_INVENTORY_CATEGORIES = [
    INVENTORY_CATEGORY_RAW,
    INVENTORY_CATEGORY_AUXILIARY,
    INVENTORY_CATEGORY_SELF_SEMI,
    INVENTORY_CATEGORY_OUTSOURCE_SEMI,
    INVENTORY_CATEGORY_FINISHED,
    INVENTORY_CATEGORY_TRADING_GOODS,
    INVENTORY_CATEGORY_SERVICE,
    INVENTORY_CATEGORY_ASSET,
    INVENTORY_CATEGORY_EXPENSE,
    INVENTORY_CATEGORY_LABOR,
]


def normalize_material_inventory_category(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw in CANONICAL_INVENTORY_CATEGORIES:
        return raw
    upper = raw.upper()
    for code in CANONICAL_INVENTORY_CATEGORIES:
        if code.upper() == upper:
            return code
    return None


def is_canonical_material_inventory_category(value: Optional[str]) -> bool:
    return normalize_material_inventory_category(value) is not None


def require_canonical_material_inventory_category_optional(
    value: Optional[str],
) -> Optional[str]:
    """空则保持空；非空须为预置编码之一。"""
    normalized = normalize_material_inventory_category(value)
    if value is not None and str(value).strip() and not normalized:
        raise ValidationError(
            f"无效的存货类别: {value}（须为系统预置编码如 {INVENTORY_CATEGORY_RAW}）"
        )
    return normalized
