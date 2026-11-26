"""采购入库外推：库存单位取物料真源，禁止 kg→004；须显式推送辅助数量。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaiconnect.services.document_push.kingdee_purchase_receipt_push_service import (
    build_kingdee_purchase_receipt_model,
    resolve_purchase_receipt_line_unit_qty,
)


@pytest.mark.asyncio
async def test_resolve_line_unit_prefers_inventory_unit_not_builtin_004():
    item = SimpleNamespace(
        id=11,
        material_id=101,
        material_code="0201010108",
        material_unit="kg",
        receipt_quantity=Decimal("20"),
        aux_quantity=None,
        aux_unit=None,
        unit_conversion_rate=None,
    )
    material = SimpleNamespace(
        id=101,
        base_unit="kg",
        inventory_unit="kg",
        units=None,
    )

    async def _lookup(_tid, ref):
        return "kg" if str(ref).strip().lower() == "kg" else None

    with (
        patch(
            "apps.master_data.models.material.Material.filter",
            new_callable=AsyncMock,
            return_value=[material],
        ),
        patch(
            "core.services.integration.document_push_codes.lookup_unit_catalog_code",
            new_callable=AsyncMock,
            side_effect=_lookup,
        ),
        patch(
            "apps.kuaizhizao.utils.inventory_posting_utils.convert_line_to_posting_quantities",
            return_value=SimpleNamespace(
                inventory_quantity=Decimal("20"),
                base_quantity=Decimal("20"),
            ),
        ),
    ):
        plan = await resolve_purchase_receipt_line_unit_qty(71, [item])

    assert plan[11]["unit_number"] == "kg"
    assert plan[11]["qty"] == 20.0
    assert "qtyunit2nd" not in plan[11]


@pytest.mark.asyncio
async def test_resolve_line_skips_dirty_aux_when_material_has_no_aux_unit():
    """物料未启用辅助单位时，行上残留 aux_* 不得推 unit2nd。"""
    item = SimpleNamespace(
        id=11,
        material_id=101,
        material_code="0304060002",
        material_unit="桶",
        receipt_quantity=Decimal("10"),
        aux_quantity=Decimal("10"),
        aux_unit="件",
        unit_conversion_rate=Decimal("1"),
    )
    material = SimpleNamespace(
        id=101,
        base_unit="桶",
        inventory_unit="桶",
        units={"units": [], "scenarios": {"inventory": "桶"}},
    )

    async def _lookup(_tid, ref):
        text = str(ref).strip()
        return text if text in {"桶", "件"} else None

    with (
        patch(
            "apps.master_data.models.material.Material.filter",
            new_callable=AsyncMock,
            return_value=[material],
        ),
        patch(
            "core.services.integration.document_push_codes.lookup_unit_catalog_code",
            new_callable=AsyncMock,
            side_effect=_lookup,
        ),
        patch(
            "apps.kuaizhizao.utils.inventory_posting_utils.convert_line_to_posting_quantities",
            return_value=SimpleNamespace(
                inventory_quantity=Decimal("10"),
                base_quantity=Decimal("10"),
            ),
        ),
    ):
        plan = await resolve_purchase_receipt_line_unit_qty(2, [item])

    assert plan[11]["unit_number"] == "桶"
    assert plan[11]["qty"] == 10.0
    assert "unit2nd_number" not in plan[11]
    assert "qtyunit2nd" not in plan[11]


@pytest.mark.asyncio
async def test_resolve_line_pushes_document_aux_qtyunit2nd():
    """单据行 20kg / 5件 → 苍穹 qty + qtyunit2nd（非 qty2nd）。"""
    item = SimpleNamespace(
        id=11,
        material_id=101,
        material_code="0201010108",
        material_unit="kg",
        receipt_quantity=Decimal("20"),
        aux_quantity=Decimal("5"),
        aux_unit="件",
        unit_conversion_rate=Decimal("4"),
    )
    material = SimpleNamespace(
        id=101,
        base_unit="kg",
        inventory_unit="kg",
        units={"units": [{"unit": "件", "conversionType": "floating"}]},
    )

    async def _lookup(_tid, ref):
        text = str(ref).strip()
        if text.casefold() == "kg":
            return "kg"
        if text == "件":
            return "件"
        return None

    with (
        patch(
            "apps.master_data.models.material.Material.filter",
            new_callable=AsyncMock,
            return_value=[material],
        ),
        patch(
            "core.services.integration.document_push_codes.lookup_unit_catalog_code",
            new_callable=AsyncMock,
            side_effect=_lookup,
        ),
        patch(
            "apps.kuaizhizao.utils.inventory_posting_utils.convert_line_to_posting_quantities",
            return_value=SimpleNamespace(
                inventory_quantity=Decimal("20"),
                base_quantity=Decimal("20"),
            ),
        ),
    ):
        plan = await resolve_purchase_receipt_line_unit_qty(71, [item])

    assert plan[11]["unit_number"] == "kg"
    assert plan[11]["qty"] == 20.0
    assert plan[11]["baseqty"] == 20.0
    assert plan[11]["unit2nd_number"] == "件"
    assert plan[11]["qtyunit2nd"] == 5.0
    assert "qty2nd" not in plan[11]


def test_build_model_uses_line_unit_plan():
    receipt = SimpleNamespace(
        id=569,
        receipt_code="CGRK-TEST",
        receipt_time=None,
        created_at=None,
        pay_mode=None,
        tax_rate=Decimal("13"),
        notes=None,
        buyer_operator_number=None,
        receiver_name=None,
    )
    item = SimpleNamespace(
        id=11,
        material_code="0201010108",
        material_unit="kg",
        receipt_quantity=Decimal("20"),
        unit_price=Decimal("1"),
        total_amount=Decimal("20"),
        warehouse_id=None,
        batch_number=None,
        manufacturing_date=None,
        expiry_date=None,
        notes=None,
        location_id=None,
        location_code=None,
    )
    model = build_kingdee_purchase_receipt_model(
        receipt=receipt,
        items=[item],
        cfg={
            "org_number": "100",
            "billtype_number": "im_PurInBill_STD_BT_S",
            "biztype_number": "110",
            "invscheme_number": "110",
            "invstatus_number": "110",
            "invtype_number": "110",
            "linetype_number": "010",
        },
        supplier_number="V001",
        line_unit_qty_by_item_id={
            11: {
                "unit_number": "kg",
                "qty": 20.0,
                "baseqty": 20.0,
                "unit2nd_number": "件",
                "qtyunit2nd": 5.0,
            }
        },
    )
    entry = model["billentry"][0]
    assert entry["unit_number"] == "kg"
    assert entry["qty"] == 20.0
    assert entry["baseqty"] == 20.0
    assert entry["unit2nd_number"] == "件"
    assert entry["qtyunit2nd"] == 5.0
    assert "qty2nd" not in entry


def test_build_model_prefers_document_buyer_over_config_and_fixed():
    """单据采购员工号优先；fixed_values 不得盖回旧工号。无单据工号时才用配置。"""
    receipt = SimpleNamespace(
        id=578,
        receipt_code="CGRK-TEST-BUYER",
        receipt_time=None,
        created_at=None,
        pay_mode=None,
        tax_rate=Decimal("13"),
        notes=None,
        buyer_operator_number="ID-000082",
        receiver_name=None,
    )
    item = SimpleNamespace(
        id=11,
        material_code="0201010108",
        material_unit="kg",
        receipt_quantity=Decimal("1"),
        unit_price=Decimal("1"),
        total_amount=Decimal("1"),
        warehouse_id=None,
        batch_number=None,
        manufacturing_date=None,
        expiry_date=None,
        notes=None,
        location_id=None,
        location_code=None,
    )
    model = build_kingdee_purchase_receipt_model(
        receipt=receipt,
        items=[item],
        cfg={
            "org_number": "BU-00001",
            "billtype_number": "im_PurInBill_STD_BT_S",
            "biztype_number": "110",
            "invscheme_number": "110",
            "invstatus_number": "110",
            "invtype_number": "110",
            "linetype_number": "010",
            "bizoperator_operatornumber": "ID-000081",
            "fixed_values": {"bizoperator_operatornumber": "ID-000107"},
        },
        supplier_number="V001",
        line_unit_qty_by_item_id={11: {"unit_number": "kg", "qty": 1.0}},
    )
    assert model["bizoperator_operatornumber"] == "ID-000082"

    receipt_no_buyer = SimpleNamespace(
        id=578,
        receipt_code="CGRK-TEST-BUYER",
        receipt_time=None,
        created_at=None,
        pay_mode=None,
        tax_rate=Decimal("13"),
        notes=None,
        buyer_operator_number=None,
        receiver_name=None,
    )
    model_cfg = build_kingdee_purchase_receipt_model(
        receipt=receipt_no_buyer,
        items=[item],
        cfg={
            "org_number": "BU-00001",
            "billtype_number": "im_PurInBill_STD_BT_S",
            "biztype_number": "110",
            "invscheme_number": "110",
            "invstatus_number": "110",
            "invtype_number": "110",
            "linetype_number": "010",
            "bizoperator_operatornumber": "ID-000081",
        },
        supplier_number="V001",
        line_unit_qty_by_item_id={11: {"unit_number": "kg", "qty": 1.0}},
    )
    assert model_cfg["bizoperator_operatornumber"] == "ID-000081"



