"""流程造数 P0/P1 修复与 P2 扩展（外购直推 / 工序委外 / 轻财务结算）回归单测。"""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaizhizao.schemas.warehouse import OtherInboundItemCreate
from apps.kuaizhizao.services.demand_computation_service import DemandComputationService
from apps.kuaizhizao.services.flow_data_generate_service import (
    FlowDataGenerateService,
    FlowGenerateRequest,
    IntervalConfig,
    STEP_KEYS,
    TimelineEntry,
    TimelinePlanner,
)
from apps.kuaizhizao.services.flow_sim.engine import map_steps_for_scenarios
from apps.kuaizhizao.services.flow_sim.scenarios import (
    DIRECT_PURCHASE_SCENARIOS,
    FULL_CHAIN_SCENARIOS,
    SCENARIO_DEFS,
    resolve_scenario_ids,
)
from core.services.document_time_rewrite_service import REWRITE_SPECS
from core.services.integration.document_push_silent import (
    is_silent_push_suppressed,
    maybe_silent_push_after_audit,
    silent_push_would_run_on_confirm,
    suppress_silent_push,
)
from infra.exceptions.exceptions import BusinessLogicError


FLOW_SVC_PATH = (
    Path(__file__).resolve().parents[4]
    / "src"
    / "apps"
    / "kuaizhizao"
    / "services"
    / "flow_data_generate_service.py"
)


def test_other_inbound_item_create_always_passes_warehouse_id():
    tree = ast.parse(FLOW_SVC_PATH.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "OtherInboundItemCreate"
    ]
    assert len(calls) >= 3
    for node in calls:
        kw_names = {kw.arg for kw in node.keywords if kw.arg}
        assert "warehouse_id" in kw_names, f"L{node.lineno} OtherInboundItemCreate 缺少 warehouse_id"

    # 验证与真实 Pydantic Schema 兼容
    item = OtherInboundItemCreate(
        material_id=1,
        material_code="M001",
        material_name="原料A",
        material_unit="个",
        inbound_quantity=5.0,
        warehouse_id=10,
        warehouse_name="主仓",
    )
    assert item.warehouse_id == 10


def test_sales_forecast_item_filter_has_no_deleted_at():
    tree = ast.parse(FLOW_SVC_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "SalesForecastItem"
            and node.func.attr == "filter"
        ):
            kw_names = {kw.arg for kw in node.keywords if kw.arg}
            assert "deleted_at__isnull" not in kw_names, (
                f"L{node.lineno} SalesForecastItem.filter 不应传 deleted_at__isnull"
            )


def test_approve_purchase_order_uses_auto_approve_flag():
    tree = ast.parse(FLOW_SVC_PATH.read_text(encoding="utf-8"))
    found = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "approve_purchase_order"
        ):
            found += 1
            kw_map = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            assert "is_auto_approve" in kw_map
            assert isinstance(kw_map["is_auto_approve"], ast.Constant)
            assert kw_map["is_auto_approve"].value is True
    assert found >= 1


@pytest.mark.asyncio
async def test_suppress_silent_push_blocks_confirm_precheck_and_audit_push():
    assert is_silent_push_suppressed() is False
    with suppress_silent_push():
        assert is_silent_push_suppressed() is True
        assert await silent_push_would_run_on_confirm(1, "production_picking") is False
        res = await maybe_silent_push_after_audit(
            tenant_id=1,
            user_id=1,
            entity_type="sales_delivery",
            entity_id=99,
            action="confirm",
        )
        assert res is None
    assert is_silent_push_suppressed() is False


@pytest.mark.asyncio
async def test_resolve_purchase_order_department_from_users():
    buyer = SimpleNamespace(id=11, department_id=None)
    creator = SimpleNamespace(id=12, department_id=101)
    dept = SimpleNamespace(id=101, name="采购部")

    async def fake_user_get(id=None, **_kwargs):
        return {11: buyer, 12: creator}.get(id)

    async def fake_dept_get(tenant_id=None, id=None, **_kwargs):
        return dept if id == 101 else None

    with (
        patch("apps.kuaizhizao.services.demand_computation_service.User.get_or_none", side_effect=fake_user_get),
        patch("core.models.department.Department.get_or_none", side_effect=fake_dept_get),
    ):
        did, dname = await DemandComputationService._resolve_purchase_order_department_from_users(
            1, 11, 12
        )
        assert (did, dname) == (101, "采购部")

        did_none, dname_none = await DemandComputationService._resolve_purchase_order_department_from_users(
            1, 11
        )
        assert (did_none, dname_none) == (None, None)


