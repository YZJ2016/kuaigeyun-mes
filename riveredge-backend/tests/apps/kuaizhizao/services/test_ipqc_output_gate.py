"""KR-PG6：关键工序未检验不得算工序完成或报产出。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaizhizao.services.operation_transfer_service import (
    resolve_key_operation_output_quantity,
    resolve_operation_transfer_qualified,
)
from apps.kuaizhizao.services.quality_automation_service import QualityAutomationService
from apps.kuaizhizao.services.reporting_service import (
    ReportingService,
    _apply_key_last_operation_header_output,
    _mark_approved_operation_completion,
    _maybe_mark_operation_completed,
)
from apps.kuaizhizao.services.work_order_service import WorkOrderService


def _cfg(*, ipqc_stage=True, process_module=True, auto_ipqc=True):
    return {
        "stage_enabled": {"iqc": True, "ipqc": ipqc_stage, "fqc": True, "oqc": True},
        "module_enabled": {
            "incoming": True,
            "process": process_module,
            "finished": True,
            "defect_handling": True,
        },
        "auto_create": {"ipqc_on_reporting": auto_ipqc},
        "gate": {},
        "fai": {},
    }


def _woo(**kwargs):
    data = {
        "id": 2,
        "sequence": 1,
        "operation_id": 1,
        "qualified_quantity": Decimal("80"),
        "unqualified_quantity": Decimal("0"),
        "completed_quantity": Decimal("80"),
        "status": "in_progress",
        "reporting_type": "quantity",
        "actual_end_date": None,
        "inspection_mode": None,
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def _wo(**kwargs):
    data = {"id": 10, "quantity": Decimal("80"), "status": "in_progress", "code": "WO1"}
    data.update(kwargs)
    return SimpleNamespace(**data)


def _qs(rows):
    class _Query:
        def __init__(self, items):
            self.items = items

        async def all(self):
            return self.items

    return _Query(rows)


def _patch_policy(mode, source, *, ipqc_stage=True, process_module=True):
    return (
        patch(
            "apps.kuaizhizao.services.operation_transfer_service.resolve_inspection_policy",
            new=AsyncMock(return_value=(mode, None, source)),
        ),
        patch(
            "apps.kuaizhizao.services.operation_transfer_service.get_quality_effective_config",
            new=AsyncMock(return_value=_cfg(ipqc_stage=ipqc_stage, process_module=process_module)),
        ),
    )


@pytest.mark.asyncio
async def test_simple_uninspected_does_not_complete():
    woo = _woo(inspection_mode="simple", qualified_quantity=Decimal("80"))
    work_order = _wo(quantity=Decimal("80"))
    policy, cfg = _patch_policy("simple", "operation")
    with policy, cfg, patch(
        "apps.kuaizhizao.models.process_inspection.ProcessInspection.filter",
        return_value=_qs([]),
    ):
        transfer = await resolve_operation_transfer_qualified(1, 10, woo, audit_required=False)
        marked = await _maybe_mark_operation_completed(1, work_order, woo)
    assert transfer == Decimal("0")
    assert marked is False
    assert woo.status == "in_progress"


@pytest.mark.asyncio
async def test_status_reporting_on_key_operation_does_not_complete_without_release():
    woo = _woo(inspection_mode="simple", reporting_type="status")
    work_order = _wo()
    policy, cfg = _patch_policy("simple", "operation")
    with policy, cfg, patch(
        "apps.kuaizhizao.models.process_inspection.ProcessInspection.filter",
        return_value=_qs([]),
    ):
        became = await _mark_approved_operation_completion(
            1,
            work_order,
            woo,
            reporting_type="status",
            reported_quantity=Decimal("80"),
        )
    assert became is False
    assert woo.status == "in_progress"


@pytest.mark.asyncio
async def test_status_reporting_on_non_key_still_completes_when_quantity_positive():
    woo = _woo(inspection_mode=None, reporting_type="status", qualified_quantity=Decimal("1"))
    work_order = _wo(quantity=Decimal("80"))
    policy, cfg = _patch_policy("none", "default_none")
    with policy, cfg:
        became = await _mark_approved_operation_completion(
            1,
            work_order,
            woo,
            reporting_type="status",
            reported_quantity=Decimal("1"),
        )
    assert became is True
    assert woo.status == "completed"


@pytest.mark.asyncio
async def test_plan_unfinished_does_not_complete_and_transfer_excludes_concession():
    woo = _woo(inspection_mode="plan", qualified_quantity=Decimal("80"))
    inspection = SimpleNamespace(
        id=5,
        status="待检验",
        qualified_quantity=Decimal("0"),
        quality_status="待检",
        review_status=None,
        inspection_code="PQ1",
        notes="",
        inspection_plan_id=1,
    )
    work_order = _wo()
    policy, cfg = _patch_policy("plan", "operation")
    with policy, cfg, patch(
        "apps.kuaizhizao.models.process_inspection.ProcessInspection.filter",
        return_value=_qs([inspection]),
    ):
        transfer = await resolve_operation_transfer_qualified(
            1,
            10,
            woo,
            audit_required=False,
        )
        marked = await _maybe_mark_operation_completed(1, work_order, woo)
    assert transfer == Decimal("0")
    assert marked is False
    assert woo.status == "in_progress"


@pytest.mark.asyncio
async def test_none_still_completes_from_reported_qualified():
    woo = _woo(
        inspection_mode=None,
        qualified_quantity=Decimal("80"),
        completed_quantity=Decimal("80"),
    )
    work_order = _wo(quantity=Decimal("80"))
    policy, cfg = _patch_policy("none", "default_none")
    with policy, cfg:
        transfer = await resolve_operation_transfer_qualified(1, 10, woo)
        marked = await _maybe_mark_operation_completed(1, work_order, woo)
    assert transfer == Decimal("80")
    assert marked is True
    assert woo.status == "completed"


@pytest.mark.asyncio
async def test_stage_disabled_still_uses_reported_qualified():
    woo = _woo(inspection_mode="simple", qualified_quantity=Decimal("80"))
    policy, cfg = _patch_policy("simple", "operation", ipqc_stage=False)
    with policy, cfg:
        transfer = await resolve_operation_transfer_qualified(1, 10, woo)
        output = await resolve_key_operation_output_quantity(1, 10, woo)
    assert transfer == Decimal("80")
    assert output is None


@pytest.mark.asyncio
async def test_module_disabled_still_uses_reported_qualified():
    woo = _woo(inspection_mode="plan", qualified_quantity=Decimal("40"))
    policy, cfg = _patch_policy("plan", "operation", process_module=False)
    with policy, cfg:
        transfer = await resolve_operation_transfer_qualified(1, 10, woo)
    assert transfer == Decimal("40")


@pytest.mark.asyncio
async def test_work_order_override_to_simple_is_key_operation():
    woo = _woo(inspection_mode=None, qualified_quantity=Decimal("80"))
    policy, cfg = _patch_policy("simple", "work_order_override")
    with policy, cfg:
        transfer = await resolve_operation_transfer_qualified(
            1, 10, woo, inspections_by_op={1: []}, audit_required=False
        )
    assert transfer == Decimal("0")


@pytest.mark.asyncio
async def test_processed_concession_counts_as_output_not_transfer():
    woo = _woo(inspection_mode="plan", qualified_quantity=Decimal("80"))
    inspection = SimpleNamespace(
        id=5,
        status="已检验",
        qualified_quantity=Decimal("10"),
        quality_status="不合格",
        review_status="通过",
        inspection_code="PQ1",
        notes="",
        inspection_plan_id=1,
    )
    defects = [
        SimpleNamespace(
            defect_quantity=Decimal("3"),
            disposition="accept",
            status="processed",
            process_inspection_id=5,
        ),
        SimpleNamespace(
            defect_quantity=Decimal("9"),
            disposition="accept",
            status="draft",
            process_inspection_id=5,
        ),
    ]

    def _filter(**kwargs):
        rows = defects
        for key in ("disposition", "status"):
            if key in kwargs:
                rows = [row for row in rows if getattr(row, key) == kwargs[key]]
        if "process_inspection_id__in" in kwargs:
            allowed = set(kwargs["process_inspection_id__in"])
            rows = [row for row in rows if row.process_inspection_id in allowed]
        return _qs(rows)

    policy, cfg = _patch_policy("plan", "operation")
    with policy, cfg, patch(
        "apps.kuaizhizao.models.defect_record.DefectRecord.filter",
        side_effect=_filter,
    ):
        transfer = await resolve_operation_transfer_qualified(
            1,
            10,
            woo,
            inspections_by_op={1: [inspection]},
            audit_required=False,
        )
        output = await resolve_key_operation_output_quantity(
            1,
            10,
            woo,
            inspections_by_op={1: [inspection]},
            audit_required=False,
        )
    assert transfer == Decimal("10")
    assert output == Decimal("13")


@pytest.mark.asyncio
async def test_key_last_operation_zero_output_does_not_copy_reported_qualified():
    woo = _woo(inspection_mode="simple")
    work_order = _wo()
    work_order.completed_quantity = Decimal("80")
    work_order.qualified_quantity = Decimal("80")
    policy, cfg = _patch_policy("simple", "operation")
    with policy, cfg:
        await _apply_key_last_operation_header_output(
            1,
            work_order,
            woo,
            inspections_by_op={1: []},
        )
    assert work_order.completed_quantity == Decimal("0")
    assert work_order.qualified_quantity == Decimal("0")


@pytest.mark.asyncio
async def test_sync_header_does_not_write_reported_qualified_for_uninspected_key_last_op():
    woo = _woo(inspection_mode="simple", sequence=2, id=2, operation_id=9)
    work_order = _wo()
    work_order.completed_quantity = Decimal("80")
    work_order.qualified_quantity = Decimal("80")
    policy, cfg = _patch_policy("simple", "operation")
    with policy, cfg, patch(
        "apps.kuaizhizao.services.reporting_service.WorkOrderOperation.filter",
        return_value=_qs([woo]),
    ), patch(
        "apps.kuaizhizao.services.operation_transfer_service.build_operation_policy_cache",
        new=AsyncMock(return_value={9: ("simple", None, "operation")}),
    ), patch(
        "apps.kuaizhizao.services.operation_transfer_service.load_process_inspections_by_operation",
        new=AsyncMock(return_value={9: []}),
    ):
        await ReportingService()._sync_work_order_header_quantities_from_last_operation(
            1, work_order
        )
    assert work_order.completed_quantity == Decimal("0")
    assert work_order.qualified_quantity == Decimal("0")


@pytest.mark.asyncio
async def test_non_key_header_keeps_reported_quantities():
    woo = _woo(inspection_mode=None, completed_quantity=Decimal("80"), qualified_quantity=Decimal("70"))
    work_order = _wo()
    work_order.completed_quantity = Decimal("1")
    work_order.qualified_quantity = Decimal("1")
    policy, cfg = _patch_policy("none", "module_disabled", process_module=False)
    with policy, cfg:
        await _apply_key_last_operation_header_output(1, work_order, woo)
    assert work_order.completed_quantity == Decimal("1")
    assert work_order.qualified_quantity == Decimal("1")


@pytest.mark.asyncio
async def test_simple_auto_create_calls_process_inspection_and_swallows_failure():
    woo = SimpleNamespace(operation_id=1, operation_name="装配", inspection_mode="simple")
    work_order = SimpleNamespace(id=10, code="WO1")
    record = SimpleNamespace(id=3, status="approved")
    create = AsyncMock(side_effect=RuntimeError("建单失败"))
    with patch(
        "apps.kuaizhizao.services.quality_automation_service.get_quality_effective_config",
        new=AsyncMock(return_value=_cfg()),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
        new=AsyncMock(return_value=("simple", None, "operation")),
    ), patch(
        "apps.kuaizhizao.services.quality_service.ProcessInspectionService"
    ) as service_cls:
        service_cls.return_value.create_inspection_from_work_order = create
        await QualityAutomationService().maybe_auto_create_ipqc_fqc_from_reporting(
            1, work_order, woo, record, 7
        )
    create.assert_awaited_once()
    assert record.status == "approved"


@pytest.mark.asyncio
async def test_plan_auto_create_still_creates_process_inspection():
    woo = SimpleNamespace(operation_id=1, operation_name="装配")
    work_order = SimpleNamespace(id=10, code="WO1")
    record = SimpleNamespace(id=3)
    create = AsyncMock()
    with patch(
        "apps.kuaizhizao.services.quality_automation_service.get_quality_effective_config",
        new=AsyncMock(return_value=_cfg()),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
        new=AsyncMock(return_value=("plan", 4, "operation")),
    ), patch(
        "apps.kuaizhizao.services.quality_service.ProcessInspectionService"
    ) as service_cls:
        service_cls.return_value.create_inspection_from_work_order = create
        await QualityAutomationService().maybe_auto_create_ipqc_fqc_from_reporting(
            1, work_order, woo, record, 7
        )
    create.assert_awaited_once()


@pytest.mark.asyncio
async def test_none_auto_create_does_not_create_process_inspection():
    woo = SimpleNamespace(operation_id=1, operation_name="装配")
    work_order = SimpleNamespace(id=10, code="WO1")
    record = SimpleNamespace(id=3)
    create = AsyncMock()
    with patch(
        "apps.kuaizhizao.services.quality_automation_service.get_quality_effective_config",
        new=AsyncMock(return_value=_cfg()),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
        new=AsyncMock(return_value=("none", None, "default_none")),
    ), patch(
        "apps.kuaizhizao.services.quality_service.ProcessInspectionService"
    ) as service_cls:
        service_cls.return_value.create_inspection_from_work_order = create
        await QualityAutomationService().maybe_auto_create_ipqc_fqc_from_reporting(
            1, work_order, woo, record, 7
        )
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_key_last_operation_does_not_auto_inbound_when_output_is_zero():
    record = SimpleNamespace(
        id=3,
        status="approved",
        qualified_quantity=Decimal("80"),
        work_order_id=10,
        operation_id=1,
        work_order_code="WO1",
        operation_name="装配",
        inbound_warehouse_id=9,
        inbound_warehouse_name="成品仓",
    )
    quick = AsyncMock()
    svc = ReportingService()
    with patch(
        "apps.kuaizhizao.services.reporting_service.ReportingRecord.get_or_none",
        new=AsyncMock(return_value=record),
    ), patch(
        "apps.kuaizhizao.services.reporting_service.BusinessConfigService.get_last_operation_auto_inbound_mode",
        new=AsyncMock(return_value="direct_inbound"),
    ), patch.object(
        svc, "_is_last_operation_for_work_order", new=AsyncMock(return_value=True)
    ), patch(
        "apps.kuaizhizao.services.reporting_service._resolve_work_order_operation_for_reporting",
        new=AsyncMock(return_value=_woo(inspection_mode="simple")),
    ), patch(
        "apps.kuaizhizao.services.operation_transfer_service.resolve_key_operation_output_quantity",
        new=AsyncMock(return_value=Decimal("0")),
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.FinishedGoodsReceiptService"
    ) as receipt_cls:
        receipt_cls.return_value.quick_receipt_from_work_order = quick
        result = await svc._maybe_trigger_direct_finished_goods_inbound(1, 3, 7)
    assert result is None
    quick.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_key_last_operation_auto_inbound_uses_reported_qualified():
    record = SimpleNamespace(
        id=3,
        status="approved",
        qualified_quantity=Decimal("7"),
        work_order_id=10,
        operation_id=1,
        work_order_code="WO1",
        operation_name="装配",
        inbound_warehouse_id=9,
        inbound_warehouse_name="成品仓",
    )
    receipt = SimpleNamespace(id=4, receipt_code="FG1")
    quick = AsyncMock(return_value=receipt)
    confirm = AsyncMock(return_value=receipt)
    svc = ReportingService()
    with patch(
        "apps.kuaizhizao.services.reporting_service.ReportingRecord.get_or_none",
        new=AsyncMock(return_value=record),
    ), patch(
        "apps.kuaizhizao.services.reporting_service.BusinessConfigService.get_last_operation_auto_inbound_mode",
        new=AsyncMock(return_value="direct_inbound"),
    ), patch.object(
        svc, "_is_last_operation_for_work_order", new=AsyncMock(return_value=True)
    ), patch(
        "apps.kuaizhizao.services.reporting_service._resolve_work_order_operation_for_reporting",
        new=AsyncMock(return_value=_woo(inspection_mode=None)),
    ), patch(
        "apps.kuaizhizao.services.operation_transfer_service.resolve_key_operation_output_quantity",
        new=AsyncMock(return_value=None),
    ), patch.object(
        svc, "_direct_inbound_receipt_exists_for_reporting", new=AsyncMock(return_value=False)
    ), patch(
        "apps.kuaizhizao.services.reporting_service.WorkOrder.get_or_none",
        new=AsyncMock(return_value=SimpleNamespace(id=10, status="in_progress", product_id=1, code="WO1")),
    ), patch(
        "apps.kuaizhizao.services.reporting_service.is_semi_finished_product_by_bom_role",
        new=AsyncMock(return_value=False),
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.FinishedGoodsReceiptService"
    ) as receipt_cls, patch(
        "apps.kuaizhizao.services.document_relation_new_service.DocumentRelationNewService"
    ) as relation_cls:
        receipt_cls.return_value.quick_receipt_from_work_order = quick
        receipt_cls.return_value.confirm_receipt = confirm
        relation_cls.return_value.create_relation = AsyncMock()
        result = await svc._maybe_trigger_direct_finished_goods_inbound(1, 3, 7)
    assert result is not None
    assert result.outcome == "confirmed"
    quick.assert_awaited_once()
    assert quick.await_args.kwargs["receipt_quantity"] == 7.0


def _approved_last_report(**kwargs):
    data = {
        "id": 3,
        "status": "approved",
        "qualified_quantity": Decimal("80"),
        "work_order_id": 10,
        "operation_id": 1,
        "work_order_code": "WO1",
        "operation_name": "装配",
        "inbound_warehouse_id": 9,
        "inbound_warehouse_name": "成品仓",
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def _defect_filter(defects):
    def _filter(**kwargs):
        rows = defects
        for key in ("disposition", "status"):
            if key in kwargs:
                rows = [row for row in rows if getattr(row, key) == kwargs[key]]
        if "process_inspection_id__in" in kwargs:
            allowed = set(kwargs["process_inspection_id__in"])
            rows = [row for row in rows if row.process_inspection_id in allowed]
        return _qs(rows)

    return _filter


@pytest.mark.asyncio
async def test_key_last_operation_auto_inbound_uses_unreceived_increment():
    first = _approved_last_report(id=3)
    second = _approved_last_report(id=8)
    records = {3: first, 8: second}
    outputs = {3: Decimal("10"), 8: Decimal("15")}
    occupied = {3: Decimal("0"), 8: Decimal("10")}
    receipt = SimpleNamespace(id=4, receipt_code="FG1")
    quick = AsyncMock(return_value=receipt)
    confirm = AsyncMock(return_value=receipt)
    svc = ReportingService()

    async def get_record(**kwargs):
        return records[kwargs["id"]]

    async def key_output(*_args, **_kwargs):
        return outputs[svc_call["record_id"]]

    async def occupied_qty(*_args, **_kwargs):
        return occupied[svc_call["record_id"]]

    svc_call = {"record_id": 3}

    async def trigger(record_id):
        svc_call["record_id"] = record_id
        return await svc._maybe_trigger_direct_finished_goods_inbound(1, record_id, 7)

    with patch(
        "apps.kuaizhizao.services.reporting_service.ReportingRecord.get_or_none",
        new=get_record,
    ), patch(
        "apps.kuaizhizao.services.reporting_service.BusinessConfigService.get_last_operation_auto_inbound_mode",
        new=AsyncMock(return_value="direct_inbound"),
    ), patch.object(
        svc, "_is_last_operation_for_work_order", new=AsyncMock(return_value=True)
    ), patch(
        "apps.kuaizhizao.services.reporting_service._resolve_work_order_operation_for_reporting",
        new=AsyncMock(return_value=_woo(inspection_mode="simple")),
    ), patch(
        "apps.kuaizhizao.services.operation_transfer_service.resolve_key_operation_output_quantity",
        new=key_output,
    ), patch.object(
        svc, "_sum_direct_inbound_quantity_for_work_order", new=occupied_qty
    ), patch.object(
        svc, "_direct_inbound_receipt_exists_for_reporting", new=AsyncMock(return_value=False)
    ), patch(
        "apps.kuaizhizao.services.reporting_service.WorkOrder.get_or_none",
        new=AsyncMock(return_value=SimpleNamespace(id=10, status="in_progress", product_id=1, code="WO1")),
    ), patch(
        "apps.kuaizhizao.services.reporting_service.is_semi_finished_product_by_bom_role",
        new=AsyncMock(return_value=False),
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.FinishedGoodsReceiptService"
    ) as receipt_cls, patch(
        "apps.kuaizhizao.services.document_relation_new_service.DocumentRelationNewService"
    ) as relation_cls:
        receipt_cls.return_value.quick_receipt_from_work_order = quick
        receipt_cls.return_value.confirm_receipt = confirm
        relation_cls.return_value.create_relation = AsyncMock()
        first_result = await trigger(3)
        second_result = await trigger(8)

    assert first_result.outcome == "confirmed"
    assert second_result.outcome == "confirmed"
    assert [call.kwargs["receipt_quantity"] for call in quick.await_args_list] == [10.0, 5.0]


@pytest.mark.asyncio
async def test_key_last_operation_second_report_skips_inbound_when_output_still_zero():
    records = {
        3: _approved_last_report(id=3),
        8: _approved_last_report(id=8),
    }
    quick = AsyncMock()
    svc = ReportingService()

    async def get_record(**kwargs):
        return records[kwargs["id"]]

    with patch(
        "apps.kuaizhizao.services.reporting_service.ReportingRecord.get_or_none",
        new=get_record,
    ), patch(
        "apps.kuaizhizao.services.reporting_service.BusinessConfigService.get_last_operation_auto_inbound_mode",
        new=AsyncMock(return_value="direct_inbound"),
    ), patch.object(
        svc, "_is_last_operation_for_work_order", new=AsyncMock(return_value=True)
    ), patch(
        "apps.kuaizhizao.services.reporting_service._resolve_work_order_operation_for_reporting",
        new=AsyncMock(return_value=_woo(inspection_mode="simple")),
    ), patch(
        "apps.kuaizhizao.services.operation_transfer_service.resolve_key_operation_output_quantity",
        new=AsyncMock(return_value=Decimal("0")),
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.FinishedGoodsReceiptService"
    ) as receipt_cls:
        receipt_cls.return_value.quick_receipt_from_work_order = quick
        first = await svc._maybe_trigger_direct_finished_goods_inbound(1, 3, 7)
        second = await svc._maybe_trigger_direct_finished_goods_inbound(1, 8, 7)
    assert first is None
    assert second is None
    quick.assert_not_awaited()


@pytest.mark.asyncio
async def test_direct_inbound_occupied_quantity_sums_reporting_linked_receipts():
    relation_kwargs = {}
    receipt_kwargs = {}

    def relation_filter(**kwargs):
        relation_kwargs.update(kwargs)
        return _qs([SimpleNamespace(target_type="finished_goods_receipt", target_id=99)])

    def receipt_filter(**kwargs):
        receipt_kwargs.update(kwargs)
        return _qs([SimpleNamespace(total_quantity=Decimal("10"), status="已入库")])

    with patch(
        "apps.kuaizhizao.services.reporting_service.ReportingRecord.filter",
        return_value=_qs([SimpleNamespace(id=2), SimpleNamespace(id=3)]),
    ), patch(
        "apps.kuaizhizao.services.reporting_service.DocumentRelation.filter",
        side_effect=relation_filter,
    ), patch(
        "apps.kuaizhizao.models.finished_goods_receipt.FinishedGoodsReceipt.filter",
        side_effect=receipt_filter,
    ):
        total = await ReportingService()._sum_direct_inbound_quantity_for_work_order(1, 10)
    assert total == Decimal("10")
    assert relation_kwargs["source_type"] == "reporting_record"
    assert relation_kwargs["source_id__in"] == [2, 3]
    assert "finished_goods_receipt" in relation_kwargs["target_type__in"]
    assert receipt_kwargs["work_order_id"] == 10
    assert receipt_kwargs["id__in"] == [99]


@pytest.mark.asyncio
async def test_later_release_refreshes_key_last_header_without_new_reporting():
    woo = _woo(
        inspection_mode="simple",
        sequence=2,
        id=2,
        operation_id=9,
        qualified_quantity=Decimal("80"),
        unqualified_quantity=Decimal("0"),
    )
    work_order = _wo()
    work_order.completed_quantity = Decimal("0")
    work_order.qualified_quantity = Decimal("0")
    work_order.save = AsyncMock()
    inspection = SimpleNamespace(
        id=5,
        status="已检验",
        qualified_quantity=Decimal("10"),
        quality_status="合格",
        review_status="通过",
        inspection_code="PQ1",
        notes="",
        operation_id=9,
    )
    defects = [
        SimpleNamespace(
            defect_quantity=Decimal("2"),
            disposition="accept",
            status="processed",
            process_inspection_id=5,
        )
    ]
    completion = AsyncMock()
    policy, cfg = _patch_policy("simple", "operation")
    with policy, cfg, patch(
        "apps.kuaizhizao.services.reporting_service.sync_work_order_operations_completion",
        new=completion,
    ), patch(
        "apps.kuaizhizao.services.work_order_service.WorkOrder.get_or_none",
        new=AsyncMock(return_value=work_order),
    ), patch(
        "apps.kuaizhizao.services.reporting_service.WorkOrderOperation.filter",
        return_value=_qs([woo]),
    ), patch(
        "apps.kuaizhizao.services.operation_transfer_service.build_operation_policy_cache",
        new=AsyncMock(return_value={9: ("simple", None, "operation")}),
    ), patch(
        "apps.kuaizhizao.services.operation_transfer_service.load_process_inspections_by_operation",
        new=AsyncMock(return_value={9: [inspection]}),
    ), patch(
        "apps.kuaizhizao.models.defect_record.DefectRecord.filter",
        side_effect=_defect_filter(defects),
    ), patch(
        "infra.services.business_config_service.BusinessConfigService.check_audit_required",
        new=AsyncMock(return_value=False),
    ):
        await WorkOrderService().refresh_work_order_operation_transfer_state(1, 10)
    completion.assert_awaited_once()
    work_order.save.assert_awaited_once()
    assert work_order.completed_quantity == Decimal("12")
    assert work_order.qualified_quantity == Decimal("12")


@pytest.mark.asyncio
async def test_rework_verification_concession_excluded_from_output():
    woo = _woo(inspection_mode="simple", qualified_quantity=Decimal("80"))
    released = SimpleNamespace(
        id=5,
        status="已检验",
        qualified_quantity=Decimal("10"),
        quality_status="合格",
        review_status="通过",
        inspection_code="PQ1",
        notes="",
    )
    rework = SimpleNamespace(
        id=6,
        status="已检验",
        qualified_quantity=Decimal("0"),
        quality_status="不合格",
        review_status="通过",
        inspection_code="PQ-RW-1",
        notes="返工复检",
    )
    defects = [
        SimpleNamespace(
            defect_quantity=Decimal("2"),
            disposition="accept",
            status="processed",
            process_inspection_id=5,
        ),
        SimpleNamespace(
            defect_quantity=Decimal("4"),
            disposition="accept",
            status="processed",
            process_inspection_id=6,
        ),
        SimpleNamespace(
            defect_quantity=Decimal("9"),
            disposition="accept",
            status="draft",
            process_inspection_id=5,
        ),
    ]
    policy, cfg = _patch_policy("simple", "operation")
    with policy, cfg, patch(
        "apps.kuaizhizao.models.defect_record.DefectRecord.filter",
        side_effect=_defect_filter(defects),
    ):
        transfer = await resolve_operation_transfer_qualified(
            1,
            10,
            woo,
            inspections_by_op={1: [released, rework]},
            audit_required=False,
        )
        output = await resolve_key_operation_output_quantity(
            1,
            10,
            woo,
            inspections_by_op={1: [released, rework]},
            audit_required=False,
        )
    assert transfer == Decimal("10")
    assert output == Decimal("12")
