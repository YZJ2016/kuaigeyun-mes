"""试算平衡合计：末级真源，轧卷展示不得双计（WPS D-15）。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaicaiwu.services.gl.balance_service import BalanceService


@pytest.mark.asyncio
async def test_trial_balance_totals_use_leaf_only_when_rows_rolled_up():
    child_credit = 198796.46
    child_row = {
        "account_id": 2,
        "opening_debit": 0.0,
        "opening_credit": child_credit,
        "period_debit": 0.0,
        "period_credit": 0.0,
        "ending_debit": 0.0,
        "ending_credit": child_credit,
    }
    parent_row = {
        "account_id": 1,
        "opening_debit": 0.0,
        "opening_credit": child_credit,
        "period_debit": 0.0,
        "period_credit": 0.0,
        "ending_debit": 0.0,
        "ending_credit": child_credit,
    }
    accounts = {
        1: SimpleNamespace(id=1, is_leaf=False),
        2: SimpleNamespace(id=2, is_leaf=True),
    }
    svc = BalanceService()

    async def mock_sheet(_tenant_id, _year, _month, **kwargs):
        if kwargs.get("rollup_hierarchy"):
            return [child_row, parent_row]
        return [child_row]

    with patch.object(svc, "_load_accounts_by_id", AsyncMock(return_value=accounts)):
        with patch.object(svc, "account_balance_sheet", side_effect=mock_sheet):
            trial = await svc.trial_balance(1, 2026, 5, expand_hierarchy=True)

    assert trial["opening_credit"] == pytest.approx(child_credit, abs=0.01)
    assert trial["opening_credit"] != pytest.approx(child_credit * 2, abs=0.01)
    assert len(trial["rows"]) == 2
    rolled_row_sum = sum(r["opening_credit"] for r in trial["rows"])
    assert rolled_row_sum == pytest.approx(child_credit * 2, abs=0.01)
