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
