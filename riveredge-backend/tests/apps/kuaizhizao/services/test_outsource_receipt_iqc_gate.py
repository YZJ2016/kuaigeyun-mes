"""KR-PG2：委外收货套用来料检验。无库，只测创建/确认分叉与检验单挂接。"""

from contextlib import ExitStack, asynccontextmanager, contextmanager
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaizhizao.schemas.outsource_work_order import OutsourceMaterialReceiptCreate
from apps.kuaizhizao.schemas.quality import IncomingInspectionUpdate
from apps.kuaizhizao.services.defect_record_service import DefectRecordService
from apps.kuaizhizao.services.outsource_material_receipt_service import (
    OutsourceMaterialReceiptService,
)
from apps.kuaizhizao.services.quality_service import IncomingInspectionService
from infra.exceptions.exceptions import BusinessLogicError


_txn_state = {"open": False, "rolled_back": False}


@asynccontextmanager
async def _txn():
    _txn_state["open"] = True
    _txn_state["rolled_back"] = False
    try:
        yield None
    except Exception:
        _txn_state["rolled_back"] = True
        raise
    finally:
        _txn_state["open"] = False


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
    wo.tenant_id = 1
    wo.product_id = product_id
    wo.unit_price = Decimal("2")
    wo.quantity = Decimal("10")
    wo.received_quantity = Decimal("0")
    wo.qualified_quantity = Decimal("0")
    wo.unqualified_quantity = Decimal("0")
    wo.status = "in_progress"
    wo.code = "OWO-1"
    wo.save = AsyncMock()
    return wo


def _service(wo):
    svc = OutsourceMaterialReceiptService()
    svc.get_user_info = AsyncMock(return_value={"name": "tester"})
    svc.get_user_name = AsyncMock(return_value="tester")
    svc._acquire_outsource_work_order_row_lock = AsyncMock(return_value=wo)
    svc._posting = {"stock": [], "cost": [], "payable": []}
    return svc


@contextmanager
def _posting_patches(svc, *, stock_error=None, cost_error=None, payable_error=None):
    state = svc._posting

    async def increase_stock(**kwargs):
        state["stock"].append({"in_txn": _txn_state["open"], "kwargs": kwargs})
        if stock_error is not None:
            raise stock_error

    async def on_cost(_self, tenant_id, receipt_id):
        state["cost"].append(
            {"in_txn": _txn_state["open"], "tenant_id": tenant_id, "receipt_id": receipt_id}
        )
        if cost_error is not None:
            raise cost_error

    async def payable(*_args, **kwargs):
        state["payable"].append({"in_txn": _txn_state["open"], "kwargs": kwargs})
        if payable_error is not None:
            raise payable_error

    svc._maybe_auto_create_payable_for_outsource_receipt = AsyncMock(side_effect=payable)
    with (
        patch(
            "apps.kuaizhizao.services.inventory_service.InventoryService.increase_stock",
            new=increase_stock,
        ),
        patch(
            "apps.kuaicaiwu.services.inventory_cost_service.InventoryCostService.on_outsource_receipt_confirmed",
            new=on_cost,
        ),
    ):
        yield state


def _assert_no_posting(svc):
    assert svc._posting["stock"] == []
    assert svc._posting["cost"] == []
    assert svc._posting["payable"] == []


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
        _posting_patches(svc),
    ):
        result = await svc.create_material_receipt(1, _receipt_create(), 8)

    assert result.status == "draft"
    assert create_mock.await_args.kwargs["status"] == "draft"
    wo.save.assert_not_awaited()
    assert wo.received_quantity == Decimal("0")
    assert wo.qualified_quantity == Decimal("0")
    _assert_no_posting(svc)


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
        _posting_patches(svc),
    ):
        result = await svc.create_material_receipt(1, _receipt_create(), 8)

    assert result.status == "completed"
    assert create_mock.await_args.kwargs["status"] == "completed"
    wo.save.assert_awaited()
    assert wo.received_quantity == Decimal("4")
    assert wo.qualified_quantity == Decimal("4")
    assert len(svc._posting["stock"]) == 1
    stock = svc._posting["stock"][0]
    assert stock["in_txn"] is True
    assert stock["kwargs"]["source_type"] == "outsource_material_receipt"
    assert stock["kwargs"]["source_doc_id"] == 77
    assert stock["kwargs"]["movement_type"] == "outsource_receipt"
    assert stock["kwargs"]["idempotency_key"] == "outsource_material_receipt:77:inc"
    assert svc._posting["cost"] == [
        {"in_txn": True, "tenant_id": 1, "receipt_id": 77}
    ]
    assert len(svc._posting["payable"]) == 1
    assert svc._posting["payable"][0]["in_txn"] is False


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
    receipt.warehouse_name = "主仓"
    receipt.unit = "件"
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
        _posting_patches(svc),
    ):
        with pytest.raises(BusinessLogicError, match="来料检验"):
            await svc.complete_material_receipt(1, 8, 4)

    assert receipt.status == "draft"
    receipt.save.assert_not_awaited()
    _assert_no_posting(svc)
    assert defect_filter.call_args.kwargs["disposition"] == "accept"
    assert defect_filter.call_args.kwargs["status"] == "processed"
    assert defect_filter.call_args.kwargs["incoming_inspection_id__in"] == [11]
    assert defect_filter.call_args.kwargs["tenant_id"] == 1


