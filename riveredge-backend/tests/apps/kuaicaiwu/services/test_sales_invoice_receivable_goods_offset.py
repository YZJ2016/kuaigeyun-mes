"""应收单销项发票可开票金额：须扣减退货冲减。"""

from decimal import Decimal


def _preview_max_push(*, quantity: Decimal, pushed: Decimal, goods_offset: Decimal) -> float:
    offset = max(Decimal("0"), goods_offset)
    return float(max(Decimal("0"), quantity - pushed - offset))


def test_receivable_invoice_preview_subtracts_goods_offset():
    """与 SalesInvoiceService._build_preview_item 可开票公式一致。"""
    assert _preview_max_push(
        quantity=Decimal("300"),
        pushed=Decimal("0"),
        goods_offset=Decimal("150"),
    ) == 150.0


def test_receivable_invoice_preview_subtracts_invoiced_and_offset():
    assert _preview_max_push(
        quantity=Decimal("300"),
        pushed=Decimal("50"),
        goods_offset=Decimal("150"),
    ) == 100.0
