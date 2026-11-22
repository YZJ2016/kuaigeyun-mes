"""拉源与工序卡片在制：前序关键节点放行、补领不绕过节点。"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaizhizao.services.reporting_service import ReportingService
from apps.kuaizhizao.services.work_order_service import WorkOrderService

QUALITY_CFG = {
    "stage_enabled": {"ipqc": True},
    "module_enabled": {"process": True},
}


def _quality_config():
    config = MagicMock()
    config.check_audit_required = AsyncMock(return_value=False)
    return config


def _query_all(rows):
    query = MagicMock()
    query.all = AsyncMock(return_value=rows)
    return query


def _pull_work_order():
    return SimpleNamespace(
        id=1,
        quantity=Decimal("100"),
        over_report_mode="none",
        over_report_value=Decimal("0"),
        allow_operation_jump=True,
        code="WO",
        name="工单",
        product_name="产品",
        product_code="P",
        planned_start_date=None,
        status="in_progress",
    )


def _pull_operation(
    *,
    op_id: int,
    master_id: int,
    sequence: int,
    name: str,
    is_node: bool,
    inspection_mode: str | None = None,
):
    op = SimpleNamespace(
        id=op_id,
        work_order_id=1,
        operation_id=master_id,
        operation_code=f"OP{sequence}",
        operation_name=name,
        sequence=sequence,
        completed_quantity=Decimal("0"),
        qualified_quantity=Decimal("0"),
        over_report_mode="none",
        over_report_value=Decimal("0"),
        reporting_type="quantity",
        deleted_at=None,
        is_node_operation=is_node,
    )
    if inspection_mode is not None:
        op.inspection_mode = inspection_mode
        if inspection_mode == "plan":
            op.inspection_plan_id = 9
    return op


def _released_inspection(*, status: str):
    return SimpleNamespace(
        id=8,
        operation_id=11,
        work_order_id=1,
        status=status,
        qualified_quantity=Decimal("40"),
        unqualified_quantity=Decimal("0"),
        inspection_code="PQ-1",
        notes="",
        inspection_plan_id=9,
        review_status=None,
    )


async def _list_pull(operations, inspections):
    wo_query = MagicMock()
    wo_query.order_by.return_value.limit = AsyncMock(return_value=[_pull_work_order()])
    op_query = MagicMock()
    op_query.order_by.return_value.all = AsyncMock(return_value=operations)
    config = _quality_config()
    with patch(
        "apps.kuaizhizao.services.reporting_service.WorkOrder.filter",
        return_value=wo_query,
    ), patch(
        "apps.kuaizhizao.services.reporting_service.WorkOrderOperation.filter",
        return_value=op_query,
    ), patch(
        "apps.kuaizhizao.services.operation_transfer_service.build_operation_policy_cache",
        new=AsyncMock(
            return_value={
                11: ("simple", None, "operation"),
                22: ("none", None, "default_none"),
            }
        ),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.get_quality_effective_config",
        new=AsyncMock(return_value=QUALITY_CFG),
    ), patch(
        "apps.kuaizhizao.services.operation_transfer_service.get_quality_effective_config",
        new=AsyncMock(return_value=QUALITY_CFG),
    ), patch(
        "apps.kuaizhizao.services.reporting_service.BusinessConfigService",
        return_value=config,
    ), patch(
        "infra.services.business_config_service.BusinessConfigService",
        return_value=config,
    ), patch(
        "apps.kuaizhizao.models.process_inspection.ProcessInspection.filter",
        return_value=_query_all(inspections),
    ), patch(
        "apps.kuaizhizao.models.scrap_record.ScrapRecord.filter",
        return_value=_query_all([]),
    ), patch(
        "apps.master_data.models.process.Operation.get_or_none",
        new=AsyncMock(return_value=None),
    ), patch(
        "apps.kuaizhizao.services.work_order_service.WorkOrderService.resolve_material_incoming_picking_extra_units",
        new=AsyncMock(return_value=Decimal("0")),
    ):
        return await ReportingService().list_reporting_pull_candidates(
            tenant_id=1, scope="reportable"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("inspection_mode", ["simple", "plan"])
async def test_pull_keeps_non_node_when_previous_key_node_is_released(inspection_mode):
    """允许跳转时，前序简单检/方案检已放行，非节点仍可报，转入按库里的放行数量。"""
    node = _pull_operation(
        op_id=1,
        master_id=11,
        sequence=1,
        name="关键节点",
        is_node=True,
        inspection_mode=inspection_mode,
    )
    later = _pull_operation(
        op_id=2,
        master_id=22,
        sequence=2,
        name="非节点",
        is_node=False,
    )
    page = await _list_pull(
        [node, later],
        [_released_inspection(status="已检验")],
    )
    later_rows = [row for row in page.data if row.operation_id == 22]
    assert len(later_rows) == 1
    assert later_rows[0].reportable_quantity_max == Decimal("100")


@pytest.mark.asyncio
@pytest.mark.parametrize("inspection_mode", ["simple", "plan"])
async def test_pull_hides_non_node_when_previous_key_node_is_not_released(inspection_mode):
    """未放行时非节点不能进入可报列表；直接提交的节点门禁不因此放宽。"""
    node = _pull_operation(
        op_id=1,
        master_id=11,
        sequence=1,
        name="关键节点",
        is_node=True,
        inspection_mode=inspection_mode,
    )
    later = _pull_operation(
        op_id=2,
        master_id=22,
        sequence=2,
        name="非节点",
        is_node=False,
    )
    page = await _list_pull(
        [node, later],
        [_released_inspection(status="待检验")],
    )
    assert all(row.operation_id != 22 for row in page.data)


def _card_operation(*, op_id: int, master_id: int, sequence: int, name: str, is_node: bool):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=op_id,
        uuid=f"woo-{op_id}",
        tenant_id=1,
        work_order_id=1,
        work_order_code="WO",
        operation_id=master_id,
        operation_code=f"OP{sequence}",
        operation_name=name,
        sequence=sequence,
        status="pending",
        completed_quantity=Decimal("0"),
        qualified_quantity=Decimal("0"),
        unqualified_quantity=Decimal("0"),
        reporting_type="quantity",
        allow_jump=True,
        is_node_operation=is_node,
        over_report_mode="none",
        over_report_value=Decimal("0"),
        outsource_kind="none",
        deleted_at=None,
        assigned_worker_id=None,
        assigned_worker_ids=[],
        assigned_team_id=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_operation_card_does_not_add_picking_extra_when_incoming_is_zero():
    """前序节点无合格产出时在制为 0，工序卡片不再把补领加回去。"""
    work_order = SimpleNamespace(
        id=1,
        quantity=Decimal("100"),
        allow_operation_jump=True,
        product_id=None,
        over_report_mode="none",
        over_report_value=Decimal("0"),
    )
    operations = [
        _card_operation(op_id=1, master_id=11, sequence=1, name="节点", is_node=True),
        _card_operation(op_id=2, master_id=22, sequence=2, name="后道", is_node=False),
    ]
    op_query = MagicMock()
    op_query.order_by.return_value.all = AsyncMock(return_value=operations)
    downtime_query = _query_all([])
    outsource_query = MagicMock()
    outsource_query.exclude.return_value.all = AsyncMock(return_value=[])
    config = _quality_config()
    with patch(
        "apps.kuaizhizao.services.work_order_service.WorkOrder.get_or_none",
        new=AsyncMock(return_value=work_order),
    ), patch(
        "apps.kuaizhizao.services.work_order_service.WorkOrderOperation.filter",
        return_value=op_query,
    ), patch(
        "apps.kuaizhizao.services.work_order_service.ProductionPicking.filter",
        return_value=_query_all([]),
    ), patch(
        "apps.kuaizhizao.services.work_order_service.ScrapRecord.filter",
        return_value=_query_all([]),
    ), patch(
        "apps.kuaizhizao.services.reporting_service.sync_work_order_operations_completion",
        new=AsyncMock(),
    ), patch(
        "apps.kuaizhizao.models.station_operation_downtime.StationOperationDowntime.filter",
        return_value=downtime_query,
    ), patch(
        "apps.kuaizhizao.services.work_order_service.batch_get_operation_defect_types_via_table",
        new=AsyncMock(return_value={}),
    ), patch(
        "apps.kuaizhizao.services.work_order_service._batch_sop_for_master_operations",
        new=AsyncMock(return_value={}),
    ), patch(
        "apps.kuaizhizao.services.work_order_service._batch_default_operators_snapshots_by_master_operation_id",
        new=AsyncMock(return_value={}),
    ), patch(
        "apps.kuaizhizao.models.outsource_order.OutsourceOrder.filter",
        return_value=outsource_query,
    ), patch(
        "apps.kuaizhizao.services.operation_transfer_service.build_operation_policy_cache",
        new=AsyncMock(
            return_value={
                11: ("none", None, "default_none"),
                22: ("none", None, "default_none"),
            }
        ),
    ), patch(
        "apps.kuaizhizao.services.operation_transfer_service.load_process_inspections_by_operation",
        new=AsyncMock(return_value={}),
    ), patch(
        "apps.kuaizhizao.services.work_order_service.BusinessConfigService",
        return_value=config,
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.get_quality_effective_config",
        new=AsyncMock(return_value=QUALITY_CFG),
    ), patch(
        "apps.kuaizhizao.services.operation_transfer_service.get_quality_effective_config",
        new=AsyncMock(return_value=QUALITY_CFG),
    ), patch(
        "apps.kuaizhizao.services.operation_transfer_service.resolve_operation_transfer_qualified",
        new=AsyncMock(return_value=Decimal("0")),
    ), patch(
        "apps.kuaizhizao.services.operation_jump_rules.resolve_material_incoming_qty",
        new=AsyncMock(side_effect=[Decimal("100"), Decimal("0")]),
    ), patch.object(
        WorkOrderService,
        "resolve_material_incoming_picking_extra_units",
        new=AsyncMock(return_value=Decimal("20")),
    ):
        rows = await WorkOrderService().get_work_order_operations(1, 1)

    by_op = {row.operation_id: row for row in rows}
    assert by_op[11].material_remaining == Decimal("120")
    assert by_op[22].material_remaining == Decimal("0")