@pytest.mark.asyncio
async def test_complete_posts_after_passed_inspection():
    receipt = _draft_receipt()
    wo = _work_order()
    svc = _service(wo)
    inspection = SimpleNamespace(id=11, tenant_id=1, material_id=9)
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
        _posting_patches(svc),
    ):
        result = await svc.complete_material_receipt(1, 8, 4)

    assert result.status == "completed"
    assert receipt.status == "completed"
    receipt.save.assert_awaited()
    assert wo.received_quantity == Decimal("4")
    assert wo.qualified_quantity == Decimal("4")
    wo.save.assert_awaited()
    assert len(svc._posting["stock"]) == 1
    stock = svc._posting["stock"][0]
    assert stock["in_txn"] is True
    assert stock["kwargs"]["source_type"] == "outsource_material_receipt"
    assert stock["kwargs"]["material_id"] == 9
    assert stock["kwargs"]["movement_type"] == "outsource_receipt"
    assert stock["kwargs"]["idempotency_key"] == "outsource_material_receipt:8:inc"
    assert svc._posting["cost"] == [
        {"in_txn": True, "tenant_id": 1, "receipt_id": 8}
    ]
    assert len(svc._posting["payable"]) == 1
    assert svc._posting["payable"][0]["in_txn"] is False


@pytest.mark.asyncio
async def test_complete_posts_on_processed_accept_concession():
    receipt = _draft_receipt()
    wo = _work_order()
    svc = _service(wo)
    inspection = SimpleNamespace(id=11, tenant_id=1, material_id=9)
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
        _posting_patches(svc),
    ):
        result = await svc.complete_material_receipt(1, 8, 4)

    assert result.status == "completed"
    assert wo.received_quantity == Decimal("4")
    assert len(svc._posting["stock"]) == 1
    stock = svc._posting["stock"][0]
    assert stock["in_txn"] is True
    assert stock["kwargs"]["source_type"] == "outsource_material_receipt"
    assert stock["kwargs"]["source_doc_id"] == receipt.id
    assert svc._posting["cost"][0]["in_txn"] is True
    assert svc._posting["payable"][0]["in_txn"] is False


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
        _posting_patches(svc),
    ):
        result = await svc.complete_material_receipt(1, 8, 4)

    assert result.status == "completed"
    inspection_filter.assert_not_called()
    receipt.save.assert_not_awaited()
    _assert_no_posting(svc)


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


