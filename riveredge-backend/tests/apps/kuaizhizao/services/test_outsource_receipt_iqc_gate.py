"""KR-PG2：委外收货套用来料检验。无库，只测创建/确认分叉与检验单挂接。"""

from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaizhizao.schemas.outsource_work_order import OutsourceMaterialReceiptCreate
from apps.kuaizhizao.services.outsource_material_receipt_service import (
    OutsourceMaterialReceiptService,
)
from apps.kuaizhizao.services.quality_service import IncomingInspectionService
from infra.exceptions.exceptions import BusinessLogicError


@asynccontextmanager
async def _txn():
    yield None


def _receipt_create() -> OutsourceMaterialReceiptCreate:
    return OutsourceMaterialReceiptCreate(
        code="OWR-TEST-0001",
        outsource_work_order_id=3,
        outsource_work_order_code="OWO-1",
        quantity=Decimal("5"),
        qualified_quantity=Decimal("4"),
        unqualified_quantity=Decimal("1"),
        unit="件",
        warehouse_id=2,
        warehouse_name="主仓",
    )


def _work_order(*, product_id=9):
    wo = MagicMock()
    wo.id = 3
    wo.product_id = product_id
    wo.unit_price = Decimal("2")
    wo.quantity = Decimal("10")
    wo.received_quantity = Decimal("0")
    wo.qualified_quantity = Decimal("0")
    wo.unqualified_quantity = Decimal("0")
    wo.status = "in_progress"
    wo.save = AsyncMock()
    return wo


def _service(wo):
    svc = OutsourceMaterialReceiptService()
    svc.get_user_info = AsyncMock(return_value={"name": "tester"})
    svc.get_user_name = AsyncMock(return_value="tester")
    svc._acquire_outsource_work_order_row_lock = AsyncMock(return_value=wo)
    svc._schedule_stock_for_outsource_receipt = MagicMock()
    svc._schedule_cost_for_outsource_receipt = MagicMock()
    svc._schedule_auto_payable_for_outsource_receipt = MagicMock()
    return svc


def _created_receipt():
    created = MagicMock()
    created.id = 77
    created.code = "OWR-TEST-0001"
    created.refresh_from_db = AsyncMock()
    return created


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "policy",
    [
        ("none", None, "default_none"),
        ("simple", 1, "material"),
        ("plan", 2, "material"),
    ],
)
async def test_required_receipt_stays_draft_without_posting(policy):
    wo = _work_order()
    svc = _service(wo)
    created = _created_receipt()
    wo_qs = MagicMock()
    wo_qs.first = AsyncMock(return_value=wo)
    receipt_qs = MagicMock()
    receipt_qs.first = AsyncMock(return_value=None)

    with (
        patch(
            "apps.kuaizhizao.services.document_action_policy.outsource_work_order.assert_outsource_work_order_capability"
        ),
        patch(
            "apps.kuaizhizao.services.outsource_material_receipt_service.in_transaction",
            _txn,
        ),
        patch(
            "apps.kuaizhizao.models.outsource_work_order.OutsourceWorkOrder.filter",
            return_value=wo_qs,
        ),
        patch(
            "apps.kuaizhizao.models.outsource_work_order.OutsourceMaterialReceipt.filter",
            return_value=receipt_qs,
        ),
        patch(
            "apps.kuaizhizao.models.outsource_work_order.OutsourceMaterialReceipt.create",
            new=AsyncMock(return_value=created),
        ) as create_mock,
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
            new=AsyncMock(return_value=policy),
        ),
        patch(
            "apps.kuaizhizao.schemas.outsource_work_order.OutsourceMaterialReceiptResponse.model_validate",
            return_value=SimpleNamespace(status="draft"),
        ),
    ):
        result = await svc.create_material_receipt(1, _receipt_create(), 8)

    assert result.status == "draft"
    assert create_mock.await_args.kwargs["status"] == "draft"
    wo.save.assert_not_awaited()
    assert wo.received_quantity == Decimal("0")
    assert wo.qualified_quantity == Decimal("0")
    svc._schedule_stock_for_outsource_receipt.assert_not_called()
    svc._schedule_cost_for_outsource_receipt.assert_not_called()
    svc._schedule_auto_payable_for_outsource_receipt.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "policy",
    [
        ("none", None, "material"),
        ("none", None, "stage_disabled"),
        ("none", None, "module_disabled"),
    ],
)
async def test_exempt_receipt_completes_and_posts(policy):
    wo = _work_order()
    svc = _service(wo)
    created = _created_receipt()
    wo_qs = MagicMock()
    wo_qs.first = AsyncMock(return_value=wo)
    receipt_qs = MagicMock()
    receipt_qs.first = AsyncMock(return_value=None)

    with (
        patch(
            "apps.kuaizhizao.services.document_action_policy.outsource_work_order.assert_outsource_work_order_capability"
        ),
        patch(
            "apps.kuaizhizao.services.outsource_material_receipt_service.in_transaction",
            _txn,
        ),
        patch(
            "apps.kuaizhizao.models.outsource_work_order.OutsourceWorkOrder.filter",
            return_value=wo_qs,
        ),
        patch(
            "apps.kuaizhizao.models.outsource_work_order.OutsourceMaterialReceipt.filter",
            return_value=receipt_qs,
        ),
        patch(
            "apps.kuaizhizao.models.outsource_work_order.OutsourceMaterialReceipt.create",
            new=AsyncMock(return_value=created),
        ) as create_mock,
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
            new=AsyncMock(return_value=policy),
        ),
        patch(
            "apps.kuaizhizao.schemas.outsource_work_order.OutsourceMaterialReceiptResponse.model_validate",
            side_effect=lambda obj: SimpleNamespace(status=create_mock.await_args.kwargs["status"]),
        ),
    ):
        result = await svc.create_material_receipt(1, _receipt_create(), 8)

    assert result.status == "completed"
    assert create_mock.await_args.kwargs["status"] == "completed"
    wo.save.assert_awaited()
    assert wo.received_quantity == Decimal("4")
    assert wo.qualified_quantity == Decimal("4")
    stock = svc._schedule_stock_for_outsource_receipt.call_args.args[0]
    assert stock["source_type"] == "outsource_material_receipt"
    assert stock["source_doc_id"] == 77
    svc._schedule_auto_payable_for_outsource_receipt.assert_called_once()
    svc._schedule_cost_for_outsource_receipt.assert_called_once()


