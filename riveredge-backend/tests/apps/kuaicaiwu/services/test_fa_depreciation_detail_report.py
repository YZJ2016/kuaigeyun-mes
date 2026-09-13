"""固定资产折旧明细报表。"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from apps.kuaicaiwu.services.fa_depreciation_service import FaDepreciationService


def test_depreciation_detail_report_net_value():
    line = MagicMock(
        id=1,
        run_id=10,
        asset_id=100,
        asset_code="FA001",
        asset_name="设备A",
        calculated_amount=Decimal("7500"),
        final_amount=Decimal("7500"),
    )
    run = MagicMock(
        id=10,
        status="confirmed",
        period_year=2024,
        period_month=9,
        run_code="FDR202409120001",
        confirmed_by_name="tester",
        confirmed_at=None,
    )
    asset = MagicMock(
        id=100,
        category_name="机器",
        department_name="生产部",
        user_name="张三",
        original_value=Decimal("500000"),
        accumulated_depreciation=Decimal("37600"),
        impairment_value=Decimal("100"),
        expense_account_code="5101",
    )

    svc = FaDepreciationService()

    async def run_report():
        with patch(
            "apps.kuaicaiwu.services.fa_depreciation_service.FaDepreciationRunLine.filter"
        ) as line_filter, patch(
            "apps.kuaicaiwu.services.fa_depreciation_service.FaDepreciationRun.filter"
        ) as run_filter, patch(
            "apps.kuaicaiwu.services.fa_depreciation_service.FaAsset.filter"
        ) as asset_filter:
            line_q = MagicMock()
            line_q.order_by.return_value.limit = AsyncMock(return_value=[line])
            line_filter.return_value = line_q
            run_q = MagicMock()
            run_q.all = AsyncMock(return_value=[run])
            run_filter.return_value = run_q
            asset_q = MagicMock()
            asset_q.all = AsyncMock(return_value=[asset])
            asset_filter.return_value = asset_q
            return await svc.depreciation_detail_report(1)

    rows = asyncio.run(run_report())
    assert len(rows) == 1
    assert rows[0]["net_value"] == 462300.0
