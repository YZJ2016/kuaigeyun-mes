"""科目余额汇总：辅助核算合并与上下级轧卷。"""

from types import SimpleNamespace

from apps.kuaicaiwu.services.gl.balance_aggregate import (
    aggregate_balances_by_account,
    rollup_balances_to_ancestors,
)


def test_aggregate_balances_by_account_merges_customer_aux_rows():
    rows = [
        {
            "account_id": 10,
            "account_code": "6001",
            "account_name": "主营业务收入",
            "account_type": "profit_loss",
            "opening_debit": 0,
            "opening_credit": 0,
            "period_debit": 0,
            "period_credit": 92700,
            "year_debit": 0,
            "year_credit": 92700,
            "ending_debit": 0,
            "ending_credit": 92700,
            "customer_id": 1,
        },
        {
            "account_id": 10,
            "account_code": "6001",
            "account_name": "主营业务收入",
            "account_type": "profit_loss",
            "opening_debit": 0,
            "opening_credit": 0,
            "period_debit": 0,
            "period_credit": 9000,
            "year_debit": 0,
            "year_credit": 9000,
            "ending_debit": 0,
            "ending_credit": 9000,
            "customer_id": 2,
        },
    ]
    merged = aggregate_balances_by_account(rows)
    assert len(merged) == 1
    assert merged[0]["period_credit"] == 101700.0
    assert merged[0]["ending_credit"] == 101700.0


def test_rollup_balances_to_ancestors_includes_child_on_parent():
    parent = SimpleNamespace(
        id=1,
        parent_id=None,
        account_code="6001",
        account_name="主营业务收入",
        account_type="profit_loss",
    )
    child = SimpleNamespace(
        id=2,
        parent_id=1,
        account_code="600101",
        account_name="主营业务收入-产品",
        account_type="profit_loss",
    )
    accounts = {1: parent, 2: child}
    rows = [
        {
            "account_id": 2,
            "account_code": "600101",
            "account_name": child.account_name,
            "account_type": "profit_loss",
            "opening_debit": 0,
            "opening_credit": 0,
            "period_debit": 0,
            "period_credit": 101700,
            "year_debit": 0,
            "year_credit": 101700,
            "ending_debit": 0,
            "ending_credit": 101700,
        },
    ]
    rolled = rollup_balances_to_ancestors(rows, accounts)
    by_code = {r["account_code"]: r for r in rolled}
    assert by_code["600101"]["period_credit"] == 101700.0
    assert by_code["6001"]["period_credit"] == 101700.0


def test_rollup_nets_parent_opening_like_ending_for_taxes_payable():
    """父级期初与期末统一轧差；本期发生额保持借贷毛额。

    场景：子科目期初一借一贷同额可对冲，父级期初不应双边毛示。
    """
    parent = SimpleNamespace(
        id=1,
        parent_id=None,
        account_code="2221",
        account_name="应交税费",
        account_type="liability",
    )
    child_output = SimpleNamespace(
        id=2,
        parent_id=1,
        account_code="22210102",
        account_name="销项税额",
        account_type="liability",
    )
    child_transfer = SimpleNamespace(
        id=3,
        parent_id=1,
        account_code="22210105",
        account_name="转出未交增值税",
        account_type="liability",
    )
    child_other = SimpleNamespace(
        id=4,
        parent_id=1,
        account_code="22210199",
        account_name="其他税费",
        account_type="liability",
    )
    accounts = {
        1: parent,
        2: child_output,
        3: child_transfer,
        4: child_other,
    }
    rows = [
        {
            "account_id": 2,
            "account_code": "22210102",
            "account_name": child_output.account_name,
            "account_type": "liability",
            "opening_debit": 0,
            "opening_credit": 198796.46,
            "period_debit": 0,
            "period_credit": 0,
            "year_debit": 0,
            "year_credit": 0,
            "ending_debit": 0,
            "ending_credit": 198796.46,
        },
        {
            "account_id": 3,
            "account_code": "22210105",
            "account_name": child_transfer.account_name,
            "account_type": "liability",
            "opening_debit": 198796.46,
            "opening_credit": 0,
            "period_debit": 0,
            "period_credit": 0,
            "year_debit": 0,
            "year_credit": 0,
            "ending_debit": 198796.46,
            "ending_credit": 0,
        },
        {
            "account_id": 4,
            "account_code": "22210199",
            "account_name": child_other.account_name,
            "account_type": "liability",
            "opening_debit": 0,
            "opening_credit": 222652.03,
            "period_debit": 100,
            "period_credit": 50,
            "year_debit": 100,
            "year_credit": 50,
            "ending_debit": 0,
            "ending_credit": 222702.03,
        },
    ]
    rolled = rollup_balances_to_ancestors(rows, accounts)
    parent_row = next(r for r in rolled if r["account_code"] == "2221")
    # 期初：198796.46 借贷对冲后只剩贷 222652.03
    assert parent_row["opening_debit"] == 0.0
    assert parent_row["opening_credit"] == 222652.03
    # 本期发生额不轧差
    assert parent_row["period_debit"] == 100.0
    assert parent_row["period_credit"] == 50.0
    # 期末与期初+本期净额一致：贷 222652.03 + 50 - 100 = 222602.03
    assert parent_row["ending_debit"] == 0.0
    assert parent_row["ending_credit"] == 222602.03


def test_aggregate_nets_opening_when_aux_sides_oppose():
    rows = [
        {
            "account_id": 10,
            "account_code": "2221",
            "account_name": "应交税费",
            "account_type": "liability",
            "opening_debit": 0,
            "opening_credit": 100,
            "period_debit": 0,
            "period_credit": 0,
            "year_debit": 0,
            "year_credit": 0,
            "ending_debit": 0,
            "ending_credit": 100,
            "customer_id": 1,
        },
        {
            "account_id": 10,
            "account_code": "2221",
            "account_name": "应交税费",
            "account_type": "liability",
            "opening_debit": 40,
            "opening_credit": 0,
            "period_debit": 0,
            "period_credit": 0,
            "year_debit": 0,
            "year_credit": 0,
            "ending_debit": 40,
            "ending_credit": 0,
            "customer_id": 2,
        },
    ]
    merged = aggregate_balances_by_account(rows)
    assert len(merged) == 1
    assert merged[0]["opening_debit"] == 0.0
    assert merged[0]["opening_credit"] == 60.0
    assert merged[0]["ending_debit"] == 0.0
    assert merged[0]["ending_credit"] == 60.0
