"""出纳：银行对账查询自动同步企业账。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from apps.kuaicaiwu.services.gl.cashier_service import GlCashierService


def test_list_reconcile_items_syncs_enterprise_by_default():
    svc = GlCashierService()
    row = MagicMock()
    row.id = 1
    row.gl_account_id = 2
    row.period_year = 2026
    row.period_month = 9
    row.side = "enterprise"
    row.txn_date = None
    row.summary = "收款"
    row.debit_amount = 100
    row.credit_amount = 0
    row.is_opening = False
    row.is_matched = False
    row.match_group = None
    row.voucher_id = 10
    row.voucher_line_id = 11

    async def run():
        with patch.object(
            svc, "sync_enterprise_from_journal", new=AsyncMock(return_value={"created": 1})
        ) as sync_mock:
            q = MagicMock()
            q.filter.return_value = q
            q.order_by.return_value = q
            q.all = AsyncMock(return_value=[row])
            with patch(
                "apps.kuaicaiwu.services.gl.cashier_service.BankReconcileItem.filter",
                return_value=q,
            ):
                items = await svc.list_reconcile_items(1, 2, 2026, 9)
        sync_mock.assert_awaited_once_with(1, 2, 2026, 9)
        assert len(items) == 1
        assert items[0]["side"] == "enterprise"

    asyncio.run(run())


def test_list_reconcile_items_skips_sync_when_disabled():
    svc = GlCashierService()

    async def run():
        with patch.object(
            svc, "sync_enterprise_from_journal", new=AsyncMock()
        ) as sync_mock:
            q = MagicMock()
            q.filter.return_value = q
            q.order_by.return_value = q
            q.all = AsyncMock(return_value=[])
            with patch(
                "apps.kuaicaiwu.services.gl.cashier_service.BankReconcileItem.filter",
                return_value=q,
            ):
                await svc.list_reconcile_items(1, 2, 2026, 9, sync_enterprise=False)
        sync_mock.assert_not_awaited()

    asyncio.run(run())
