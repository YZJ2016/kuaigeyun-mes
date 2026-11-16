"""采购入库价税 rollup 与立账策略门控（单元）。"""

from decimal import Decimal
from types import SimpleNamespace

from apps.kuaicaiwu.services.purchase_settlement import (
    compute_purchase_order_header_rollup,
    compute_purchase_receipt_header_rollup,
    compute_purchase_receipt_settlement_gross_from_lines,
    normalize_po_tax_rate_to_percent,
    proportional_line_gross,
    purchase_order_settlement_gross,
    purchase_receipt_header_out_of_sync,
    purchase_receipt_settlement_gross,
    resolve_purchase_receipt_line_excl_amount,
    rollup_purchase_receipt_header_tax,
)
from apps.kuaizhizao.services.document_recognition import (
    describe_purchase_receipt_payable_auto_skip,
    should_auto_payable_on_purchase_invoice,
    should_auto_payable_on_purchase_receipt,
)


def test_normalize_po_tax_rate_decimal_to_percent():
    assert normalize_po_tax_rate_to_percent(Decimal("0.13")) == Decimal("13.00")
    assert normalize_po_tax_rate_to_percent(13) == Decimal("13.00")


def test_compute_purchase_order_header_rollup_from_lines():
    order = SimpleNamespace(tax_rate=Decimal("0.13"), price_type="tax_exclusive")
    items = [
        SimpleNamespace(
            ordered_quantity=Decimal("10"),
            unit_price=Decimal("100"),
            total_price=Decimal("1000"),
            tax_rate=Decimal("13"),
        ),
    ]
    qty, excl, tax, net, rate = compute_purchase_order_header_rollup(order, items)
    assert qty == Decimal("10.0000")
    assert excl == Decimal("1000.00")
    assert tax == Decimal("130.00")
    assert net == Decimal("1130.00")
    assert rate == Decimal("0.13")


def test_inclusive_rollup_keeps_entered_unit_price():
    order = SimpleNamespace(tax_rate=Decimal("0.13"), price_type="tax_inclusive")
    items = [
        SimpleNamespace(
            ordered_quantity=Decimal("1"),
            unit_price=Decimal("530.9735"),
            display_unit_price=Decimal("600"),
            tax_rate=Decimal("13"),
        ),
    ]
    rolled = compute_purchase_order_header_rollup(order, items)
    assert rolled is not None
    _qty, _excl, _tax, net, _rate = rolled
    assert net == Decimal("600.00")


def test_inclusive_rollup_without_display_unit_price_does_not_rebuild():
    order = SimpleNamespace(tax_rate=Decimal("0.13"), price_type="tax_inclusive")
    items = [
        SimpleNamespace(
            ordered_quantity=Decimal("1"),
            unit_price=Decimal("530.9735"),
            display_unit_price=None,
            tax_rate=Decimal("13"),
        ),
    ]
    assert compute_purchase_order_header_rollup(order, items) is None


def test_compute_purchase_receipt_header_rollup_multi_line_matches_finance():
    """空白建单多行：头表 rollup 与各行未税+13% 汇总一致（CGSD 类漂移场景）。"""
    receipt = SimpleNamespace(tax_rate=Decimal("13"))
    lines = [
        SimpleNamespace(
            receipt_quantity=Decimal("1500"),
            unit_price=Decimal("0.53"),
            purchase_order_item_id=None,
            total_amount=Decimal("795"),
            tax_rate=Decimal("13"),
        ),
        SimpleNamespace(
            receipt_quantity=Decimal("10200"),
            unit_price=Decimal("0.84"),
            purchase_order_item_id=None,
            total_amount=Decimal("8568"),
            tax_rate=Decimal("13"),
        ),
    ]
    qty, excl, tax, net = compute_purchase_receipt_header_rollup(receipt, lines, {})
    assert excl == Decimal("9363.00")
    assert tax == Decimal("1217.19")
    assert net == Decimal("10580.19")
    header = SimpleNamespace(
        total_amount=Decimal("9363.00"),
        tax_amount=Decimal("1217.19"),
        net_amount=Decimal("10580.19"),
        total_quantity=qty,
    )
    assert not purchase_receipt_header_out_of_sync(
        header, total_qty=qty, excl=excl, tax_amt=tax, net_amt=net
    )
    stale = SimpleNamespace(
        total_amount=Decimal("9400"),
        tax_amount=Decimal("1222"),
        net_amount=Decimal("10622"),
        total_quantity=qty,
    )
    assert purchase_receipt_header_out_of_sync(
        stale, total_qty=qty, excl=excl, tax_amt=tax, net_amt=net
    )


