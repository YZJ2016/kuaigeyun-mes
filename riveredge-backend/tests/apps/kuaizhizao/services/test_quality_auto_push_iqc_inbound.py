"""来料检验合格后自动下推采购入库（组织配置）。"""

from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaizhizao.services.quality_automation_service import QualityAutomationService


@pytest.mark.asyncio
async def test_auto_push_skipped_when_config_off():
    svc = QualityAutomationService()
    with patch(
        "apps.kuaizhizao.services.quality_automation_service.get_quality_effective_config",
        new=AsyncMock(
            return_value={
                "stage_enabled": {"iqc": True},
                "module_enabled": {"incoming": True},
                "auto_push": {"purchase_receipt_after_iqc_pass": False},
            }
        ),
    ):
        await svc.maybe_auto_push_purchase_receipt_from_iqc(1, 99, 10)
