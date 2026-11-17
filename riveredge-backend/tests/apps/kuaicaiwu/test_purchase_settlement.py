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
    # 百分数 1% 不得被当成小数 1.0 抬成 100%
    assert normalize_po_tax_rate_to_percent(Decimal("1")) == Decimal("1.00")
    assert normalize_po_tax_rate_to_percent(1) == Decimal("1.00")
    # 头表小数 1%（0.01）仍换算为 1
    assert normalize_po_tax_rate_to_percent(Decimal("0.01")) == Decimal("1.00")


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


def test_purchase_receipt_standalone_tax_inclusive_display_unit_price():
    from apps.kuaicaiwu.services.purchase_settlement import (
        compute_purchase_receipt_line_settlement_amounts,
    )

    receipt = SimpleNamespace(tax_rate=Decimal("0.13"))
    line = SimpleNamespace(
        receipt_quantity=Decimal("1"),
        unit_price=Decimal("53.098"),
        display_unit_price=Decimal("60"),
        tax_rate=Decimal("13"),
        purchase_order_item_id=None,
        total_amount=Decimal("53.10"),
    )
    excl, tax, gross = compute_purchase_receipt_line_settlement_amounts(
        receipt, line, {},
    )
    assert gross == Decimal("60.00")
    assert excl == Decimal("53.10")
    assert tax == Decimal("6.90")


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


def test_receipt_settlement_gross_aligns_with_purchase_order_rollup():
    """多行入库价税合计应与采购订单头 net_amount（按行 qty×单价 rollup）一致，避免 456.00 vs 455.99。"""
    from types import SimpleNamespace

    from apps.kuaicaiwu.services.purchase_settlement import (
        compute_purchase_order_header_rollup,
        compute_purchase_receipt_settlement_gross_from_lines,
        purchase_order_item_settlement_gross,
        purchase_order_settlement_gross,
    )

    order = SimpleNamespace(tax_rate=Decimal("0.13"), price_type="tax_exclusive")
    lines_po = [
        SimpleNamespace(
            ordered_quantity=Decimal("8"),
            unit_price=Decimal("22.5660"),
            tax_rate=Decimal("13"),
            display_unit_price=None,
            total_price=Decimal("180.5280"),
            order_id=1,
            id=101,
        ),
        SimpleNamespace(
            ordered_quantity=Decimal("12"),
            unit_price=Decimal("22.8940"),
            tax_rate=Decimal("13"),
            display_unit_price=None,
            total_price=Decimal("274.7280"),
            order_id=1,
            id=102,
        ),
    ]
    _, _, _, po_net, _ = compute_purchase_order_header_rollup(order, lines_po)
    assert purchase_order_settlement_gross(
        SimpleNamespace(
            total_amount=Decimal("455.2560"),
            tax_amount=Decimal("59.18"),
            tax_rate=Decimal("0.13"),
            net_amount=po_net,
        )
    ) == po_net

    receipt = SimpleNamespace(tax_rate=Decimal("13"))
    receipt_lines = [
        SimpleNamespace(
            receipt_quantity=Decimal("8"),
            unit_price=Decimal("22.5660"),
            purchase_order_item_id=101,
            total_amount=Decimal("180.5280"),
        ),
        SimpleNamespace(
            receipt_quantity=Decimal("12"),
            unit_price=Decimal("22.8940"),
            purchase_order_item_id=102,
            total_amount=Decimal("274.7280"),
        ),
    ]
    poi_by_id = {101: lines_po[0], 102: lines_po[1]}
    order_by_id = {1: order}
    gross_legacy = Decimal("0")
    for poi in lines_po:
        share_excl = Decimal(str(poi.total_price))
        poi_gross = purchase_order_item_settlement_gross(order, poi)
        from apps.kuaicaiwu.services.purchase_settlement import (
            compute_tax_from_excluding,
            resolve_purchase_receipt_line_excl_amount,
        )

        excl = resolve_purchase_receipt_line_excl_amount(
            receipt_quantity=Decimal(str(poi.ordered_quantity)),
            unit_price=Decimal(str(poi.unit_price)),
            purchase_order_item_id=int(poi.id),
            line_total_amount=share_excl,
            poi_by_id=poi_by_id,
        )
        _, tax, _ = compute_tax_from_excluding(excl, Decimal("13"))
        gross_legacy += excl + tax

    gross_new = compute_purchase_receipt_settlement_gross_from_lines(
        receipt, receipt_lines, poi_by_id, purchase_order_by_id=order_by_id
    )
    from apps.kuaicaiwu.services.finance_tax import quantize_money

    gross_legacy = quantize_money(gross_legacy)
    assert gross_new == po_net
    assert gross_legacy <= po_net


def test_on_purchase_invoice_skips_receipt_payable():
    assert should_auto_payable_on_purchase_receipt("on_purchase_invoice") is False
    assert should_auto_payable_on_purchase_receipt("on_receipt") is True
    assert should_auto_payable_on_purchase_invoice("on_purchase_invoice") is True
    assert should_auto_payable_on_purchase_invoice("on_receipt") is False
    reason = describe_purchase_receipt_payable_auto_skip("on_purchase_invoice")
    assert reason is not None
    assert "进项发票" in reason