def _draft_receipt():
    receipt = MagicMock()
    receipt.id = 8
    receipt.tenant_id = 1
    receipt.status = "draft"
    receipt.code = "OWR-1"
    receipt.outsource_work_order_id = 3
    receipt.qualified_quantity = Decimal("4")
    receipt.unqualified_quantity = Decimal("1")
    receipt.quantity = Decimal("5")
    receipt.warehouse_id = 2
    receipt.batch_number = None
    receipt.received_at = None
    receipt.save = AsyncMock()
    receipt.refresh_from_db = AsyncMock()
    return receipt


def _receipt_query(receipt):
    locked = MagicMock()
    locked.first = AsyncMock(return_value=receipt)
    query = MagicMock()
    query.first = AsyncMock(return_value=receipt)
    query.select_for_update = MagicMock(return_value=locked)
    return query


@pytest.mark.asyncio
async def test_complete_rejects_without_passed_inspection_or_processed_concession():
    receipt = _draft_receipt()
    svc = _service(_work_order())
    inspection = SimpleNamespace(id=11, tenant_id=1)
    inspections = MagicMock()
    inspections.all = AsyncMock(return_value=[inspection])
    concessions = MagicMock()
    concessions.first = AsyncMock(return_value=None)

    with (
        patch(
            "apps.kuaizhizao.services.document_action_policy.warehouse_inbound_hub.assert_inbound_hub_capability"
        ),
        patch(
            "apps.kuaizhizao.models.incoming_inspection.IncomingInspection.filter",
            return_value=inspections,
        ),
        patch(
            "apps.kuaizhizao.models.defect_record.DefectRecord.filter",
            return_value=concessions,
        ) as defect_filter,
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.iqc_inspection_passed_for_inbound",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "apps.kuaizhizao.models.outsource_work_order.OutsourceMaterialReceipt.filter",
            return_value=_receipt_query(receipt),
        ),
    ):
        with pytest.raises(BusinessLogicError, match="来料检验"):
            await svc.complete_material_receipt(1, 8, 4)

    assert receipt.status == "draft"
    receipt.save.assert_not_awaited()
    svc._schedule_stock_for_outsource_receipt.assert_not_called()
    svc._schedule_auto_payable_for_outsource_receipt.assert_not_called()
    assert defect_filter.call_args.kwargs["disposition"] == "accept"
    assert defect_filter.call_args.kwargs["status"] == "processed"
    assert defect_filter.call_args.kwargs["incoming_inspection_id__in"] == [11]
    assert defect_filter.call_args.kwargs["tenant_id"] == 1


