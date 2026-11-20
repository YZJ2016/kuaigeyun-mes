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
    inventory_category_print_label,
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


def _format_material_line_hint(
    main_code: Optional[str],
    name: Optional[str],
    category: Optional[str],
) -> str:
    code = str(main_code or "").strip()
    title = str(name or "").strip()
    identity = f"{code} {title}".strip()
    cat_label = inventory_category_print_label(category)
    if identity and cat_label:
        return f"{identity}（存货类别：{cat_label}）"
    if identity:
        return identity
    if cat_label:
        return f"存货类别：{cat_label}"
    return "未分类物料"


def _format_offending_lines(
    rows: list[dict],
    *,
    max_lines: int = 5,
) -> str:
    hints: list[str] = []
    for row in rows[:max_lines]:
        hints.append(
            _format_material_line_hint(
                row.get("main_code"),
                row.get("name"),
                row.get("inventory_category"),
            )
        )
    tail = ""
    if len(rows) > max_lines:
        tail = f"；另有 {len(rows) - max_lines} 行未列出"
    return "；".join(hints) + tail


def _raise_purchase_type_mismatch(
    *,
    document_label: str,
    current_type: str,
    offenders: list[dict],
    action_hint: str,
    generic_message: str,
) -> None:
    has_identity = any(
        str(row.get("main_code") or "").strip() or str(row.get("name") or "").strip()
        for row in offenders
    )
    if has_identity and offenders:
        detail = _format_offending_lines(offenders)
        raise BusinessLogicError(
            f"{document_label}当前表头采购类型为「{current_type}」，"
            f"以下明细物料与类型不符：{detail}。{action_hint}"
        )
    raise BusinessLogicError(generic_message)


def assert_purchase_order_type_matches_material_rows(
    order_type: str,
    material_rows: Iterable[dict],
    *,
    document_label: str = "单据",
) -> None:
    """校验单据头采购类型与行物料存货类别一致（含物料编码/名称提示）。"""
    rows = list(material_rows)
    if not rows:
        return
    normalized_type = normalize_purchase_order_type(order_type)
    asset = INVENTORY_CATEGORY_ASSET

    refs = [
        (
            normalize_material_inventory_category(row.get("inventory_category"))
            if row.get("inventory_category") is not None
            else None,
            str(row.get("source_type")).strip() if row.get("source_type") else None,
            row,
        )
        for row in rows
    ]

    if normalized_type == PURCHASE_ORDER_TYPE_ASSET:
        non_asset = [
            row
            for category, _source, row in refs
            if category is not None and category != asset
        ]
        if non_asset:
            _raise_purchase_type_mismatch(
                document_label=document_label,
                current_type=PURCHASE_ORDER_TYPE_ASSET,
                offenders=non_asset,
                action_hint="请改表头为匹配的采购类型，或更换明细物料。",
                generic_message=(
                    f"{document_label}为「{PURCHASE_ORDER_TYPE_ASSET}」，"
                    "明细不得包含非固定资产物料，请改采购类型或更换物料"
                ),
            )
        if not any(category == asset for category, _source, _row in refs):
            raise BusinessLogicError(
                f"{document_label}为「{PURCHASE_ORDER_TYPE_ASSET}」，明细须为固定资产类物料"
            )
        return

    if normalized_type == PURCHASE_ORDER_TYPE_SERVICE:
        offenders: list[dict] = []
        for category, source, row in refs:
            if category in SERVICE_PURCHASE_CATEGORIES:
                continue
            if category is None and source == SOURCE_TYPE_SERVICE:
                continue
            offenders.append(row)
        if offenders:
            _raise_purchase_type_mismatch(
                document_label=document_label,
                current_type=PURCHASE_ORDER_TYPE_SERVICE,
                offenders=offenders,
                action_hint=(
                    f"请将表头「采购类型」改为「{PURCHASE_ORDER_TYPE_STANDARD}」或"
                    f"「{PURCHASE_ORDER_TYPE_ASSET}」，或更换为服务/费用/劳务类物料。"
                ),
                generic_message=(
                    f"{document_label}为「{PURCHASE_ORDER_TYPE_SERVICE}」，"
                    "明细须为服务、费用或劳务类物料，请改采购类型或更换物料"
                ),
            )
        return

    asset_lines = [row for category, _source, row in refs if category == asset]
    if asset_lines:
        _raise_purchase_type_mismatch(
            document_label=document_label,
            current_type=PURCHASE_ORDER_TYPE_STANDARD,
            offenders=asset_lines,
            action_hint=(
                f"请将表头「采购类型」改为「{PURCHASE_ORDER_TYPE_ASSET}」，"
                "或在明细中更换为可库存类物料（如原材料、辅料、商品等）。"
            ),
            generic_message=(
                f"{document_label}为「{PURCHASE_ORDER_TYPE_STANDARD}」，"
                f"明细不得包含固定资产物料，请改为「{PURCHASE_ORDER_TYPE_ASSET}」或更换物料"
            ),
        )

    service_lines = [
        row
        for category, _source, row in refs
        if category in SERVICE_PURCHASE_CATEGORIES
    ]
    if service_lines:
        _raise_purchase_type_mismatch(
            document_label=document_label,
            current_type=PURCHASE_ORDER_TYPE_STANDARD,
            offenders=service_lines,
            action_hint=(
                f"请将表头「采购类型」改为「{PURCHASE_ORDER_TYPE_SERVICE}」，"
                "或在明细中更换为可库存类物料。"
            ),
            generic_message=(
                f"{document_label}为「{PURCHASE_ORDER_TYPE_STANDARD}」，"
                f"明细不得包含服务类物料，请改为「{PURCHASE_ORDER_TYPE_SERVICE}」或更换物料"
            ),
        )

    invalid_for_standard = [
        row
        for category, _source, row in refs
        if category is not None and category not in STOCK_PURCHASE_CATEGORIES
    ]
    if invalid_for_standard:
        _raise_purchase_type_mismatch(
            document_label=document_label,
            current_type=PURCHASE_ORDER_TYPE_STANDARD,
            offenders=invalid_for_standard,
            action_hint="请改表头采购类型，或更换为可库存类物料。",
            generic_message=(
                f"{document_label}为「{PURCHASE_ORDER_TYPE_STANDARD}」，"
                "明细须为可库存类物料，请改采购类型或更换物料"
            ),
        )


def assert_purchase_order_type_matches_material_categories(
    order_type: str,
    categories: Iterable,
    *,
    document_label: str = "单据",
) -> None:
    """校验单据头采购类型与行物料存货类别一致（仅类别，无物料快照）。"""
    if not categories:
        return
    refs = _material_category_sources(categories)
    rows = [
        {
            "main_code": "",
            "name": "",
            "inventory_category": category,
            "source_type": source,
        }
        for category, source in refs
    ]
    assert_purchase_order_type_matches_material_rows(
        order_type,
        rows,
        document_label=document_label,
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
    ).values("main_code", "name", "inventory_category", "source_type")
    assert_purchase_order_type_matches_material_rows(
        order_type,
        list(rows),
        document_label=document_label,
    )