def _accept_defect():
    return SimpleNamespace(
        id=3,
        tenant_id=1,
        code="DF-1",
        disposition="accept",
        status="draft",
        defect_quantity=Decimal("1"),
        incoming_inspection_id=11,
        finished_goods_inspection_id=None,
        finished_goods_receipt_id=None,
        accept_purchase_receipt_id=None,
        other_inbound_id=None,
        processed_by=None,
        processed_at=None,
        processed_by_name=None,
        updated_by=None,
        updated_by_name=None,
        work_order_id=None,
        remarks=None,
        save=AsyncMock(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "inspection",
    [
        SimpleNamespace(
            id=11,
            source_type="outsource_material_receipt",
            outsource_material_receipt_id=8,
            supplier_id=5,
        ),
        SimpleNamespace(
            id=11,
            source_type="purchase_receipt",
            outsource_material_receipt_id=8,
            supplier_id=5,
        ),
    ],
)
async def test_outsource_concession_stays_processed_without_other_inbound(inspection):
    defect = _accept_defect()
    svc = DefectRecordService()
    svc.get_user_info = AsyncMock(return_value={"name": "tester"})
    svc._close_linked_quality_exceptions_after_disposition = AsyncMock()
    svc._resolve_accept_material_and_warehouse = AsyncMock(
        return_value=("P-9", "委外件", "件", 2, "主仓")
    )
    svc._execute_accept_via_purchase_receipt = AsyncMock()
    svc._execute_accept_via_other_inbound = AsyncMock()
    svc._execute_accept_via_finished_goods_receipt = AsyncMock()

    with (
        patch(
            "apps.kuaizhizao.services.defect_record_service.in_transaction",
            _txn,
        ),
        patch(
            "apps.kuaizhizao.services.defect_record_service.DefectRecord.get",
            new=AsyncMock(return_value=defect),
        ),
        patch(
            "apps.kuaizhizao.models.incoming_inspection.IncomingInspection.get_or_none",
            new=AsyncMock(return_value=inspection),
        ),
        patch(
            "apps.kuaizhizao.services.warehouse_service.PurchaseReceiptService"
        ) as purchase_cls,
        patch(
            "apps.kuaizhizao.services.warehouse_service.OtherInboundService"
        ) as other_cls,
    ):
        result = await svc._apply_disposition_after_persist(
            tenant_id=1,
            defect_id=3,
            updated_by=4,
            stock_warehouse_id=2,
        )

    assert result.status == "processed"
    assert result.disposition == "accept"
    assert result.accept_purchase_receipt_id is None
    assert result.other_inbound_id is None
    svc._execute_accept_via_purchase_receipt.assert_not_awaited()
    svc._execute_accept_via_other_inbound.assert_not_awaited()
    svc._execute_accept_via_finished_goods_receipt.assert_not_awaited()
    purchase_cls.assert_not_called()
    other_cls.assert_not_called()


@pytest.mark.asyncio
async def test_locked_assert_failure_keeps_draft():
    receipt = _draft_receipt()
    wo = _work_order()
    svc = _service(wo)
    inspection = SimpleNamespace(id=11, tenant_id=1, material_id=9)
    inspections = MagicMock()
    inspections.all = AsyncMock(return_value=[inspection])
    concessions = MagicMock()
    concessions.first = AsyncMock(return_value=None)
    events = []
    query = _receipt_query(receipt)
    locked = query.select_for_update.return_value

    async def locked_first():
        events.append("lock")
        return receipt

    locked.first = locked_first
    passes = {"n": 0}

    async def passed(_tenant_id, _inspection):
        passes["n"] += 1
        if passes["n"] == 1:
            assert "lock" not in events
            return True
        assert "lock" in events
        return False

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
            new=passed,
        ),
        patch(
            "apps.kuaizhizao.models.outsource_work_order.OutsourceMaterialReceipt.filter",
            return_value=query,
        ),
        patch(
            "apps.kuaizhizao.utils.inbound_confirm_helper.resolve_inbound_confirm_receiver",
            new=AsyncMock(return_value=(4, "tester")),
        ),
        patch(
            "apps.kuaizhizao.utils.inbound_confirm_helper.resolve_inbound_confirm_business_time",
            return_value=datetime(2026, 9, 30, 8, 0, 0),
        ),
        _posting_patches(svc),
    ):
        with pytest.raises(BusinessLogicError, match="来料检验"):
            await svc.complete_material_receipt(1, 8, 4)

    assert passes["n"] == 2
    assert receipt.status == "draft"
    receipt.save.assert_not_awaited()
    wo.save.assert_not_awaited()
    svc._acquire_outsource_work_order_row_lock.assert_awaited()
    _assert_no_posting(svc)


@pytest.mark.asyncio
async def test_complete_rejects_when_inspection_material_differs_from_work_order():
    receipt = _draft_receipt()
    wo = _work_order(product_id=9)
    svc = _service(wo)
    inspection = SimpleNamespace(id=11, tenant_id=1, material_id=8)
    inspections = MagicMock()
    inspections.all = AsyncMock(return_value=[inspection])
    query = _receipt_query(receipt)

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
            return_value=query,
        ),
        patch(
            "apps.kuaizhizao.utils.inbound_confirm_helper.resolve_inbound_confirm_receiver",
            new=AsyncMock(return_value=(4, "tester")),
        ),
        patch(
            "apps.kuaizhizao.utils.inbound_confirm_helper.resolve_inbound_confirm_business_time",
            return_value=datetime(2026, 9, 30, 8, 0, 0),
        ),
        _posting_patches(svc),
    ):
        with pytest.raises(BusinessLogicError, match="来料检验"):
            await svc.complete_material_receipt(1, 8, 4)

    assert query.select_for_update.called
    svc._acquire_outsource_work_order_row_lock.assert_awaited()
    assert receipt.status == "draft"
    receipt.save.assert_not_awaited()
    wo.save.assert_not_awaited()
    _assert_no_posting(svc)