@pytest.mark.asyncio
async def test_complete_posts_after_passed_inspection():
    receipt = _draft_receipt()
    wo = _work_order()
    svc = _service(wo)
    inspection = SimpleNamespace(id=11, tenant_id=1)
    inspections = MagicMock()
    inspections.all = AsyncMock(return_value=[inspection])

    with (
        patch(
            "apps.kuaizhizao.services.document_action_policy.warehouse_inbound_hub.assert_inbound_hub_capability"
        ),
        patch(
            "apps.kuaizhizao.services.outsource_material_receipt_service.in_transaction",
            _txn,
        ),
        patch(
            "apps.kuaizhizao.models.incoming_inspection.IncomingInspection.filter",
            return_value=inspections,
        ),
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.iqc_inspection_passed_for_inbound",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "apps.kuaizhizao.models.outsource_work_order.OutsourceMaterialReceipt.filter",
            return_value=_receipt_query(receipt),
        ),
        patch(
            "apps.kuaizhizao.utils.inbound_confirm_helper.resolve_inbound_confirm_receiver",
            new=AsyncMock(return_value=(4, "tester")),
        ),
        patch(
            "apps.kuaizhizao.utils.inbound_confirm_helper.resolve_inbound_confirm_business_time",
            return_value=datetime(2026, 9, 30, 8, 0, 0),
        ),
        patch(
            "apps.kuaizhizao.schemas.outsource_work_order.OutsourceMaterialReceiptResponse.model_validate",
            side_effect=lambda obj: SimpleNamespace(status=obj.status),
        ),
    ):
        result = await svc.complete_material_receipt(1, 8, 4)

    assert result.status == "completed"
    assert receipt.status == "completed"
    receipt.save.assert_awaited()
    assert wo.received_quantity == Decimal("4")
    assert wo.qualified_quantity == Decimal("4")
    wo.save.assert_awaited()
    stock = svc._schedule_stock_for_outsource_receipt.call_args.args[0]
    assert stock["source_type"] == "outsource_material_receipt"
    assert stock["material_id"] == 9
    svc._schedule_auto_payable_for_outsource_receipt.assert_called_once()


@pytest.mark.asyncio
async def test_complete_posts_on_processed_accept_concession():
    receipt = _draft_receipt()
    wo = _work_order()
    svc = _service(wo)
    inspection = SimpleNamespace(id=11, tenant_id=1)
    inspections = MagicMock()
    inspections.all = AsyncMock(return_value=[inspection])
    concessions = MagicMock()
    concessions.first = AsyncMock(return_value=SimpleNamespace(id=3, tenant_id=1, status="processed"))

    with (
        patch(
            "apps.kuaizhizao.services.document_action_policy.warehouse_inbound_hub.assert_inbound_hub_capability"
        ),
        patch(
            "apps.kuaizhizao.services.outsource_material_receipt_service.in_transaction",
            _txn,
        ),
        patch(
            "apps.kuaizhizao.models.incoming_inspection.IncomingInspection.filter",
            return_value=inspections,
        ),
        patch(
            "apps.kuaizhizao.models.defect_record.DefectRecord.filter",
            return_value=concessions,
        ),
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.iqc_inspection_passed_for_inbound",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "apps.kuaizhizao.models.outsource_work_order.OutsourceMaterialReceipt.filter",
            return_value=_receipt_query(receipt),
        ),
        patch(
            "apps.kuaizhizao.utils.inbound_confirm_helper.resolve_inbound_confirm_receiver",
            new=AsyncMock(return_value=(4, "tester")),
        ),
        patch(
            "apps.kuaizhizao.utils.inbound_confirm_helper.resolve_inbound_confirm_business_time",
            return_value=datetime(2026, 9, 30, 8, 0, 0),
        ),
        patch(
            "apps.kuaizhizao.schemas.outsource_work_order.OutsourceMaterialReceiptResponse.model_validate",
            side_effect=lambda obj: SimpleNamespace(status=obj.status),
        ),
    ):
        result = await svc.complete_material_receipt(1, 8, 4)

    assert result.status == "completed"
    assert wo.received_quantity == Decimal("4")
    svc._schedule_stock_for_outsource_receipt.assert_called_once()