def test_p2_scenarios_step_keys_and_time_rewrite_specs():
    assert "direct_purchase" in SCENARIO_DEFS
    assert "finance_settlement" in SCENARIO_DEFS
    assert "finance_settlement" in FULL_CHAIN_SCENARIOS
    assert "direct_purchase" not in FULL_CHAIN_SCENARIOS
    assert DIRECT_PURCHASE_SCENARIOS == (
        "direct_purchase",
        "purchase_inbound",
        "ship",
        "finance_settlement",
    )
    assert "direct_purchase" in STEP_KEYS
    assert "process_outsource" in STEP_KEYS
    assert "finance_settlement" in STEP_KEYS

    dp_steps = map_steps_for_scenarios(resolve_scenario_ids(["direct_purchase", "purchase_inbound"]))
    assert dp_steps["direct_purchase"] is True
    assert dp_steps["demand_computation"] is False
    assert dp_steps["purchase"] is True

    wo_steps = map_steps_for_scenarios(resolve_scenario_ids(["wo_complete"]))
    assert wo_steps["process_outsource"] is True

    rewrite_types = {spec.doc_type for spec in REWRITE_SPECS}
    for required_type in (
        "outsource_order",
        "purchase_requisition",
        "payable",
        "receivable",
        "payment",
        "receipt",
    ):
        assert required_type in rewrite_types


@pytest.mark.asyncio
async def test_execute_rejects_conflicting_or_invalid_direct_purchase_scenarios():
    svc = FlowDataGenerateService()
    with pytest.raises(BusinessLogicError, match="互斥"):
        await svc.execute(
            tenant_id=1,
            operator_id=1,
            req=FlowGenerateRequest(
                source_type="sales_order",
                sales_order_id=10,
                scenarios=["mrp_push", "direct_purchase"],
            ),
        )

    with pytest.raises(BusinessLogicError, match="仅支持销售订单"):
        await svc.execute(
            tenant_id=1,
            operator_id=1,
            req=FlowGenerateRequest(
                source_type="sales_forecast",
                sales_forecast_id=20,
                scenarios=["direct_purchase", "purchase_inbound"],
            ),
        )


@pytest.mark.asyncio
async def test_fulfill_operation_outsource_orders_runs_full_lifecycle():
    svc = FlowDataGenerateService()
    wo = SimpleNamespace(id=50, code="WO-50")
    wo_op = SimpleNamespace(
        id=501,
        operation_name="电镀委外",
        outsource_kind="planned",
        default_outsource_supplier_id=88,
    )
    oo_row = SimpleNamespace(
        id=900,
        code="OO-900",
        status="draft",
        outsource_quantity=Decimal("10"),
        received_quantity=Decimal("0"),
    )

    async def fake_refresh():
        return None

    oo_row.refresh_from_db = fake_refresh

    async def fake_release(tenant_id, outsource_order_id, updated_by):
        oo_row.status = "released"

    async def fake_register_receipt(tenant_id, outsource_order_id, receipt_data, updated_by):
        oo_row.received_quantity = Decimal(str(receipt_data.received_quantity))
        oo_row.status = "in_progress"

    async def fake_complete(tenant_id, outsource_order_id, updated_by):
        oo_row.status = "completed"

    mock_query = MagicMock()
    mock_query.exclude.return_value.order_by.return_value.all = AsyncMock(return_value=[])

    mock_oo_svc = MagicMock()
    mock_oo_svc.create_outsource_order_from_work_order = AsyncMock(
        return_value=SimpleNamespace(id=900, code="OO-900")
    )
    mock_oo_svc.release_outsource_order = AsyncMock(side_effect=fake_release)
    mock_oo_svc.register_outsource_order_receipt = AsyncMock(side_effect=fake_register_receipt)
    mock_oo_svc.complete_outsource_order = AsyncMock(side_effect=fake_complete)

    mock_bridge = MagicMock()
    mock_bridge.get_issue_preview = AsyncMock(return_value=SimpleNamespace(lines=[]))

    planner = TimelinePlanner(
        anchor=datetime(2026, 11, 27, 2, 0, 0, tzinfo=timezone.utc),
        default_interval=IntervalConfig(),
        intervals={},
    )
    timeline: list[TimelineEntry] = []
    step_results: list[dict] = []

    with (
        patch("apps.kuaizhizao.models.outsource_order.OutsourceOrder.filter", return_value=mock_query),
        patch("apps.kuaizhizao.models.outsource_order.OutsourceOrder.get_or_none", AsyncMock(return_value=oo_row)),
        patch("apps.kuaizhizao.services.outsource_service.OutsourceService", return_value=mock_oo_svc),
        patch("apps.kuaizhizao.services.outsource_order_issue_bridge.OutsourceOrderIssueBridge", return_value=mock_bridge),
        patch.object(svc, "_record_step", AsyncMock()) as mock_record,
    ):
        handled = await svc._fulfill_operation_outsource_orders(
            tenant_id=1,
            operator_id=7,
            work_order=wo,
            wo_op=wo_op,
            quantity=Decimal("10"),
            warehouse={"id": 3, "name": "主仓"},
            planner=planner,
            timeline=timeline,
            step_results=step_results,
            run_id="run-oo-1",
        )

    assert handled is True
    assert oo_row.status == "completed"
    mock_oo_svc.create_outsource_order_from_work_order.assert_awaited_once()
    mock_oo_svc.release_outsource_order.assert_awaited_once()
    mock_oo_svc.register_outsource_order_receipt.assert_awaited_once()
    mock_oo_svc.complete_outsource_order.assert_awaited_once()
    mock_record.assert_awaited_once()
    assert mock_record.call_args.kwargs["doc_type"] == "outsource_order"
