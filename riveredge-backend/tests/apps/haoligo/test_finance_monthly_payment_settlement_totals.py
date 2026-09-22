"""本月付款明细：结算方式分项须与表体剩余应付同口径。"""

from decimal import Decimal

from apps.haoligo.services.finance_payable_report import build_remaining_totals_by_settlement


def test_build_remaining_totals_by_settlement_matches_detail_rows():
    rows = [
        {
            "settlement_method": "未设置",
            "remaining_amount": Decimal("16270.00"),
        },
        {
            "settlement_method": "未设置",
            "remaining_amount": Decimal("18200.00"),
        },
        {
            "settlement_method": "银行转账（先汇款后开票）",
            "remaining_amount": Decimal("100.00"),
        },
        {
            "settlement_method": "未设置",
            "remaining_amount": Decimal("0"),
        },
    ]
    totals = build_remaining_totals_by_settlement(rows)
    by_method = {r["settlement_method"]: r["total_amount"] for r in totals}
    assert by_method["未设置"] == Decimal("34470.00")
    assert by_method["银行转账（先汇款后开票）"] == Decimal("100.00")
    assert sum(by_method.values(), Decimal("0")) == Decimal("34570.00")
