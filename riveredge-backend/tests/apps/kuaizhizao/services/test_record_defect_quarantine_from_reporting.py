"""报工登记不良：隔离处置未传仓库时由副作用解析待检仓。"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from apps.kuaizhizao.schemas.defect_record import DefectRecordCreateFromReporting
from apps.kuaizhizao.services.defect_record_service import DefectRecordService


def test_apply_disposition_quarantine_without_warehouse_id_allowed():
    defect = MagicMock(
        id=1,
        disposition="quarantine",
        incoming_inspection_id=None,
        work_order_id=10,
        operation_id=1,
    )
    svc = DefectRecordService()
    with patch(
        "apps.kuaizhizao.models.defect_record.DefectRecord.get",
        new=AsyncMock(return_value=defect),
    ), patch.object(
        svc,
        "_validate_disposition_choice",
        return_value=None,
    ), patch.object(
        svc,
        "_execute_disposition_side_effects",
        new=AsyncMock(),
    ) as side_effects_mock, patch.object(
        svc,
        "_mark_disposition_processed",
        new=AsyncMock(),
    ), patch(
        "tortoise.transactions.in_transaction",
        return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
    ):
        asyncio.run(
            svc._apply_disposition_after_persist(
                1,
                1,
                updated_by=7,
                quarantine_warehouse_id=None,
            )
        )
    side_effects_mock.assert_awaited_once()
