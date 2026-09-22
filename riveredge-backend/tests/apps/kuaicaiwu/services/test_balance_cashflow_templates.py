"""资产负债表 / 现金流量表标准模板。"""

from decimal import Decimal

from apps.kuaicaiwu.services.gl.balance_sheet_template import build_balance_sheet_rows
from apps.kuaicaiwu.services.gl.cash_flow_statement_template import build_cash_flow_rows
from apps.kuaicaiwu.services.gl.statement_service import signed_amount


def test_balance_sheet_template_totals():
    balance_rows = [
        {
            "account_id": 1,
            "account_code": "1001",
            "account_name": "库存现金",
            "account_type": "asset",
            "balance_direction": "debit",
            "opening_debit": 50,
            "opening_credit": 0,
            "ending_debit": 100,
            "ending_credit": 0,
        },
        {
            "account_id": 2,
            "account_code": "1002",
            "account_name": "银行存款",
            "account_type": "asset",
            "balance_direction": "debit",
            "opening_debit": 200,
            "opening_credit": 0,
            "ending_debit": 300,
            "ending_credit": 0,
        },
        {
            "account_id": 3,
            "account_code": "2001",
            "account_name": "短期借款",
            "account_type": "liability",
            "balance_direction": "credit",
            "opening_debit": 0,
            "opening_credit": 80,
            "ending_debit": 0,
            "ending_credit": 120,
        },
        {
            "account_id": 4,
            "account_code": "4001",
            "account_name": "实收资本",
            "account_type": "equity",
            "balance_direction": "credit",
            "opening_debit": 0,
            "opening_credit": 170,
            "ending_debit": 0,
            "ending_credit": 170,
        },
        {
            "account_id": 5,
            "account_code": "4103",
            "account_name": "本年利润",
            "account_type": "equity",
            "balance_direction": "credit",
            "opening_debit": 0,
            "opening_credit": 0,
            "ending_debit": 0,
            "ending_credit": 110,
        },
    ]
    rows, totals = build_balance_sheet_rows(balance_rows, signed_amount_fn=signed_amount)
    assert len(rows) == 32
    assert totals["total_assets"] == Decimal("400")
    assert totals["total_liabilities"] == Decimal("120")
    assert totals["total_equity"] == Decimal("280")
    assert totals["total_assets"] == totals["total_liabilities_and_equity"]
    last = rows[-1]
    assert last["asset"]["line_no"] == 30
    assert last["liability_equity"]["line_no"] == 53


def test_balance_sheet_includes_child_ar_ap_tax_accounts():
    """明细科目（1122xx / 2202xx / 2221xx）须计入对应报表行，不能因精确匹配漏掉。"""
    balance_rows = [
        {
            "account_id": 1,
            "account_code": "112201",
            "account_name": "应收账款-客户A",
            "account_type": "asset",
            "balance_direction": "debit",
            "opening_debit": 0,
            "opening_credit": 0,
            "ending_debit": 1500,
            "ending_credit": 0,
        },
        {
            "account_id": 2,
            "account_code": "220201",
            "account_name": "应付账款-供应商B",
            "account_type": "liability",
            "balance_direction": "credit",
            "opening_debit": 0,
            "opening_credit": 0,
            "ending_debit": 0,
            "ending_credit": 800,
        },
        {
            "account_id": 3,
            "account_code": "22210101",
            "account_name": "应交税费-应交增值税-销项税额",
            "account_type": "liability",
            "balance_direction": "credit",
            "opening_debit": 0,
            "opening_credit": 0,
            "ending_debit": 0,
            "ending_credit": 130,
        },
        {
            "account_id": 4,
            "account_code": "22210102",
            "account_name": "应交税费-应交增值税-进项税额",
            "account_type": "liability",
            "balance_direction": "credit",
            "opening_debit": 0,
            "opening_credit": 0,
            "ending_debit": 200,
            "ending_credit": 0,
        },
        {
            "account_id": 5,
            "account_code": "1001",
            "account_name": "库存现金",
            "account_type": "asset",
            "balance_direction": "debit",
            "opening_debit": 0,
            "opening_credit": 0,
            "ending_debit": 100,
            "ending_credit": 0,
        },
    ]
    rows, totals = build_balance_sheet_rows(balance_rows, signed_amount_fn=signed_amount)
    by_asset = {r["asset"]["line_key"]: r["asset"] for r in rows if r.get("asset")}
    by_le = {
        r["liability_equity"]["line_key"]: r["liability_equity"]
        for r in rows
        if r.get("liability_equity")
    }
    assert by_asset["a_04"]["ending_amount"] == 1500.0
    assert by_le["l_33"]["ending_amount"] == 800.0
    # 销项贷方 130 − 进项借方 200 = 应交税费 −70（借方余额以负号列示）
    assert by_le["l_36"]["ending_amount"] == -70.0
    assert totals["total_assets"] == Decimal("1600")
    assert totals["total_liabilities"] == Decimal("730")


def test_cash_flow_template_formulas():
    rows = build_cash_flow_rows(
        cf_period_by_code={
            "CF01": Decimal("1000"),
            "CF03": Decimal("-400"),
            "CF04": Decimal("-100"),
        },
        cf_year_by_code={
            "CF01": Decimal("5000"),
            "CF03": Decimal("-2000"),
            "CF04": Decimal("-500"),
        },
        cash_opening={"period": Decimal("200"), "year": Decimal("150")},
        cash_ending={"period": Decimal("700"), "year": Decimal("700")},
    )
    by_key = {row["line_key"]: row for row in rows}
    assert by_key["cf_07"]["period_amount"] == 500.0
    assert by_key["cf_07"]["year_amount"] == 2500.0
    assert by_key["cf_21"]["period_amount"] == 200.0
    assert by_key["cf_22"]["period_amount"] == 700.0
