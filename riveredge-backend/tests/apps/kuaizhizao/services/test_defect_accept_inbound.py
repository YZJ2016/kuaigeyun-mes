"""让步接收处置：按检验类型生成入库单。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from apps.kuaizhizao.services.defect_record_service import DefectRecordService


def test_accept_routes_finished_goods_inspection_to_fg_receipt():
    defect = MagicMock(
        id=1,
        code="DF202609130001",
        product_id=100,
        defect_quantity=20,
        finished_goods_inspection_id=55,
        incoming_inspection_id=None,
        finished_goods_receipt_id=None,
        accept_purchase_receipt_id=None,
        other_inbound_id=None,
        save=AsyncMock(),
    )
    svc = DefectRecordService()
    with patch.object(
        svc,
        "_resolve_accept_material_and_warehouse",
        new=AsyncMock(return_value=("010001", "测试品", "件", 4, "成品仓")),
    ), patch.object(
        svc,
        "_execute_accept_via_finished_goods_receipt",
        new=AsyncMock(),
    ) as fg_mock, patch.object(
        svc,
        "_execute_accept_via_purchase_receipt",
        new=AsyncMock(),
    ) as pr_mock, patch.object(
        svc,
        "_execute_accept_via_other_inbound",
        new=AsyncMock(),
    ) as oi_mock:
        asyncio.run(
            svc._execute_accept_concession_inbound(
                1,
                defect,
                updated_by=7,
                stock_warehouse_id=4,
            )
        )

    fg_mock.assert_awaited_once()
    pr_mock.assert_not_awaited()
    oi_mock.assert_not_awaited()


def test_accept_routes_incoming_inspection_with_supplier_to_purchase_receipt():
    defect = MagicMock(
        id=1,
        code="DF202609130001",
        product_id=100,
        defect_quantity=20,
        finished_goods_inspection_id=None,
        incoming_inspection_id=88,
        finished_goods_receipt_id=None,
        accept_purchase_receipt_id=None,
        other_inbound_id=None,
        save=AsyncMock(),
    )
    inspection = MagicMock(supplier_id=9)
    svc = DefectRecordService()
    with patch.object(
        svc,
        "_resolve_accept_material_and_warehouse",
        new=AsyncMock(return_value=("010001", "测试品", "件", 4, "原料仓")),
    ), patch(
        "apps.kuaizhizao.models.incoming_inspection.IncomingInspection.get_or_none",
        new=AsyncMock(return_value=inspection),
    ), patch.object(
        svc,
        "_execute_accept_via_finished_goods_receipt",
        new=AsyncMock(),
    ) as fg_mock, patch.object(
        svc,
        "_execute_accept_via_purchase_receipt",
        new=AsyncMock(),
    ) as pr_mock, patch.object(
        svc,
        "_execute_accept_via_other_inbound",
        new=AsyncMock(),
    ) as oi_mock:
        asyncio.run(
            svc._execute_accept_concession_inbound(
                1,
                defect,
                updated_by=7,
                stock_warehouse_id=4,
            )
        )

    pr_mock.assert_awaited_once()
    fg_mock.assert_not_awaited()
    oi_mock.assert_not_awaited()


def test_accept_is_idempotent_when_linked():
    defect = MagicMock(
        finished_goods_receipt_id=10,
        accept_purchase_receipt_id=None,
        other_inbound_id=None,
    )
    svc = DefectRecordService()
    with patch.object(
        svc,
        "_resolve_accept_material_and_warehouse",
        new=AsyncMock(),
    ) as resolve_mock:
        asyncio.run(
            svc._execute_accept_concession_inbound(
                1,
                defect,
                updated_by=7,
                stock_warehouse_id=4,
            )
        )
    resolve_mock.assert_not_awaited()
