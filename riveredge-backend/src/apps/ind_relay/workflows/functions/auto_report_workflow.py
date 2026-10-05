"""继电器自动报工定时任务入口。"""

from __future__ import annotations

from typing import Any, Dict

from apps.ind_relay.services.auto_report_service import AutoReportService


async def run_ind_relay_auto_report_tick() -> Dict[str, Any]:
    return await AutoReportService.settle_all_tenants()