@pytest.mark.asyncio
async def test_complete_already_completed_returns_without_gate_or_posting():
    receipt = _draft_receipt()
    receipt.status = "completed"
    svc = _service(_work_order())

    with (
        patch(
            "apps.kuaizhizao.models.outsource_work_order.OutsourceMaterialReceipt.filter",
            return_value=_receipt_query(receipt),
        ),
        patch(
            "apps.kuaizhizao.models.incoming_inspection.IncomingInspection.filter"
        ) as inspection_filter,
        patch(
            "apps.kuaizhizao.schemas.outsource_work_order.OutsourceMaterialReceiptResponse.model_validate",
            side_effect=lambda obj: SimpleNamespace(status=obj.status),
        ),
    ):
        result = await svc.complete_material_receipt(1, 8, 4)

    assert result.status == "completed"
    inspection_filter.assert_not_called()
    receipt.save.assert_not_awaited()
    svc._schedule_stock_for_outsource_receipt.assert_not_called()


@pytest.mark.asyncio
async def test_normalize_legacy_draft_does_not_rewrite_status_or_receiver():
    receipt = _draft_receipt()
    receipt.received_by = None
    receipt.received_by_name = None
    svc = OutsourceMaterialReceiptService()

    await svc._normalize_legacy_draft_receipts([receipt])

    assert receipt.status == "draft"
    assert receipt.received_by is None
    assert receipt.received_by_name is None
    receipt.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_inspection_from_draft_outsource_receipt_links_source():
    receipt = _draft_receipt()
    receipt.unit = "件"
    work_order = SimpleNamespace(
        id=3,
        tenant_id=1,
        product_id=9,
        product_code="P-9",
        product_name="委外件",
        supplier_id=5,
        supplier_name="供应商甲",
    )
    inspections = MagicMock()
    inspections.first = AsyncMock(return_value=None)
    created = SimpleNamespace(id=21, inspection_code="IQ001")
    svc = IncomingInspectionService()
    svc.generate_code = AsyncMock(return_value="IQ001")
    svc.get_user_name = AsyncMock(return_value="tester")

    with (
        patch(
            "apps.kuaizhizao.services.quality_service._require_iqc_stage_enabled",
            new=AsyncMock(),
        ),
        patch(
            "apps.kuaizhizao.services.quality_service._get_quality_policy_flags",
            new=AsyncMock(return_value=(True, False)),
        ),
        patch(
            "apps.kuaizhizao.services.quality_service.in_transaction",
            _txn,
        ),
        patch(
            "apps.kuaizhizao.models.outsource_work_order.OutsourceMaterialReceipt.get_or_none",
            new=AsyncMock(return_value=receipt),
        ),
        patch(
            "apps.kuaizhizao.models.outsource_work_order.OutsourceWorkOrder.get_or_none",
            new=AsyncMock(return_value=work_order),
        ),
        patch(
            "apps.kuaizhizao.services.quality_service.IncomingInspection.filter",
            return_value=inspections,
        ),
        patch(
            "apps.master_data.models.material.Material.get_or_none",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "apps.kuaizhizao.services.quality_service._resolve_inspection_template_fields",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "apps.kuaizhizao.services.quality_service._quality_inspection_initial_review_fields",
            new=AsyncMock(return_value={"review_status": ""}),
        ),
        patch(
            "apps.kuaizhizao.services.quality_service.IncomingInspection.create",
            new=AsyncMock(return_value=created),
        ) as create_mock,
        patch(
            "apps.kuaizhizao.services.quality_service.IncomingInspectionResponse.model_validate",
            side_effect=lambda obj: obj,
        ),
    ):
        rows = await svc.create_inspection_from_outsource_material_receipt(1, 8, 4)

    assert rows == [created]
    kwargs = create_mock.await_args.kwargs
    assert kwargs["source_type"] == "outsource_material_receipt"
    assert kwargs["outsource_material_receipt_id"] == 8
    assert kwargs["outsource_material_receipt_code"] == "OWR-1"
    assert kwargs["tenant_id"] == 1
    assert kwargs["material_id"] == 9
    assert kwargs["inspection_quantity"] == Decimal("5")
