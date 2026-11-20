from apps.kuaizhizao.services.report_enhancements import (
    resolve_inventory_movement_report_doc_type,
    resolve_inventory_movement_report_quantities,
)


def test_fg_receipt_confirm_counts_as_inbound():
    qty_in, qty_out = resolve_inventory_movement_report_quantities(
        movement_type="fg_receipt",
        quantity=5.0,
    )
    assert qty_in == 5.0
    assert qty_out == 0.0


def test_fg_receipt_withdraw_reduces_inbound_not_outbound():
    qty_in, qty_out = resolve_inventory_movement_report_quantities(
        movement_type="fg_receipt_withdraw",
        quantity=-5.0,
    )
    assert qty_in == -5.0
    assert qty_out == 0.0


def test_legacy_finished_goods_revoke_other_outbound_reclassified():
    qty_in, qty_out = resolve_inventory_movement_report_quantities(
        movement_type="other_outbound",
        quantity=-5.0,
        source_doc_type="finished_goods_receipt_revoke",
    )
    assert qty_in == -5.0
    assert qty_out == 0.0


def test_production_issue_still_counts_as_outbound():
    qty_in, qty_out = resolve_inventory_movement_report_quantities(
        movement_type="production_issue",
        quantity=-3.0,
    )
    assert qty_in == 0.0
    assert qty_out == 3.0


def test_confirm_withdraw_reconfirm_net_inbound():
    events = [
        resolve_inventory_movement_report_quantities(movement_type="fg_receipt", quantity=5.0),
        resolve_inventory_movement_report_quantities(movement_type="fg_receipt_withdraw", quantity=-5.0),
        resolve_inventory_movement_report_quantities(movement_type="fg_receipt", quantity=5.0),
    ]
    inbound = sum(e[0] for e in events)
    outbound = sum(e[1] for e in events)
    assert inbound == 5.0
    assert outbound == 0.0


def test_legacy_finished_goods_revoke_doc_type_not_other_outbound():
    label = resolve_inventory_movement_report_doc_type(
        movement_type="other_outbound",
        source_doc_type="finished_goods_receipt_revoke",
        quantity=-5.0,
        default_labels={"other_outbound": "其他出库"},
    )
    assert label == "成品入库撤回"


def test_purchase_receipt_withdraw_doc_type():
    label = resolve_inventory_movement_report_doc_type(
        movement_type="purchase_receipt_withdraw",
        source_doc_type="purchase_receipt_revoke",
        quantity=-3.0,
    )
    assert label == "采购入库撤回"


def test_legacy_purchase_receipt_revoke_not_outbound_qty():
    qty_in, qty_out = resolve_inventory_movement_report_quantities(
        movement_type="other_outbound",
        quantity=-3.0,
        source_doc_type="purchase_receipt_revoke",
    )
    assert qty_in == -3.0
    assert qty_out == 0.0


def test_other_outbound_positive_qty_still_outbound_not_inbound():
    qty_in, qty_out = resolve_inventory_movement_report_quantities(
        movement_type="other_outbound",
        quantity=4.0,
    )
    assert qty_in == 0.0
    assert qty_out == 4.0


def test_sales_delivery_positive_qty_counts_outbound_only():
    qty_in, qty_out = resolve_inventory_movement_report_quantities(
        movement_type="sales_delivery",
        quantity=6.0,
    )
    assert qty_in == 0.0
    assert qty_out == 6.0


def test_sales_delivery_doc_type_label_chinese():
    label = resolve_inventory_movement_report_doc_type(
        movement_type="sales_delivery",
        source_doc_type="sales_delivery",
        quantity=-2.0,
    )
    assert label == "销售出库"


def test_unknown_movement_falls_back_source_doc_label():
    label = resolve_inventory_movement_report_doc_type(
        movement_type="",
        source_doc_type="other_outbound",
        quantity=-1.0,
    )
    assert label == "其他出库"