def test_rollup_purchase_receipt_header_tax_13_percent():
    excl, tax, gross = rollup_purchase_receipt_header_tax(Decimal("1000"), Decimal("13"))
    assert excl == Decimal("1000.00")
    assert tax == Decimal("130.00")
    assert gross == Decimal("1130.00")


def test_purchase_receipt_settlement_gross_prefers_net_amount():
    receipt = SimpleNamespace(total_amount=Decimal("1000"), tax_rate=Decimal("13"), net_amount=Decimal("1130"))
    assert purchase_receipt_settlement_gross(receipt) == Decimal("1130.00")


def test_purchase_receipt_settlement_gross_from_po_line_avoids_qty_unit_tail():
    """PO 行未税 8849.56、入库 qty×单价 得 8849.60 时，比例分摊 rollup 应为 10000.00 而非 10000.05。"""
    receipt = SimpleNamespace(tax_rate=Decimal("13"))
    poi = SimpleNamespace(ordered_quantity=Decimal("1000"), total_price=Decimal("8849.56"))
    line = SimpleNamespace(
        receipt_quantity=Decimal("1000"),
        unit_price=Decimal("8.8496"),
        purchase_order_item_id=1,
        total_amount=Decimal("8849.60"),
    )
    gross = compute_purchase_receipt_settlement_gross_from_lines(
        receipt, [line], {1: poi}
    )
    assert gross == Decimal("10000.00")
    line_excl = resolve_purchase_receipt_line_excl_amount(
        receipt_quantity=Decimal("1000"),
        unit_price=Decimal("8.8496"),
        purchase_order_item_id=1,
        line_total_amount=Decimal("8849.60"),
        poi_by_id={1: poi},
    )
    assert line_excl == Decimal("8849.56")

    from apps.kuaicaiwu.services.purchase_settlement import (
        compute_purchase_receipt_line_settlement_amounts,
    )

    excl, tax, gross = compute_purchase_receipt_line_settlement_amounts(
        receipt, line, {1: poi}
    )
    assert excl == Decimal("8849.56")
    assert gross == Decimal("10000.00")
    assert excl + tax == gross


def test_purchase_order_settlement_gross_prefers_net_amount():
    order = SimpleNamespace(total_amount=Decimal("1000"), tax_rate=Decimal("0.13"), net_amount=Decimal("1130"))
    assert purchase_order_settlement_gross(order) == Decimal("1130.00")


def test_purchase_order_settlement_gross_rollups_from_excl():
    order = SimpleNamespace(total_amount=Decimal("1000"), tax_rate=Decimal("0.13"), net_amount=Decimal("0"))
    assert purchase_order_settlement_gross(order) == Decimal("1130.00")


def test_purchase_order_settlement_gross_uses_tax_amount_when_net_missing():
    order = SimpleNamespace(
        total_amount=Decimal("176.99"),
        tax_amount=Decimal("23.01"),
        tax_rate=Decimal("0"),
        net_amount=Decimal("0"),
    )
    assert purchase_order_settlement_gross(order) == Decimal("200.00")


def test_proportional_line_gross():
    line = proportional_line_gross(Decimal("400"), Decimal("1000"), Decimal("1130"))
    assert line == Decimal("452.00")


def test_on_purchase_invoice_skips_receipt_payable():
    assert should_auto_payable_on_purchase_receipt("on_purchase_invoice") is False
    assert should_auto_payable_on_purchase_receipt("on_receipt") is True
    assert should_auto_payable_on_purchase_invoice("on_purchase_invoice") is True
    assert should_auto_payable_on_purchase_invoice("on_receipt") is False
    reason = describe_purchase_receipt_payable_auto_skip("on_purchase_invoice")
    assert reason is not None
    assert "进项发票" in reason
