from apps.kuaizhizao.services.report_enhancements import (
    filter_inventory_movement_events_by_direction,
    resolve_inventory_movement_report_quantities,
)


def _event(movement_type: str, quantity: float, source_doc_type: str = "") -> dict:
    qty_in, qty_out = resolve_inventory_movement_report_quantities(
        movement_type=movement_type,
        quantity=quantity,
        source_doc_type=source_doc_type or None,
    )
    return {
        "movement_type": movement_type,
        "qty_in": qty_in,
        "qty_out": qty_out,
        "doc_type": movement_type,
    }


def test_inbound_detail_excludes_outbound_types_even_when_qty_positive():
    events = [
        _event("other_outbound", 4.0),
        _event("sales_delivery", 6.0),
        _event("other_inbound", 3.0),
        _event("fg_receipt", 5.0),
    ]
    inbound = filter_inventory_movement_events_by_direction(events, "inbound")
    assert len(inbound) == 2
    assert all(float(ev["qty_in"]) != 0 for ev in inbound)
    assert all(float(ev.get("qty_out") or 0) == 0 for ev in inbound)


def test_outbound_detail_excludes_inbound_types():
    events = [
        _event("other_outbound", 4.0),
        _event("other_inbound", 3.0),
        _event("fg_receipt_withdraw", -2.0),
    ]
    outbound = filter_inventory_movement_events_by_direction(events, "outbound")
    assert len(outbound) == 1
    assert outbound[0]["movement_type"] == "other_outbound"
    assert float(outbound[0]["qty_out"]) == 4.0


def test_dual_side_rows_excluded_from_both_detail_reports():
    dual = {"qty_in": 1.0, "qty_out": 1.0, "doc_type": "bad"}
    inbound = filter_inventory_movement_events_by_direction(
        [dual, _event("other_inbound", 2.0)],
        "inbound",
    )
    outbound = filter_inventory_movement_events_by_direction(
        [dual, _event("other_outbound", 2.0)],
        "outbound",
    )
    assert len(inbound) == 1
    assert len(outbound) == 1
    assert inbound[0]["movement_type"] == "other_inbound"
    assert outbound[0]["movement_type"] == "other_outbound"
