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

# 标准采购入库常用物资行类型；资产采购不得继承该默认（见 finalize / assert）
PURCHASE_RECEIPT_MATERIAL_LINETYPE_NUMBER = "010"
PURCHASE_RECEIPT_MATERIAL_BIZTYPE_NUMBER = "110"
PURCHASE_RECEIPT_MATERIAL_INVSCHEME_NUMBER = "110"
PURCHASE_RECEIPT_STD_BILLTYPE_NUMBER = "im_PurInBill_STD_BT_S"

OTHER_OUTBOUND_BASE_KEY = "kingdee_other_outbound_push"
OTHER_OUTBOUND_AUXILIARY_KEY = "kingdee_other_outbound_push_auxiliary"
OTHER_OUTBOUND_ASSET_KEY = "kingdee_other_outbound_push_asset"
OTHER_OUTBOUND_ASSET_KINGDEE_RELATED_DOCUMENT = "other_outbound_asset"

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


def _variant_has_non_empty(variant: Dict[str, Any], key: str) -> bool:
    val = variant.get(key)
    if val is None:
        return False
    if isinstance(val, str):
        return bool(val.strip())
    return True


def finalize_purchase_receipt_asset_push_config(
    config: Dict[str, Any],
    warehouse: Dict[str, Any],
    *,
    variant_key: Optional[str],
) -> Dict[str, Any]:
    """资产采购入库外推：variant 未配置时不得回落标准物资行类型(010)。"""
    if variant_key != PURCHASE_RECEIPT_ASSET_KEY:
        return config
    variant_raw = warehouse.get(PURCHASE_RECEIPT_ASSET_KEY)
    variant = variant_raw if isinstance(variant_raw, dict) else {}
    out = dict(config)
    strip_rules = (
        ("linetype_number", "linetype_number", PURCHASE_RECEIPT_MATERIAL_LINETYPE_NUMBER),
        ("biztype_number", "biztype_number", PURCHASE_RECEIPT_MATERIAL_BIZTYPE_NUMBER),
        ("invscheme_number", "invscheme_number", PURCHASE_RECEIPT_MATERIAL_INVSCHEME_NUMBER),
        ("billtype_number", "billtype_number", PURCHASE_RECEIPT_STD_BILLTYPE_NUMBER),
        ("billtype_number", "bill_type_number", PURCHASE_RECEIPT_STD_BILLTYPE_NUMBER),
    )
    for variant_key_name, config_key, material_default in strip_rules:
        if not _variant_has_non_empty(variant, variant_key_name):
            if str(out.get(config_key) or "").strip() == material_default:
                out.pop(config_key, None)
    return out


