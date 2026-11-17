"""采购订单/入库单业务类型（标准采购、资产采购、服务采购）。"""

from __future__ import annotations

from typing import Iterable, Optional

from apps.master_data.constants.material_source_type import SOURCE_TYPE_SERVICE
from apps.master_data.constants.material_inventory_category import (
    INVENTORY_CATEGORY_ASSET,
    INVENTORY_CATEGORY_EXPENSE,
    INVENTORY_CATEGORY_FINISHED,
    INVENTORY_CATEGORY_LABOR,
    INVENTORY_CATEGORY_OUTSOURCE_SEMI,
    INVENTORY_CATEGORY_RAW,
    INVENTORY_CATEGORY_SELF_SEMI,
    INVENTORY_CATEGORY_SERVICE,
    INVENTORY_CATEGORY_TRADING_GOODS,
    INVENTORY_CATEGORY_AUXILIARY,
    normalize_material_inventory_category,
)
from infra.exceptions.exceptions import BusinessLogicError, ValidationError

PURCHASE_ORDER_TYPE_STANDARD = "标准采购"
PURCHASE_ORDER_TYPE_ASSET = "资产采购"
PURCHASE_ORDER_TYPE_SERVICE = "服务采购"

ALLOWED_PURCHASE_ORDER_TYPES = frozenset(
    {
        PURCHASE_ORDER_TYPE_STANDARD,
        PURCHASE_ORDER_TYPE_ASSET,
        PURCHASE_ORDER_TYPE_SERVICE,
    }
)

SERVICE_PURCHASE_CATEGORIES = frozenset(
    {
        INVENTORY_CATEGORY_SERVICE,
        INVENTORY_CATEGORY_EXPENSE,
        INVENTORY_CATEGORY_LABOR,
    }
)

STOCK_PURCHASE_CATEGORIES = frozenset(
    {
        INVENTORY_CATEGORY_RAW,
        INVENTORY_CATEGORY_AUXILIARY,
        INVENTORY_CATEGORY_SELF_SEMI,
        INVENTORY_CATEGORY_OUTSOURCE_SEMI,
        INVENTORY_CATEGORY_FINISHED,
        INVENTORY_CATEGORY_TRADING_GOODS,
    }
)


def is_service_purchase_order_type(value: Optional[str]) -> bool:
    try:
        return normalize_purchase_order_type(value) == PURCHASE_ORDER_TYPE_SERVICE
    except ValidationError:
        return False


def normalize_purchase_order_type(value: Optional[str]) -> str:
    raw = str(value or "").strip()
    if not raw or raw == "框架协议":
        return PURCHASE_ORDER_TYPE_STANDARD
    if raw not in ALLOWED_PURCHASE_ORDER_TYPES:
        raise ValidationError(
            f"采购类型无效：{raw}，仅支持「{PURCHASE_ORDER_TYPE_STANDARD}」"
            f"、「{PURCHASE_ORDER_TYPE_ASSET}」或「{PURCHASE_ORDER_TYPE_SERVICE}」"
        )
    return raw


def _material_category_sources(
    categories: Iterable,
) -> list[tuple[Optional[str], Optional[str]]]:
    """存货类别与来源类型。元素可以是类别，或 (类别, 来源类型)。"""
    refs: list[tuple[Optional[str], Optional[str]]] = []
    for item in categories:
        if isinstance(item, tuple):
            raw_category = item[0] if item else None
            raw_source = item[1] if len(item) > 1 else None
        else:
            raw_category = item
            raw_source = None
        category = (
            normalize_material_inventory_category(raw_category)
            if raw_category is not None
            else None
        )
        source = str(raw_source).strip() if raw_source else None
        refs.append((category, source or None))
    return refs


def assert_purchase_order_type_matches_material_categories(
    order_type: str,
    categories: Iterable,
    *,
    document_label: str = "单据",
) -> None:
    """校验单据头采购类型与行物料存货类别一致。

    未填存货类别时不猜类别：标准采购沿用原规则放行；服务采购仅接受来源类型为服务的物料。
    已填写且与采购类型冲突的存货类别仍拒绝。
    """
    normalized_type = normalize_purchase_order_type(order_type)
    if not categories:
        return
    refs = _material_category_sources(categories)
    asset = INVENTORY_CATEGORY_ASSET
    known_categories = {category for category, _source in refs if category is not None}
    non_asset = {category for category in known_categories if category != asset}

    if normalized_type == PURCHASE_ORDER_TYPE_ASSET:
        if non_asset:
            raise BusinessLogicError(
                f"{document_label}为「{PURCHASE_ORDER_TYPE_ASSET}」，"
                "明细不得包含非固定资产物料，请改采购类型或更换物料"
            )
        if asset not in known_categories:
            raise BusinessLogicError(
                f"{document_label}为「{PURCHASE_ORDER_TYPE_ASSET}」，明细须为固定资产类物料"
            )
        return

    if normalized_type == PURCHASE_ORDER_TYPE_SERVICE:
        for category, source in refs:
            if category in SERVICE_PURCHASE_CATEGORIES:
                continue
            if category is None and source == SOURCE_TYPE_SERVICE:
                continue
            raise BusinessLogicError(
                f"{document_label}为「{PURCHASE_ORDER_TYPE_SERVICE}」，"
                "明细须为服务、费用或劳务类物料，请改采购类型或更换物料"
            )
        return

    if asset in known_categories:
        raise BusinessLogicError(
            f"{document_label}为「{PURCHASE_ORDER_TYPE_STANDARD}」，"
            f"明细不得包含固定资产物料，请改为「{PURCHASE_ORDER_TYPE_ASSET}」或更换物料"
        )
    if known_categories & SERVICE_PURCHASE_CATEGORIES:
        raise BusinessLogicError(
            f"{document_label}为「{PURCHASE_ORDER_TYPE_STANDARD}」，"
            f"明细不得包含服务类物料，请改为「{PURCHASE_ORDER_TYPE_SERVICE}」或更换物料"
        )
    invalid_for_standard = known_categories - STOCK_PURCHASE_CATEGORIES
    if invalid_for_standard:
        raise BusinessLogicError(
            f"{document_label}为「{PURCHASE_ORDER_TYPE_STANDARD}」，"
            "明细须为可库存类物料，请改采购类型或更换物料"
        )


async def load_and_assert_purchase_order_type_materials(
    tenant_id: int,
    order_type: str,
    material_ids: Iterable[int],
    *,
    document_label: str = "单据",
) -> None:
    from apps.master_data.models.material import Material

    ids = sorted({int(mid) for mid in material_ids if int(mid or 0) > 0})
    if not ids:
        return
    rows = await Material.filter(
        tenant_id=tenant_id,
        id__in=ids,
        deleted_at__isnull=True,
    ).values("inventory_category", "source_type")
    categories = {
        (
            normalize_material_inventory_category(row.get("inventory_category")),
            row.get("source_type"),
        )
        for row in rows
    }
    assert_purchase_order_type_matches_material_categories(
        order_type,
        categories,
        document_label=document_label,
    )
