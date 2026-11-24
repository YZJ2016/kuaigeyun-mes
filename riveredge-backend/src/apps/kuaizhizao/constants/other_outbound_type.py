"""其他出库单出库类型（与采购入库 order_type 对称，外推金蝶 variant）。"""

from __future__ import annotations

from typing import Iterable, Optional

from apps.kuaizhizao.constants.purchase_order_type import (
    PURCHASE_ORDER_TYPE_ASSET,
    PURCHASE_ORDER_TYPE_STANDARD,
    assert_purchase_order_type_matches_material_rows,
    load_and_assert_purchase_order_type_materials,
)
from apps.master_data.models.material import Material

OTHER_OUTBOUND_TYPE_MATERIAL = "物料出库"
OTHER_OUTBOUND_TYPE_ASSET = "资产出库"

_OUTBOUND_TYPE_VALUES = frozenset(
    {
        OTHER_OUTBOUND_TYPE_MATERIAL,
        OTHER_OUTBOUND_TYPE_ASSET,
    }
)


def normalize_other_outbound_type(value: Optional[str]) -> str:
    text = str(value or "").strip()
    if not text:
        return OTHER_OUTBOUND_TYPE_MATERIAL
    if text not in _OUTBOUND_TYPE_VALUES:
        raise ValueError(
            f"出库类型须为「{OTHER_OUTBOUND_TYPE_MATERIAL}」或「{OTHER_OUTBOUND_TYPE_ASSET}」"
        )
    return text


def outbound_type_to_purchase_assert_type(outbound_type: str) -> str:
    normalized = normalize_other_outbound_type(outbound_type)
    if normalized == OTHER_OUTBOUND_TYPE_ASSET:
        return PURCHASE_ORDER_TYPE_ASSET
    return PURCHASE_ORDER_TYPE_STANDARD


def assert_other_outbound_type_matches_material_rows(
    outbound_type: str,
    material_rows: Iterable[dict],
    *,
    document_label: str = "其他出库单",
) -> None:
    assert_purchase_order_type_matches_material_rows(
        outbound_type_to_purchase_assert_type(outbound_type),
        material_rows,
        document_label=document_label,
    )


def assert_other_outbound_type_matches_categories(
    outbound_type: Optional[str],
    categories: Iterable,
    *,
    document_label: str = "其他出库单",
) -> None:
    if outbound_type is None or str(outbound_type).strip() == "":
        return
    from apps.kuaizhizao.constants.purchase_order_type import (
        assert_purchase_order_type_matches_material_categories,
    )

    assert_purchase_order_type_matches_material_categories(
        outbound_type_to_purchase_assert_type(outbound_type),
        categories,
        document_label=document_label,
    )


async def load_and_assert_other_outbound_type_materials(
    tenant_id: int,
    outbound_type: str,
    material_ids: Iterable[int],
) -> None:
    ids = sorted({int(mid) for mid in material_ids if int(mid or 0) > 0})
    if not ids:
        return
    rows = await Material.filter(
        tenant_id=tenant_id,
        id__in=ids,
        deleted_at__isnull=True,
    ).values("main_code", "code", "name", "inventory_category", "source_type")
    material_rows = [
        {
            "main_code": r.get("main_code") or r.get("code"),
            "name": r.get("name"),
            "inventory_category": r.get("inventory_category"),
            "source_type": r.get("source_type"),
        }
        for r in rows
    ]
    assert_other_outbound_type_matches_material_rows(
        outbound_type,
        material_rows,
        document_label="其他出库单",
    )