def assert_purchase_receipt_asset_push_line_type_configured(
    config: Dict[str, Any],
    *,
    order_type: Optional[str],
) -> None:
    """推送组包后闸口：资产单若仍为物资行类型则阻断并提示配 variant。"""
    from apps.kuaizhizao.constants.purchase_order_type import (
        PURCHASE_ORDER_TYPE_ASSET,
        normalize_purchase_order_type,
    )

    if normalize_purchase_order_type(order_type) != PURCHASE_ORDER_TYPE_ASSET:
        return
    linetype = str(config.get("linetype_number") or "").strip()
    billtype = str(
        config.get("billtype_number") or config.get("bill_type_number") or ""
    ).strip()
    biztype = str(config.get("biztype_number") or "").strip()
    invscheme = str(
        config.get("invscheme_number")
        or config.get("inwscheme_number")
        or config.get("inv_scheme_number")
        or ""
    ).strip()
    if linetype == PURCHASE_RECEIPT_MATERIAL_LINETYPE_NUMBER:
        raise BusinessLogicError(
            "资产采购入库外推金蝶：行类型不能为物资(010)，与固定资产物料业务属性不匹配。"
            "请在业务配置 parameters.warehouse.kingdee_purchase_receipt_push_asset 填写本账套资产采购入库行类型编码，"
            "或在所绑 Save 接口样例明细中配置对应 linetype_number 后重推。"
        )
    if not linetype:
        raise BusinessLogicError(
            "资产采购入库外推金蝶：缺少行类型编码。"
            "请在业务配置 parameters.warehouse.kingdee_purchase_receipt_push_asset 填写 linetype_number"
            "（及与本账套一致的 billtype_number、biztype_number、invscheme_number），"
            "或在 Save 接口样例中补齐资产行类型后重推。"
        )
    if (
        linetype != PURCHASE_RECEIPT_MATERIAL_LINETYPE_NUMBER
        and biztype == PURCHASE_RECEIPT_MATERIAL_BIZTYPE_NUMBER
    ):
        raise BusinessLogicError(
            "资产采购入库外推金蝶：行类型为资产时，业务类型不能沿用物料类采购(110)。"
            "请在业务配置 parameters.warehouse.kingdee_purchase_receipt_push_asset "
            "填写与本账套资产采购入库单一致的单据类型、业务类型、库存事务与行类型四元组。"
        )
    if (
        linetype != PURCHASE_RECEIPT_MATERIAL_LINETYPE_NUMBER
        and billtype == PURCHASE_RECEIPT_STD_BILLTYPE_NUMBER
    ):
        raise BusinessLogicError(
            "资产采购入库外推金蝶：单据类型不能为标准采购入库单("
            f"{PURCHASE_RECEIPT_STD_BILLTYPE_NUMBER})。"
            "请在业务配置 parameters.warehouse.kingdee_purchase_receipt_push_asset "
            "填写资产采购入库单据类型编码（常见 im_PurInBill_Asset_BT_S，以本账套为准）。"
        )
    if linetype != PURCHASE_RECEIPT_MATERIAL_LINETYPE_NUMBER and (
        not billtype or not biztype or not invscheme
    ):
        raise BusinessLogicError(
            "资产采购入库外推金蝶：已配置资产行类型，须同时补齐单据类型、业务类型、库存事务。"
            "请在业务配置 parameters.warehouse.kingdee_purchase_receipt_push_asset "
            "填写 billtype_number、biztype_number、invscheme_number 与 linetype_number。"
        )


def resolve_other_outbound_kingdee_expected_related_document(
    outbound_type: Optional[str],
    *,
    default: str = "other_outbound",
) -> str:
    """资产出库外推：Save 样例/operate 解析用 other_outbound_asset，与物料出库 other_outbound 区分。"""
    from apps.kuaizhizao.constants.other_outbound_type import (
        OTHER_OUTBOUND_TYPE_ASSET,
        normalize_other_outbound_type,
    )

    if outbound_type is not None and str(outbound_type).strip():
        if normalize_other_outbound_type(outbound_type) == OTHER_OUTBOUND_TYPE_ASSET:
            return OTHER_OUTBOUND_ASSET_KINGDEE_RELATED_DOCUMENT
    return default


def resolve_other_outbound_variant_key_from_outbound_type(
    outbound_type: Optional[str],
) -> Optional[str]:
    from apps.kuaizhizao.constants.other_outbound_type import (
        OTHER_OUTBOUND_TYPE_ASSET,
        normalize_other_outbound_type,
    )

    if outbound_type is None or str(outbound_type).strip() == "":
        return None
    if normalize_other_outbound_type(outbound_type) == OTHER_OUTBOUND_TYPE_ASSET:
        return OTHER_OUTBOUND_ASSET_KEY
    return None


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
    merged = merge_warehouse_push_variant(
        warehouse,
        base_key=PURCHASE_RECEIPT_BASE_KEY,
        variant_key=variant_key,
    )
    return finalize_purchase_receipt_asset_push_config(
        merged,
        warehouse,
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
    outbound_type: Optional[str] = None,
) -> Dict[str, Any]:
    from apps.kuaizhizao.constants.other_outbound_type import (
        OTHER_OUTBOUND_TYPE_ASSET,
        assert_other_outbound_type_matches_categories,
        normalize_other_outbound_type,
    )

    category_by_id = await load_material_inventory_categories(tenant_id, material_ids)
    categories = _categories_on_lines(material_ids, category_by_id)
    header_type: Optional[str] = None
    if outbound_type is not None and str(outbound_type).strip():
        header_type = normalize_other_outbound_type(outbound_type)
        assert_other_outbound_type_matches_categories(
            header_type,
            categories,
            document_label="其他出库单",
        )
    variant_key = resolve_other_outbound_variant_key_from_outbound_type(header_type)
    if variant_key is None and header_type is None:
        variant_key = resolve_other_outbound_variant_key(categories)
    elif variant_key is None and header_type != OTHER_OUTBOUND_TYPE_ASSET:
        variant_key = resolve_other_outbound_variant_key(categories)
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
