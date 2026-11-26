"""成品入库工单额度：工单量 vs 领料套数。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaizhizao.services.warehouse_service import FinishedGoodsReceiptService


@pytest.mark.asyncio
async def test_compute_picking_kit_sets_cap_min_of_kitting_materials():
    svc = FinishedGoodsReceiptService()
    wo = SimpleNamespace(id=1, product_id=100, quantity=10)
    req_a = SimpleNamespace(
        component_id=201,
        gross_requirement=20,
        issue_method="backflush",
        component_type="material",
    )
    req_b = SimpleNamespace(
        component_id=202,
        gross_requirement=10,
        issue_method="backflush",
        component_type="material",
    )

    with patch(
        "apps.kuaizhizao.utils.bom_helper.calculate_material_requirements_from_bom",
        new_callable=AsyncMock,
        return_value=[req_a, req_b],
    ), patch(
        "apps.kuaizhizao.utils.picking_posting.sum_confirmed_picked_by_material",
        new_callable=AsyncMock,
        return_value={201: 15, 202: 40},
    ), patch(
        "apps.kuaizhizao.utils.issue_method_resolver.is_kitting_rate_material",
        return_value=True,
    ):
        cap = await svc._compute_picking_kit_sets_cap(1, wo)

    assert cap == 7.0


@pytest.mark.asyncio
async def test_compute_picking_kit_sets_cap_zero_without_kitting_lines():
    svc = FinishedGoodsReceiptService()
    wo = SimpleNamespace(id=2, product_id=100, quantity=5)
    req = SimpleNamespace(
        component_id=301,
        gross_requirement=5,
        issue_method="manual",
        component_type="material",
    )

    with patch(
        "apps.kuaizhizao.utils.bom_helper.calculate_material_requirements_from_bom",
        new_callable=AsyncMock,
        return_value=[req],
    ), patch(
        "apps.kuaizhizao.utils.picking_posting.sum_confirmed_picked_by_material",
        new_callable=AsyncMock,
        return_value={301: 100},
    ), patch(
        "apps.kuaizhizao.utils.issue_method_resolver.is_kitting_rate_material",
        return_value=False,
    ):
        cap = await svc._compute_picking_kit_sets_cap(1, wo)

    assert cap == 0.0


@pytest.mark.asyncio
async def test_get_work_order_inbound_quota_picking_kit_caps_pending():
    svc = FinishedGoodsReceiptService()
    work_order = SimpleNamespace(
        id=9,
        quantity=100,
        product_id=50,
        over_report_mode=None,
        over_report_value=None,
    )

    with patch(
        "apps.kuaizhizao.models.work_order.WorkOrder.get_or_none",
        new_callable=AsyncMock,
        return_value=work_order,
    ), patch.object(
        svc,
        "_sum_work_order_inbound_quantity",
        new_callable=AsyncMock,
        return_value=0.0,
    ), patch(
        "infra.services.business_config_service.BusinessConfigService.get_finished_goods_inbound_limit_mode",
        new_callable=AsyncMock,
        return_value="picking_kit_sets",
    ), patch.object(
        svc,
        "_compute_picking_kit_sets_cap",
        new_callable=AsyncMock,
        return_value=30.0,
    ), patch(
        "apps.kuaizhizao.utils.over_qty_tolerance.OverQtyToleranceResolver.resolve_over_receipt_pct",
        new_callable=AsyncMock,
        return_value=0,
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
        new_callable=AsyncMock,
        return_value=("none", None, None),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.get_fqc_inbound_remaining_quantity",
        new_callable=AsyncMock,
        return_value=Decimal("1000"),
    ):
        quota = await svc._get_work_order_inbound_quota(1, 9)

    assert quota["inbound_limit_mode"] == "picking_kit_sets"
    assert quota["picking_kit_sets_cap"] == 30.0
    assert quota["pending"] == 30.0
    assert quota["max_quantity"] == 30.0


@pytest.mark.asyncio
async def test_get_work_order_inbound_quota_work_order_quantity_ignores_kit_cap():
    svc = FinishedGoodsReceiptService()
    work_order = SimpleNamespace(
        id=10,
        quantity=100,
        product_id=50,
        over_report_mode=None,
        over_report_value=None,
    )

    compute_cap = AsyncMock(return_value=30.0)

    with patch(
        "apps.kuaizhizao.models.work_order.WorkOrder.get_or_none",
        new_callable=AsyncMock,
        return_value=work_order,
    ), patch.object(
        svc,
        "_sum_work_order_inbound_quantity",
        new_callable=AsyncMock,
        return_value=10.0,
    ), patch(
        "infra.services.business_config_service.BusinessConfigService.get_finished_goods_inbound_limit_mode",
        new_callable=AsyncMock,
        return_value="work_order_quantity",
    ), patch.object(svc, "_compute_picking_kit_sets_cap", compute_cap), patch(
        "apps.kuaizhizao.utils.over_qty_tolerance.OverQtyToleranceResolver.resolve_over_receipt_pct",
        new_callable=AsyncMock,
        return_value=0,
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
        new_callable=AsyncMock,
        return_value=("none", None, None),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.get_fqc_inbound_remaining_quantity",
        new_callable=AsyncMock,
        return_value=Decimal("1000"),
    ):
        quota = await svc._get_work_order_inbound_quota(1, 10)

    compute_cap.assert_not_called()
    assert quota["picking_kit_sets_cap"] is None
    assert quota["pending"] == 90.0