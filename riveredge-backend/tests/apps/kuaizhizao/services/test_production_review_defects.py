"""生产/委外审查缺陷：继承超报拉源、已保存子件、委外补领、未审报工不改执行中、委外节点门禁。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaizhizao.services.outsource_service import OutsourceService
from apps.kuaizhizao.services.reporting_service import (
    ReportingService,
    promote_released_work_order_when_reporting_approved,
)
from apps.kuaizhizao.services.work_order_service import WorkOrderService
from infra.exceptions.exceptions import BusinessLogicError


def _noop_transaction():
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=None)
    return tx


def test_pending_reporting_does_not_move_released_work_order():
    work_order = SimpleNamespace(status="released", actual_start_date=None)
    promote_released_work_order_when_reporting_approved(work_order, approved=False)
    assert work_order.status == "released"
    assert work_order.actual_start_date is None


def test_approved_reporting_moves_released_work_order_to_in_progress():
    work_order = SimpleNamespace(status="released", actual_start_date=None)
    promote_released_work_order_when_reporting_approved(work_order, approved=True)
    assert work_order.status == "in_progress"
    assert work_order.actual_start_date is not None


def test_approved_reporting_leaves_non_released_status():
    work_order = SimpleNamespace(status="draft", actual_start_date=None)
    promote_released_work_order_when_reporting_approved(work_order, approved=True)
    assert work_order.status == "draft"


@pytest.mark.asyncio
async def test_progress_update_promotes_released_only_after_approved_reporting():
    work_order = SimpleNamespace(id=3, status="released", actual_start_date=None)
    work_order.save = AsyncMock()
    exists = AsyncMock(return_value=False)
    filt = MagicMock()
    filt.exists = exists
    service = ReportingService()
    with patch(
        "apps.kuaizhizao.services.reporting_service.WorkOrder.get_or_none",
        new=AsyncMock(return_value=work_order),
    ), patch(
        "apps.kuaizhizao.services.reporting_service.sync_work_order_operations_completion",
        new=AsyncMock(),
    ), patch(
        "apps.kuaizhizao.services.reporting_service.ReportingRecord.filter",
        return_value=filt,
    ), patch.object(
        service,
        "_sync_work_order_header_quantities_from_last_operation",
        new=AsyncMock(),
    ), patch.object(
        service,
        "_sync_pending_inbound_receipts_if_needed",
        new=AsyncMock(),
    ):
        await service._update_work_order_progress(1, 3)
        assert work_order.status == "released"

        exists.return_value = True
        work_order.status = "released"
        work_order.actual_start_date = None
        await service._update_work_order_progress(1, 3)
    assert work_order.status == "in_progress"


def _saved_component():
    return SimpleNamespace(
        issue_method=None,
        component_type=None,
        component_id=42,
        component_code="SAVED",
        component_name="已保存子件",
        net_requirement=8,
        gross_requirement=8,
        unit="件",
    )


@pytest.mark.asyncio
async def test_shortage_uses_saved_lines_not_bom_template():
    service = WorkOrderService()
    service.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            id=7,
            code="WO-1",
            name="工单",
            product_id=3,
            quantity=Decimal("10"),
            variant_attributes=None,
            configurable_selections=None,
        )
    )
    bom = AsyncMock(side_effect=AssertionError("不应读 BOM 模板"))
    with patch(
        "apps.kuaizhizao.services.work_order_bom_line_service.WorkOrderBomLineService.build_requirements_from_saved_lines",
        new=AsyncMock(return_value=[_saved_component()]),
    ), patch(
        "apps.kuaizhizao.services.work_order_service.calculate_material_requirements_from_bom",
        new=bom,
    ), patch(
        "apps.kuaizhizao.services.work_order_service.get_material_available_quantity",
        new=AsyncMock(return_value=Decimal("0")),
    ):
        result = await service.check_material_shortage(tenant_id=1, work_order_id=7)
    bom.assert_not_awaited()
    assert result["bom_missing"] is False
    assert result["shortage_items"][0]["material_id"] == 42
    assert result["shortage_items"][0]["required_quantity"] == 8.0


@pytest.mark.asyncio
async def test_reportable_qty_uses_saved_lines_not_bom_template():
    work_order = SimpleNamespace(
        id=7,
        product_id=3,
        quantity=Decimal("10"),
        variant_attributes=None,
        configurable_selections=None,
    )
    saved = SimpleNamespace(
        issue_method=None,
        component_type=None,
        component_id=42,
        gross_requirement=20,
        net_requirement=20,
        unit="件",
    )
    bom = AsyncMock(side_effect=AssertionError("不应读 BOM 模板"))
    with patch(
        "apps.kuaizhizao.services.work_order_service.WorkOrder.get_or_none",
        new=AsyncMock(return_value=work_order),
    ), patch(
        "apps.kuaizhizao.services.work_order_bom_line_service.WorkOrderBomLineService.build_requirements_from_saved_lines",
        new=AsyncMock(return_value=[saved]),
    ), patch(
        "apps.kuaizhizao.services.work_order_service.calculate_material_requirements_from_bom",
        new=bom,
    ), patch(
        "apps.kuaizhizao.utils.picking_posting.sum_confirmed_picked_by_material",
        new=AsyncMock(return_value={42: Decimal("40")}),
    ):
        qty = await WorkOrderService.resolve_max_reportable_qty_from_confirmed_picking(1, 7)
    bom.assert_not_awaited()
    assert qty == Decimal("20")


@pytest.mark.asyncio
async def test_kitting_uses_saved_lines_not_bom_template():
    service = WorkOrderService()
    work_order = SimpleNamespace(
        id=7,
        code="WO-1",
        product_id=3,
        quantity=Decimal("10"),
        variant_attributes=None,
        configurable_selections=None,
        work_order_group_id=None,
    )
    bom = AsyncMock(side_effect=AssertionError("不应读 BOM 模板"))
    picking_query = MagicMock()
    picking_query.all = AsyncMock(return_value=[])
    with patch(
        "apps.kuaizhizao.services.work_order_service.WorkOrder.get_or_none",
        new=AsyncMock(return_value=work_order),
    ), patch(
        "apps.kuaizhizao.services.work_order_bom_line_service.WorkOrderBomLineService.build_requirements_from_saved_lines",
        new=AsyncMock(return_value=[_saved_component()]),
    ), patch(
        "apps.kuaizhizao.services.work_order_service.calculate_material_requirements_from_bom",
        new=bom,
    ), patch(
        "apps.kuaizhizao.services.work_order_service.ProductionPicking.filter",
        return_value=picking_query,
    ), patch.object(
        service, "_load_kitting_component_outsource_map", new=AsyncMock(return_value={})
    ), patch.object(
        service, "_load_material_open_purchase_map", new=AsyncMock(return_value={})
    ), patch(
        "apps.kuaizhizao.services.work_order_service.BusinessConfigService.get_quantity_decimal_places",
        new=AsyncMock(return_value=2),
    ), patch(
        "apps.kuaizhizao.services.work_order_service.get_material_detailed_locations",
        new=AsyncMock(return_value=[]),
    ):
        result = await service.compute_work_order_kitting_analysis(1, 7)
    bom.assert_not_awaited()
    assert result.status != "no_bom"
    assert result.items[0].material_id == 42
    assert result.items[0].required_quantity == Decimal("8")


def _pull_work_order(*, over_report_mode: str, over_report_value: str):
    return SimpleNamespace(
        id=1,
        quantity=Decimal("100"),
        over_report_mode=over_report_mode,
        over_report_value=Decimal(over_report_value),
        allow_operation_jump=True,
        code="WO",
        name="工单",
        product_name="产品",
        product_code="P",
        planned_start_date=None,
        status="in_progress",
    )


def _pull_operation():
    return SimpleNamespace(
        id=5,
        work_order_id=1,
        operation_id=11,
        operation_code="OP",
        operation_name="下料",
        sequence=1,
        completed_quantity=Decimal("100"),
        qualified_quantity=Decimal("100"),
        over_report_mode="none",
        over_report_value=Decimal("0"),
        reporting_type="quantity",
        deleted_at=None,
        is_node_operation=False,
    )


async def _list_pull(work_order, operation, *, master=None):
    wo_query = MagicMock()
    wo_query.order_by.return_value.limit = AsyncMock(return_value=[work_order])
    op_query = MagicMock()
    op_query.order_by.return_value.all = AsyncMock(return_value=[operation])
    empty = MagicMock()
    empty.all = AsyncMock(return_value=[])
    config = MagicMock()
    config.check_audit_required = AsyncMock(return_value=False)
    patches = [
        patch(
            "apps.kuaizhizao.services.reporting_service.WorkOrder.filter",
            return_value=wo_query,
        ),
        patch(
            "apps.kuaizhizao.services.reporting_service.WorkOrderOperation.filter",
            return_value=op_query,
        ),
        patch(
            "apps.kuaizhizao.services.operation_transfer_service.build_operation_policy_cache",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.get_quality_effective_config",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "apps.kuaizhizao.services.reporting_service.BusinessConfigService",
            return_value=config,
        ),
        patch(
            "apps.kuaizhizao.models.process_inspection.ProcessInspection.filter",
            return_value=empty,
        ),
        patch(
            "apps.kuaizhizao.models.scrap_record.ScrapRecord.filter",
            return_value=empty,
        ),
        patch(
            "apps.kuaizhizao.services.operation_transfer_service.resolve_operation_transfer_qualified",
            new=AsyncMock(return_value=Decimal("100")),
        ),
        patch(
            "apps.kuaizhizao.services.operation_jump_rules.resolve_material_incoming_qty",
            new=AsyncMock(return_value=Decimal("200")),
        ),
        patch(
            "apps.kuaizhizao.services.work_order_service.WorkOrderService.resolve_material_incoming_picking_extra_units",
            new=AsyncMock(return_value=Decimal("0")),
        ),
    ]
    if master is not None:
        patches.append(
            patch(
                "apps.master_data.models.process.Operation.get_or_none",
                new=AsyncMock(return_value=master),
            )
        )
    from contextlib import ExitStack

    with ExitStack() as stack:
        for item in patches:
            stack.enter_context(item)
        return await ReportingService().list_reporting_pull_candidates(tenant_id=1, scope="reportable")


@pytest.mark.asyncio
async def test_pull_inherit_over_report_uses_work_order_header():
    page = await _list_pull(
        _pull_work_order(over_report_mode="percent", over_report_value="10"),
        _pull_operation(),
    )
    assert page.total == 1
    assert page.data[0].reportable_quantity_max == Decimal("10")


@pytest.mark.asyncio
async def test_pull_inherit_over_report_falls_back_to_operation_master():
    master = SimpleNamespace(over_report_mode="percent", over_report_value=Decimal("10"))
    page = await _list_pull(
        _pull_work_order(over_report_mode="none", over_report_value="0"),
        _pull_operation(),
        master=master,
    )
    assert page.total == 1
    assert page.data[0].reportable_quantity_max == Decimal("10")


def _flow_op(op_id: int, sequence: int):
    return SimpleNamespace(
        id=op_id,
        operation_id=None,
        sequence=sequence,
        completed_quantity=Decimal("0"),
        qualified_quantity=Decimal("0"),
        over_report_mode="none",
        over_report_value=Decimal("0"),
    )


def _flow_work_order(*, allow_operation_jump: bool):
    return SimpleNamespace(
        id=1,
        quantity=Decimal("100"),
        allow_operation_jump=allow_operation_jump,
        over_report_mode="none",
        over_report_value=Decimal("0"),
    )


@pytest.mark.asyncio
async def test_outsource_incoming_adds_picking_extra_for_first_or_jump():
    service = OutsourceService()
    extra = AsyncMock(return_value=Decimal("20"))
    with patch(
        "apps.kuaizhizao.services.operation_jump_rules.resolve_material_incoming_qty",
        new=AsyncMock(return_value=Decimal("100")),
    ), patch(
        "apps.kuaizhizao.services.operation_transfer_service.resolve_operation_transfer_qualified",
        new=AsyncMock(return_value=Decimal("40")),
    ), patch(
        "apps.kuaizhizao.services.work_order_service.WorkOrderService.resolve_material_incoming_picking_extra_units",
        new=extra,
    ):
        first = await service._resolve_operation_flow_caps(
            1,
            _flow_work_order(allow_operation_jump=False),
            _flow_op(2, 1),
            ordered_operations=[_flow_op(2, 1)],
        )
        jumped = await service._resolve_operation_flow_caps(
            1,
            _flow_work_order(allow_operation_jump=True),
            _flow_op(3, 2),
            ordered_operations=[_flow_op(2, 1), _flow_op(3, 2)],
        )
        sequential = await service._resolve_operation_flow_caps(
            1,
            _flow_work_order(allow_operation_jump=False),
            _flow_op(3, 2),
            ordered_operations=[_flow_op(2, 1), _flow_op(3, 2)],
        )
    assert first["incoming_quantity"] == Decimal("120")
    assert jumped["incoming_quantity"] == Decimal("120")
    assert sequential["incoming_quantity"] == Decimal("100")
    assert extra.await_count == 2


@pytest.mark.asyncio
async def test_outsource_release_blocked_when_previous_node_has_no_output():
    service = OutsourceService()
    row = SimpleNamespace(
        id=9,
        status="draft",
        work_order_id=1,
        work_order_operation_id=4,
        outsource_quantity=Decimal("10"),
    )
    work_order = SimpleNamespace(id=1, allow_operation_jump=True, quantity=Decimal("100"))
    operation = SimpleNamespace(
        id=4,
        sequence=4,
        is_node_operation=False,
        operation_name="后道",
        work_order_id=1,
        deleted_at=None,
    )
    node = SimpleNamespace(
        id=2,
        sequence=2,
        is_node_operation=True,
        operation_name="节点",
        work_order_id=1,
        deleted_at=None,
        qualified_quantity=Decimal("0"),
    )
    with patch(
        "apps.kuaizhizao.services.outsource_service.in_transaction",
        return_value=_noop_transaction(),
    ), patch.object(
        service, "_get_outsource_order_row", new=AsyncMock(return_value=row)
    ), patch(
        "apps.kuaizhizao.services.outsource_service.WorkOrder.filter"
    ) as wo_filter, patch(
        "apps.kuaizhizao.services.outsource_service.WorkOrderOperation.filter"
    ) as op_filter, patch(
        "apps.kuaizhizao.services.operation_jump_rules.list_predecessors",
        new=AsyncMock(return_value=[node]),
    ), patch(
        "apps.kuaizhizao.services.operation_jump_rules.qualified_transfer_quantity_async",
        new=AsyncMock(return_value=Decimal("0")),
    ):
        wo_filter.return_value.first = AsyncMock(return_value=work_order)
        op_filter.return_value.first = AsyncMock(return_value=operation)
        with pytest.raises(BusinessLogicError, match="允许跳转时前序节点仍不可跳过"):
            await service.release_outsource_order(tenant_id=1, outsource_order_id=9, updated_by=1)