def _complete_release_patches(receipt):
    inspection = SimpleNamespace(id=11, tenant_id=1, material_id=9)
    inspections = MagicMock()
    inspections.all = AsyncMock(return_value=[inspection])
    return (
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
    )


@contextmanager
def _confirm_posting(svc, receipt, **posting_kwargs):
    with ExitStack() as stack:
        for manager in _complete_release_patches(receipt):
            stack.enter_context(manager)
        stack.enter_context(_posting_patches(svc, **posting_kwargs))
        yield


@pytest.mark.asyncio
@pytest.mark.parametrize("which", ["stock", "cost"])
async def test_stock_or_cost_failure_rolls_back_completed_receipt(which):
    receipt = _draft_receipt()
    wo = _work_order()
    svc = _service(wo)
    stock_error = RuntimeError("stock down") if which == "stock" else None
    cost_error = RuntimeError("cost down") if which == "cost" else None

    with _confirm_posting(svc, receipt, stock_error=stock_error, cost_error=cost_error):
        with pytest.raises(RuntimeError):
            await svc.complete_material_receipt(1, 8, 4)

    assert _txn_state["rolled_back"] is True
    assert svc._posting["payable"] == []
    assert svc._posting["stock"][0]["in_txn"] is True
    if which == "cost":
        assert svc._posting["cost"][0]["in_txn"] is True


@pytest.mark.asyncio
async def test_payable_failure_raises_business_error_after_completed_commit():
    receipt = _draft_receipt()
    wo = _work_order()
    svc = _service(wo)

    with _confirm_posting(svc, receipt, payable_error=RuntimeError("payable down")):
        with pytest.raises(BusinessLogicError, match="已完成，但自动生成应付单失败"):
            await svc.complete_material_receipt(1, 8, 4)

    assert _txn_state["rolled_back"] is False
    assert receipt.status == "completed"
    assert svc._posting["stock"][0]["in_txn"] is True
    assert svc._posting["cost"][0]["in_txn"] is True
    assert svc._posting["payable"][0]["in_txn"] is False


@pytest.mark.asyncio
async def test_update_incoming_inspection_keeps_outsource_link():
    inspection_model = SimpleNamespace(
        inspection_result="待检验",
        source_type="outsource_material_receipt",
        outsource_material_receipt_id=8,
        outsource_material_receipt_code="OWR-1",
    )
    update_qs = MagicMock()
    update_qs.update = AsyncMock()
    svc = IncomingInspectionService()
    svc.get_user_info = AsyncMock(return_value={"name": "tester"})
    svc.get_incoming_inspection_by_id = AsyncMock(return_value=SimpleNamespace(id=21))

    with (
        patch(
            "apps.kuaizhizao.services.quality_service.in_transaction",
            _txn,
        ),
        patch(
            "apps.kuaizhizao.services.quality_service.IncomingInspection.get_or_none",
            new=AsyncMock(return_value=inspection_model),
        ),
        patch(
            "apps.kuaizhizao.services.document_action_policy.quality_inspection_record.assert_quality_inspection_capability"
        ),
        patch(
            "apps.kuaizhizao.services.quality_service.IncomingInspection.filter",
            return_value=update_qs,
        ),
    ):
        await svc.update_incoming_inspection(
            1,
            21,
            IncomingInspectionUpdate(
                notes="备注",
                source_type="purchase_receipt",
                outsource_material_receipt_id=99,
                outsource_material_receipt_code="OWR-HACK",
            ),
            4,
        )

    kwargs = update_qs.update.await_args.kwargs
    assert "source_type" not in kwargs
    assert "outsource_material_receipt_id" not in kwargs
    assert "outsource_material_receipt_code" not in kwargs
    assert kwargs["notes"] == "备注"
    assert inspection_model.source_type == "outsource_material_receipt"
    assert inspection_model.outsource_material_receipt_id == 8
    assert inspection_model.outsource_material_receipt_code == "OWR-1"
