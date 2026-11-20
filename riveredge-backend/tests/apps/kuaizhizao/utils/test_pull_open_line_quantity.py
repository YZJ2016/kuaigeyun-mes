"""开口行取单主/副数量契约单测。"""

from decimal import Decimal
from types import SimpleNamespace

from apps.kuaizhizao.utils.pull_open_line_quantity import (
    build_partial_push_aux_triplet,
    build_partial_push_qty_triplet,
    build_whole_line_gate_aux_triplet,
    build_whole_line_gate_primary_triplet,
    compose_pushed_aux_qty,
    dual_quantity_for_open_requisition_push,
    enrich_pull_line_from_source_item,
    merge_pull_open_line_qty_fields,
    remaining_qty,
    resolve_requisition_material_aux_triplet,
)


class _LineSource:
    aux_quantity = 10
    aux_unit = "箱"


def test_remaining_qty_floor_at_zero():
    assert remaining_qty(5, 8) == 0.0
    assert remaining_qty(8, 3) == 5.0


def test_partial_push_primary_triplet():
    sug, pushed, rem = build_partial_push_qty_triplet(100, 30)
    assert (sug, pushed, rem) == (100.0, 30.0, 70.0)


def test_partial_push_aux_triplet_none_without_suggested():
    assert build_partial_push_aux_triplet(None, 0) == (None, None, None)


def test_partial_push_aux_triplet():
    sug, pushed, rem = build_partial_push_aux_triplet(10, 4)
    assert (sug, pushed, rem) == (10.0, 4.0, 6.0)


def test_whole_line_gate_primary_and_aux():
    ps, pp, pr = build_whole_line_gate_primary_triplet(50, already_pushed=False, push_allowed=True)
    assert (ps, pp, pr) == (50.0, 0.0, 50.0)
    as_, ap, ar = build_whole_line_gate_aux_triplet(8, already_pushed=True, push_allowed=False)
    assert (as_, ap, ar) == (8.0, 8.0, 0.0)


def test_enrich_pull_line_from_source_item_writes_aux():
    row: dict = {}
    enrich_pull_line_from_source_item(
        row,
        _LineSource(),
        suggested_primary=100,
        pushed_primary=20,
        remaining_primary=80,
        occupied_aux_pushed=3,
    )
    assert row["suggested_quantity"] == 100
    assert row["remaining_quantity"] == 80
    assert row["suggested_aux_quantity"] == 10
    assert row["pushed_aux_quantity"] == 3
    assert row["remaining_aux_quantity"] == 7
    assert row["aux_unit"] == "箱"


def test_dual_quantity_for_open_requisition_push_matches_group_remaining_aux():
    """拆行后行内 aux=30、主=3，但组级副可取仍为 110-88=22。"""
    pushed_row = SimpleNamespace(
        id=101,
        quantity=8,
        aux_quantity=80,
        aux_unit="KG",
        unit_conversion_rate=None,
    )
    open_row = SimpleNamespace(
        id=102,
        quantity=3,
        aux_quantity=30,
        aux_unit="KG",
        unit_conversion_rate=None,
    )
    group = [pushed_row, open_row]
    occ_aux = {101: Decimal("88"), 102: Decimal("0")}
    dual = dual_quantity_for_open_requisition_push(
        open_row,
        group_items=group,
        occupied_aux_by_item_id=occ_aux,
        push_primary_qty=3,
        line_remaining_primary=3,
    )
    assert float(dual["aux_quantity"]) == 22.0
    assert dual["aux_unit"] == "KG"


def test_split_requisition_material_group_qty_after_partial_po():
    """拆行后开口展示：主副三元组按同物料组汇总（申请量不变、已转累加）。"""
    pushed_row = SimpleNamespace(id=101, quantity=2, aux_quantity=5, aux_unit="箱")
    remainder_row = SimpleNamespace(id=102, quantity=2, aux_quantity=5, aux_unit="箱")
    group_suggested = float(pushed_row.quantity + remainder_row.quantity)
    group_occupied = 2.0
    sug, pushed, rem = build_partial_push_qty_triplet(group_suggested, group_occupied)
    assert (sug, pushed, rem) == (4.0, 2.0, 2.0)

    aux_sug, aux_pushed, aux_rem, unit = resolve_requisition_material_aux_triplet(
        group_items=[pushed_row, remainder_row],
        occupied_aux_by_item_id={101: Decimal("6"), 102: Decimal("0")},
    )
    assert unit == "箱"
    assert (aux_sug, aux_pushed, aux_rem) == (10.0, 6.0, 4.0)


def test_merge_without_aux_unit_omits_aux_fields():
    row: dict = {}
    merge_pull_open_line_qty_fields(
        row,
        suggested_primary=1,
        pushed_primary=0,
        remaining_primary=1,
    )
    assert "aux_unit" not in row
    assert "suggested_aux_quantity" not in row


def test_compose_pushed_aux_counts_confirmed_receipt():
    """分批入库第二次取单：已入库那批的副数量必须计入，副已转不能退回 0。"""
    assert compose_pushed_aux_qty(confirmed_receipt_aux=0.5, pending_receipt_aux=0) == 0.5


def test_compose_pushed_aux_adds_pending_occupancy():
    """同批既有已入库又有待入库占用时，副已转 = 两批之和。"""
    assert compose_pushed_aux_qty(confirmed_receipt_aux=0.5, pending_receipt_aux=0.3) == 0.8


def test_compose_pushed_aux_subtracts_confirmed_return():
    """已确认退货释放已转副数量，与已转主数量减已确认退货同口径。"""
    assert (
        compose_pushed_aux_qty(
            confirmed_receipt_aux=1,
            pending_receipt_aux=0,
            confirmed_returned_aux=0.25,
        )
        == 0.75
    )


def test_compose_pushed_aux_never_negative():
    assert (
        compose_pushed_aux_qty(
            confirmed_receipt_aux=0,
            pending_receipt_aux=0,
            confirmed_returned_aux=1,
        )
        == 0.0
    )


def test_second_batch_aux_triplet_after_first_receipt_confirmed():
    """2 KG = 1 件：首批入库 1 KG 已确认，第二次取单副三元组须为 1 / 0.5 / 0.5。"""
    pushed_aux = compose_pushed_aux_qty(
        confirmed_receipt_aux=0.5,
        pending_receipt_aux=0,
    )
    sug, pushed, rem = build_partial_push_aux_triplet(1, pushed_aux)
    assert (sug, pushed, rem) == (1.0, 0.5, 0.5)
