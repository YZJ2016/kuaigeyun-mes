"""明细账：至少返回期初行；含未记账时纳入 draft/reviewed。"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from apps.kuaicaiwu.services.gl.balance_service import BalanceService


def test_detail_ledger_always_includes_opening_row():
    account = MagicMock(id=10, account_code="1001", account_name="库存现金")
    bal = MagicMock(
        opening_debit=Decimal("100"),
        opening_credit=Decimal("0"),
    )

    async def run():
        svc = BalanceService()
        with patch(
            "apps.kuaicaiwu.models.chart_of_account.ChartOfAccount.get_or_none",
            new=AsyncMock(return_value=account),
        ), patch(
            "apps.kuaicaiwu.models.voucher.Voucher.filter",
        ) as voucher_filter, patch(
            "apps.kuaicaiwu.models.account_balance.AccountBalance.get_or_none",
            new=AsyncMock(return_value=bal),
        ):
            voucher_q = MagicMock()
            voucher_q.order_by.return_value = voucher_q
            voucher_q.all = AsyncMock(return_value=[])
            voucher_filter.return_value = voucher_q

            return await svc.detail_ledger(1, 2026, 9, 10, include_unposted=False)

    result = asyncio.run(run())
    assert result["account_id"] == 10
    assert len(result["entries"]) == 1
    assert result["entries"][0]["kind"] == "opening"
    assert result["entries"][0]["summary"] == "期初余额"


def test_detail_ledger_include_unposted_expands_status_filter():
    account = MagicMock(id=10, account_code="1001", account_name="库存现金")

    async def run():
        svc = BalanceService()
        with patch(
            "apps.kuaicaiwu.models.chart_of_account.ChartOfAccount.get_or_none",
            new=AsyncMock(return_value=account),
        ), patch(
            "apps.kuaicaiwu.models.voucher.Voucher.filter",
        ) as voucher_filter, patch(
            "apps.kuaicaiwu.models.account_balance.AccountBalance.get_or_none",
            new=AsyncMock(return_value=None),
        ):
            voucher_q = MagicMock()
            voucher_q.order_by.return_value = voucher_q
            voucher_q.all = AsyncMock(return_value=[])
            voucher_filter.return_value = voucher_q

            await svc.detail_ledger(1, 2026, 9, 10, include_unposted=True)
            voucher_filter.assert_called_once()
            kwargs = voucher_filter.call_args.kwargs
            assert kwargs["status__in"] == ["draft", "reviewed", "posted"]

    asyncio.run(run())
