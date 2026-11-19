"""金蝶分录双单位：纯函数与采购入库单价反推。"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from apps.kuaizhizao.services.kingdee_purchase_receipt_push_service import (
    build_kingdee_purchase_receipt_model,
)
from apps.kuaizhizao.services.kingdee_warehouse_billentry_dual_qty import (
    apply_billentry_dual_qty_fields,
    restate_entry_prices_for_inventory_qty,
)
from apps.kuaizhizao.utils.inventory_posting_utils import convert_line_to_posting_quantities
from apps.kuaizhizao.utils.ledger_dual_quantity_utils import ledger_aux_quantity_from_base
from apps.kuaizhizao.utils.material_unit_utils import resolve_material_inventory_unit
from core.services.integration.document_push_codes import apply_unit_code_map


def test_apply_billentry_writes_qtyunit2nd_not_qty2nd():
    entry = {"qty": 1, "unit_number": "006"}
    apply_billentry_dual_qty_fields(
        entry,
        {
            "unit_number": "010",
            "qty": 2,
            "baseqty": 20,
            "unit2nd_number": "006",
            "qtyunit2nd": 20,
        },
    )
    assert entry["qty"] == 2
    assert entry["unit_number"] == "010"
    assert entry["baseqty"] == 20
    assert entry["qtyunit2nd"] == 20
    assert "qty2nd" not in entry


def test_restate_keeps_document_amount():
    entry = {"qty": 10, "price": 50, "priceandtax": 56.5}
    restate_entry_prices_for_inventory_qty(
        entry,
        document_qty=1,
        unit_price=50,
        amount=50,
        amount_and_tax=56.5,
    )
    assert entry["price"] == 5
    assert entry["priceandtax"] == 5.65


def test_restate_noop_when_qty_unchanged():
    entry = {"qty": 2, "price": 10}
    restate_entry_prices_for_inventory_qty(
        entry, document_qty=2, unit_price=10, amount=20
    )
    assert entry["price"] == 10


def test_inventory_unit_converts_box_line_to_stock_qty():
    mat = SimpleNamespace(
        base_unit="件",
        units={
            "units": [{"unit": "箱", "numerator": 10, "denominator": 1}],
            "scenarios": {"inventory": "箱"},
        },
    )
    assert resolve_material_inventory_unit(mat) == "箱"
    posted = convert_line_to_posting_quantities(
        material=mat,
        quantity=Decimal("1"),
        material_unit="箱",
    )
    assert posted.base_quantity == Decimal("10")
    assert posted.inventory_quantity == Decimal("1")
    assert ledger_aux_quantity_from_base(mat, posted.base_quantity) == Decimal("1")


def test_apply_unit_code_map_can_skip_builtin():
    assert apply_unit_code_map("kg") == "004"
    assert apply_unit_code_map("kg", use_builtin_aliases=False) == "kg"


def test_purchase_receipt_plan_restates_unit_price_keeps_tax_amount():
    receipt = SimpleNamespace(
        receipt_code="RK001",
        receipt_time=datetime(2026, 11, 19),
        created_at=datetime(2026, 11, 19),
        tax_rate=Decimal("13"),
        pay_mode="CREDIT",
        notes=None,
        buyer_operator_number=None,
        receiver_name=None,
        inspector_name=None,
        accepted_by_name=None,
        tenant_id=1,
    )
    item = SimpleNamespace(
        id=7,
        material_code="MAT",
        material_unit="箱",
        receipt_quantity=Decimal("1"),
        unit_price=Decimal("10"),
        total_amount=Decimal("10"),
        location_code=None,
        batch_number=None,
        manufacturing_date=None,
        expiry_date=None,
        notes=None,
    )
    cfg = {"use_local_bill_no": False, "istax": True, "taxrateid_number": "V13"}
    plain = build_kingdee_purchase_receipt_model(receipt=receipt, items=[item], cfg=cfg)
    row = plain["billentry"][0]
    assert row["qty"] == 1
    assert row["price"] == 10
    assert row["amount"] == 10
    assert row["taxrate"] == 13
    assert row["amountandtax"] == 11.3
    assert "qtyunit2nd" not in row

    planned = build_kingdee_purchase_receipt_model(
        receipt=receipt,
        items=[item],
        cfg=cfg,
        line_unit_qty_by_item_id={
            7: {
                "unit_number": "jian",
                "qty": 10,
                "baseqty": 10,
                "unit2nd_number": "box",
                "qtyunit2nd": 1,
            }
        },
    )
    prow = planned["billentry"][0]
    assert prow["qty"] == 10
    assert prow["unit_number"] == "jian"
    assert prow["baseqty"] == 10
    assert prow["qtyunit2nd"] == 1
    assert prow["amount"] == 10
    assert prow["amountandtax"] == 11.3
    assert prow["taxrate"] == 13
    assert prow["taxrateid_number"] == "V13"
    assert prow["price"] == 1
    assert prow["priceandtax"] == 1.13
