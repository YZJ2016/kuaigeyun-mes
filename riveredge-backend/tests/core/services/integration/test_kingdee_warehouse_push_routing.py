"""采购入库金蝶外推：资产 variant 不得继承物资行类型 010。"""

from core.services.integration.kingdee_warehouse_push_routing import (
    PURCHASE_RECEIPT_ASSET_KEY,
    PURCHASE_RECEIPT_BASE_KEY,
    PURCHASE_RECEIPT_MATERIAL_BIZTYPE_NUMBER,
    PURCHASE_RECEIPT_MATERIAL_LINETYPE_NUMBER,
    PURCHASE_RECEIPT_STD_BILLTYPE_NUMBER,
    assert_purchase_receipt_asset_push_line_type_configured,
    finalize_purchase_receipt_asset_push_config,
    merge_warehouse_push_variant,
)
from infra.exceptions.exceptions import BusinessLogicError


def test_asset_variant_strips_inherited_material_purin_codes():
    warehouse = {
        PURCHASE_RECEIPT_BASE_KEY: {
            "enabled": True,
            "linetype_number": PURCHASE_RECEIPT_MATERIAL_LINETYPE_NUMBER,
            "biztype_number": PURCHASE_RECEIPT_MATERIAL_BIZTYPE_NUMBER,
            "invscheme_number": "110",
            "billtype_number": PURCHASE_RECEIPT_STD_BILLTYPE_NUMBER,
        },
        PURCHASE_RECEIPT_ASSET_KEY: {"enabled": True},
    }
    merged = merge_warehouse_push_variant(
        warehouse,
        base_key=PURCHASE_RECEIPT_BASE_KEY,
        variant_key=PURCHASE_RECEIPT_ASSET_KEY,
    )
    finalized = finalize_purchase_receipt_asset_push_config(
        merged,
        warehouse,
        variant_key=PURCHASE_RECEIPT_ASSET_KEY,
    )
    for key in (
        "linetype_number",
        "biztype_number",
        "invscheme_number",
        "billtype_number",
    ):
        assert key not in finalized


def test_asset_variant_strips_inherited_material_linetype():
    warehouse = {
        PURCHASE_RECEIPT_BASE_KEY: {
            "enabled": True,
            "linetype_number": PURCHASE_RECEIPT_MATERIAL_LINETYPE_NUMBER,
        },
        PURCHASE_RECEIPT_ASSET_KEY: {
            "enabled": True,
            "linetype_number": "",
        },
    }
    merged = merge_warehouse_push_variant(
        warehouse,
        base_key=PURCHASE_RECEIPT_BASE_KEY,
        variant_key=PURCHASE_RECEIPT_ASSET_KEY,
    )
    finalized = finalize_purchase_receipt_asset_push_config(
        merged,
        warehouse,
        variant_key=PURCHASE_RECEIPT_ASSET_KEY,
    )
    assert "linetype_number" not in finalized


def test_asset_variant_keeps_explicit_linetype():
    warehouse = {
        PURCHASE_RECEIPT_BASE_KEY: {
            "enabled": True,
            "linetype_number": PURCHASE_RECEIPT_MATERIAL_LINETYPE_NUMBER,
        },
        PURCHASE_RECEIPT_ASSET_KEY: {
            "enabled": True,
            "linetype_number": "030",
        },
    }
    merged = merge_warehouse_push_variant(
        warehouse,
        base_key=PURCHASE_RECEIPT_BASE_KEY,
        variant_key=PURCHASE_RECEIPT_ASSET_KEY,
    )
    finalized = finalize_purchase_receipt_asset_push_config(
        merged,
        warehouse,
        variant_key=PURCHASE_RECEIPT_ASSET_KEY,
    )
    assert finalized.get("linetype_number") == "030"


def test_assert_blocks_material_linetype_on_asset_order():
    try:
        assert_purchase_receipt_asset_push_line_type_configured(
            {"linetype_number": "010"},
            order_type="资产采购",
        )
        raise AssertionError("expected BusinessLogicError")
    except BusinessLogicError as exc:
        assert "010" in str(exc)


def test_assert_blocks_material_biztype_with_asset_linetype():
    try:
        assert_purchase_receipt_asset_push_line_type_configured(
            {
                "linetype_number": "040",
                "biztype_number": "110",
                "billtype_number": "im_PurInBill_Asset_BT_S",
                "invscheme_number": "120",
            },
            order_type="资产采购",
        )
        raise AssertionError("expected BusinessLogicError")
    except BusinessLogicError as exc:
        assert "110" in str(exc)


def test_assert_requires_full_asset_quad_when_linetype_set():
    try:
        assert_purchase_receipt_asset_push_line_type_configured(
            {"linetype_number": "040", "biztype_number": "120"},
            order_type="资产采购",
        )
        raise AssertionError("expected BusinessLogicError")
    except BusinessLogicError as exc:
        assert "billtype_number" in str(exc) or "单据类型" in str(exc)


def test_assert_allows_configured_asset_quad():
    assert_purchase_receipt_asset_push_line_type_configured(
        {
            "linetype_number": "040",
            "billtype_number": "im_PurInBill_Asset_BT_S",
            "biztype_number": "120",
            "invscheme_number": "120",
        },
        order_type="资产采购",
    )