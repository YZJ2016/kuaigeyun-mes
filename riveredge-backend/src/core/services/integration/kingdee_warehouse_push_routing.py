"""仓储外推金蝶：按物料存货类别选择 parameters.warehouse 配置 variant。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Set

from apps.master_data.constants.material_inventory_category import (
    INVENTORY_CATEGORY_ASSET,
    INVENTORY_CATEGORY_AUXILIARY,
    normalize_material_inventory_category,
)
from core.services.integration.kingdee_warehouse_document_push_config import (
    merge_warehouse_kingdee_push_config,
)
from infra.exceptions.exceptions import BusinessLogicError

PURCHASE_RECEIPT_BASE_KEY = "kingdee_purchase_receipt_push"
PURCHASE_RECEIPT_ASSET_KEY = "kingdee_purchase_receipt_push_asset"

OTHER_OUTBOUND_BASE_KEY = "kingdee_other_outbound_push"
OTHER_OUTBOUND_AUXILIARY_KEY = "kingdee_other_outbound_push_auxiliary"
OTHER_OUTBOUND_ASSET_KEY = "kingdee_other_outbound_push_asset"

FINISHED_GOODS_RECEIPT_KEY = "kingdee_finished_goods_receipt_push"
PRODUCTION_PICKING_KEY = "kingdee_production_picking_push"


def _overlay_variant_config(base: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in variant.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        out[key] = value
    if "enabled" in variant:
        out["enabled"] = bool(base.get("enabled")) and bool(variant.get("enabled", True))
    return out


def merge_warehouse_push_variant(
    warehouse: Dict[str, Any],
    *,
    base_key: str,
    variant_key: Optional[str] = None,
) -> Dict[str, Any]:
    base = merge_warehouse_kingdee_push_config(warehouse, base_key)
    if not variant_key:
        return base
    raw_variant = warehouse.get(variant_key)
    if not isinstance(raw_variant, dict):
        return base
    return _overlay_variant_config(base, raw_variant)


async def load_material_inventory_categories(
    tenant_id: int,
    material_ids: Iterable[int],
) -> Dict[int, Optional[str]]:
    ids = sorted({int(mid) for mid in material_ids if int(mid or 0) > 0})
    if not ids:
        return {}
    from apps.master_data.models.material import Material

    rows = await Material.filter(
        tenant_id=tenant_id,
        id__in=ids,
        deleted_at__isnull=True,
    ).values("id", "inventory_category")
    out: Dict[int, Optional[str]] = {}
    for row in rows:
        out[int(row["id"])] = normalize_material_inventory_category(row.get("inventory_category"))
    return out


def _categories_on_lines(
    material_ids: Iterable[int],
    category_by_id: Dict[int, Optional[str]],
) -> Set[Optional[str]]:
    return {category_by_id.get(int(mid)) for mid in material_ids if int(mid or 0) > 0}


def resolve_purchase_receipt_variant_key_from_order_type(
    order_type: Optional[str],
) -> Optional[str]:
    from apps.kuaizhizao.constants.purchase_order_type import (
        PURCHASE_ORDER_TYPE_ASSET,
        normalize_purchase_order_type,
    )

    normalized = normalize_purchase_order_type(order_type)
    if normalized == PURCHASE_ORDER_TYPE_ASSET:
        return PURCHASE_RECEIPT_ASSET_KEY
    return None


def resolve_purchase_receipt_variant_key(
    categories: Set[Optional[str]],
) -> Optional[str]:
    """按行物料类别推断 variant（无单据头类型时的遗留路径）。"""
    if not categories:
        return None
    asset = INVENTORY_CATEGORY_ASSET
    if asset in categories:
        non_asset = {c for c in categories if c != asset}
        if non_asset:
            raise BusinessLogicError(
                "采购入库外推金蝶：同一单据不能混推固定资产物料与其它存货类别，请拆单"
            )
        return PURCHASE_RECEIPT_ASSET_KEY
    return None


def assert_purchase_receipt_order_type_matches_categories(
    order_type: Optional[str],
    categories: Set[Optional[str]],
) -> None:
    from apps.kuaizhizao.constants.purchase_order_type import (
        PURCHASE_ORDER_TYPE_STANDARD,
        assert_purchase_order_type_matches_material_categories,
        normalize_purchase_order_type,
    )

    assert_purchase_order_type_matches_material_categories(
        normalize_purchase_order_type(order_type or PURCHASE_ORDER_TYPE_STANDARD),
        categories,
        document_label="采购入库单",
    )


def resolve_other_outbound_variant_key(
    categories: Set[Optional[str]],
) -> Optional[str]:
    if not categories:
        return None
    asset = INVENTORY_CATEGORY_ASSET
    auxiliary = INVENTORY_CATEGORY_AUXILIARY
    if asset in categories:
        if categories - {asset, None}:
            raise BusinessLogicError(
                "其他出库外推金蝶：同一单据不能混推固定资产物料与其它存货类别，请拆单"
            )
        return OTHER_OUTBOUND_ASSET_KEY
    if auxiliary in categories and categories <= {auxiliary, None}:
        return OTHER_OUTBOUND_AUXILIARY_KEY
    return None


async def resolve_purchase_receipt_push_config(
    tenant_id: int,
    warehouse: Dict[str, Any],
    *,
    material_ids: Iterable[int],
    order_type: Optional[str] = None,
) -> Dict[str, Any]:
    category_by_id = await load_material_inventory_categories(tenant_id, material_ids)
    categories = _categories_on_lines(material_ids, category_by_id)
    assert_purchase_receipt_order_type_matches_categories(order_type, categories)
    variant_key = resolve_purchase_receipt_variant_key_from_order_type(order_type)
    if variant_key is None and order_type is None:
        variant_key = resolve_purchase_receipt_variant_key(categories)
    return merge_warehouse_push_variant(
        warehouse,
        base_key=PURCHASE_RECEIPT_BASE_KEY,
        variant_key=variant_key,
    )


PURCHASE_ORDER_PUSH_BASE_KEY = "kingdee_purchase_order_push"
PURCHASE_ORDER_PUSH_ASSET_KEY = "kingdee_purchase_order_push_asset"


def resolve_purchase_order_push_config(
    purchase_params: Dict[str, Any],
    *,
    order_type: Optional[str],
) -> Dict[str, Any]:
    from apps.kuaizhizao.constants.purchase_order_type import (
        PURCHASE_ORDER_TYPE_ASSET,
        normalize_purchase_order_type,
    )

    base = dict(purchase_params.get(PURCHASE_ORDER_PUSH_BASE_KEY) or {})
    normalized_type = normalize_purchase_order_type(order_type)
    variant_key = (
        PURCHASE_ORDER_PUSH_ASSET_KEY
        if normalized_type == PURCHASE_ORDER_TYPE_ASSET
        else None
    )
    if not variant_key:
        return base
    raw_variant = purchase_params.get(variant_key)
    if not isinstance(raw_variant, dict):
        return base
    return _overlay_variant_config(base, raw_variant)


async def resolve_other_outbound_push_config(
    tenant_id: int,
    warehouse: Dict[str, Any],
    *,
    material_ids: Iterable[int],
) -> Dict[str, Any]:
    category_by_id = await load_material_inventory_categories(tenant_id, material_ids)
    variant_key = resolve_other_outbound_variant_key(
        _categories_on_lines(material_ids, category_by_id)
    )
    return merge_warehouse_push_variant(
        warehouse,
        base_key=OTHER_OUTBOUND_BASE_KEY,
        variant_key=variant_key,
    )


def resolve_finished_goods_push_config(warehouse: Dict[str, Any]) -> Dict[str, Any]:
    return merge_warehouse_push_variant(
        warehouse,
        base_key=FINISHED_GOODS_RECEIPT_KEY,
        variant_key=None,
    )


def resolve_production_picking_push_config(warehouse: Dict[str, Any]) -> Dict[str, Any]:
    return merge_warehouse_push_variant(
        warehouse,
        base_key=PRODUCTION_PICKING_KEY,
        variant_key=None,
    )
