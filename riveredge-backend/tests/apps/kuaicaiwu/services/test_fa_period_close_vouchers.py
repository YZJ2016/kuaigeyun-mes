"""资产结账凭证汇总。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from apps.kuaicaiwu.services.fa_depreciation_service import FaPeriodCloseService


def test_collect_period_event_ids_from_payload_period():
    svc = FaPeriodCloseService()
    ev = MagicMock(id=10, payload={"period_year": 2024, "period_month": 9}, source_doc_type=None, event_date=None)

    async def run():
        with patch(
            "apps.kuaicaiwu.models.fixed_asset.FaDepreciationRun.filter"
        ) as run_filter, patch(
            "apps.kuaicaiwu.models.fixed_asset.FaDepreciationRunLine.filter"
        ) as line_filter, patch(
            "apps.kuaicaiwu.models.fixed_asset.FaDepreciationAdjustment.filter"
        ) as adj_filter, patch(
            "apps.kuaicaiwu.models.accounting_event.AccountingEvent.filter"
        ) as event_filter:
            run_q = MagicMock()
            run_q.values_list = AsyncMock(return_value=[])
            run_filter.return_value = run_q
            line_q = MagicMock()
            line_q.values_list = AsyncMock(return_value=[])
            line_filter.return_value = line_q
            adj_q = MagicMock()
            adj_q.values_list = AsyncMock(return_value=[])
            adj_filter.return_value = adj_q
            event_q = MagicMock()
            event_q.all = AsyncMock(return_value=[ev])
            event_filter.return_value = event_q
            return await svc._collect_period_event_ids(1, 2024, 9)

    assert asyncio.run(run()) == [10]
