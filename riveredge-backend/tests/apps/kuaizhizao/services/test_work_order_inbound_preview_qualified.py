"""工单入库预览：启用 FQC 时展示合格数而非计划数。"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from apps.kuaizhizao.services.warehouse_service import FinishedGoodsReceiptService


def test_preview_quantities_use_fqc_qualified_not_planned():
    work_order = MagicMock(id=10, product_id=99, quantity=Decimal("200"), product_code="P1", product_name="测试品")

    quota = {
        "planned": 200.0,
        "max_quantity": 200.0,
        "received": 0.0,
        "pending": 200.0,
        "fqc_qualified_remaining": 180.0,
    }

    svc = FinishedGoodsReceiptService()
    with patch(
        "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
        new=AsyncMock(return_value=("plan", 1, None)),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.sum_fqc_inbound_qualified_quantity",
        new=AsyncMock(return_value=Decimal("180")),
    ):
        reference_qty, received, effective_pending, receipt_qty = asyncio.run(
            svc._resolve_work_order_inbound_preview_quantities(
                1,
                10,
                work_order,
                quota,
                suggested=180.0,
            )
        )

    assert reference_qty == 180.0
    assert received == 0.0
    assert effective_pending == 180.0
    assert receipt_qty == 180.0


def test_preview_quantities_zero_when_fqc_not_passed():
    work_order = MagicMock(id=10, product_id=99, quantity=Decimal("200"))

    quota = {
        "planned": 200.0,
        "max_quantity": 200.0,
        "received": 0.0,
        "pending": 200.0,
        "fqc_qualified_remaining": 0.0,
    }

    svc = FinishedGoodsReceiptService()
    with patch(
        "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
        new=AsyncMock(return_value=("plan", 1, None)),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.sum_fqc_inbound_qualified_quantity",
        new=AsyncMock(return_value=Decimal("0")),
    ):
        reference_qty, _, effective_pending, receipt_qty = asyncio.run(
            svc._resolve_work_order_inbound_preview_quantities(
                1,
                10,
                work_order,
                quota,
                suggested=0.0,
            )
        )

    assert reference_qty == 0.0
    assert effective_pending == 0.0
    assert receipt_qty == 0.0
