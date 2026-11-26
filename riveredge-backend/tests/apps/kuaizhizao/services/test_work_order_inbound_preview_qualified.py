"""工单入库预览：启用 FQC 时展示合格数而非计划数。"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


def test_preview_allows_create_pending_when_fqc_not_passed():
    """尚未 FQC 时仍可按计划/报工余量创建待入库单；确认入库另受 FQC 约束。"""
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
                suggested=120.0,
            )
        )

    assert reference_qty == 120.0
    assert effective_pending == 120.0
    assert receipt_qty == 120.0


def test_preview_quantities_batch_inbound_subtracts_received_when_no_fqc():
    """分批入库：累计报工 810、已入 310 → 可下推 500，数量列仍展示累计 810。"""
    work_order = MagicMock(id=10, product_id=99, quantity=Decimal("5000"))

    quota = {
        "planned": 5000.0,
        "max_quantity": 5000.0,
        "received": 310.0,
        "pending": 4690.0,
        "fqc_qualified_remaining": None,
    }

    svc = FinishedGoodsReceiptService()
    with patch(
        "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
        new=AsyncMock(return_value=("none", 0, None)),
    ):
        # suggested 已由 resolve 扣过已入库，此处传入剩余可下推 500
        reference_qty, received, effective_pending, receipt_qty = asyncio.run(
            svc._resolve_work_order_inbound_preview_quantities(
                1,
                10,
                work_order,
                quota,
                suggested=500.0,
            )
        )

    assert reference_qty == 810.0
    assert received == 310.0
    assert effective_pending == 500.0
    assert receipt_qty == 500.0


def test_suggested_receipt_quantity_subtracts_already_received():
    """建议入库量 = 累计合格/报工 − 已入库（分批场景）。"""
    work_order = MagicMock(id=10, product_id=99)
    last_op = MagicMock(id=1, sequence=10, operation_id=77, qualified_quantity=Decimal("810"))

    svc = FinishedGoodsReceiptService()

    async def _run():
        with patch(
            "apps.kuaizhizao.models.work_order.WorkOrder.get_or_none",
            new=AsyncMock(return_value=work_order),
        ), patch(
            "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
            new=AsyncMock(return_value=("none", 0, None)),
        ), patch(
            "apps.kuaizhizao.models.finished_goods_inspection.FinishedGoodsInspection.filter",
            return_value=MagicMock(all=AsyncMock(return_value=[])),
        ), patch(
            "apps.kuaizhizao.models.work_order_operation.WorkOrderOperation.filter",
            return_value=MagicMock(all=AsyncMock(return_value=[last_op])),
        ), patch.object(
            svc,
            "_sum_work_order_inbound_quantity",
            new=AsyncMock(return_value=310.0),
        ):
            return await svc._resolve_work_order_suggested_receipt_quantity(
                1, 10, strict=False
            )

    assert asyncio.run(_run()) == 500.0
