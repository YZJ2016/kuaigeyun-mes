"""采购入库行财务占用：金额/数量量化"""

from apps.kuaicaiwu.services.purchase_receipt_line_finance_occupancy_service import (
    _q_money,
    _q_qty,
)


def test_q_money_and_qty():
    assert _q_money("10.5") == _q_money("10.50")
    assert _q_qty("1.23456") == _q_qty("1.2346")
