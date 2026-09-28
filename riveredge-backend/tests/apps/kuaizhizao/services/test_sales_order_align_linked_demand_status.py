"""销售订单关联需求生命周期对齐。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.kuaizhizao.services import sales_order_service as module


@pytest.mark.asyncio
async def test_align_linked_demand_status_updates_mismatch(monkeypatch):
    demand = SimpleNamespace(
        id=2,
        status="DRAFT",
        review_status="PENDING",
        reviewer_id=None,
        reviewer_name=None,
    )
    order = SimpleNamespace(
        id=1,
        status="CONFIRMED",
        review_status="APPROVED",
        reviewer_id=9,
        reviewer_name="审核人",
        review_time="2026-09-28 10:00:00",
    )
    updated = AsyncMock()
    query = MagicMock()
    query.update = updated
    monkeypatch.setattr(module.Demand, "filter", lambda **kw: query)

    obj = module.SalesOrderService()
    monkeypatch.setattr(obj, "_get_linked_demand", AsyncMock(return_value=demand))
    monkeypatch.setattr(module.SalesOrder, "get_or_none", AsyncMock(return_value=order))

    changed = await obj._align_linked_demand_status_from_order(9, 1, 7)
    assert changed is True
    updated.assert_awaited_once()
    kwargs = updated.await_args.kwargs
    assert kwargs["status"] == "CONFIRMED"
    assert kwargs["review_status"] == "APPROVED"
    assert kwargs["reviewer_id"] == 9
    assert kwargs["updated_by"] == 7


@pytest.mark.asyncio
async def test_align_linked_demand_status_noop_when_already_aligned(monkeypatch):
    demand = SimpleNamespace(
        id=2,
        status="AUDITED",
        review_status="APPROVED",
        reviewer_id=3,
        reviewer_name="A",
    )
    order = SimpleNamespace(
        id=1,
        status="AUDITED",
        review_status="APPROVED",
        reviewer_id=3,
        reviewer_name="A",
        review_time=None,
    )
    updated = AsyncMock()
    query = MagicMock()
    query.update = updated
    monkeypatch.setattr(module.Demand, "filter", lambda **kw: query)

    obj = module.SalesOrderService()
    monkeypatch.setattr(obj, "_get_linked_demand", AsyncMock(return_value=demand))
    monkeypatch.setattr(module.SalesOrder, "get_or_none", AsyncMock(return_value=order))

    changed = await obj._align_linked_demand_status_from_order(9, 1, 7)
    assert changed is False
    updated.assert_not_awaited()


@pytest.mark.asyncio
async def test_push_aligns_existing_demand_before_computation(monkeypatch):
    order = SimpleNamespace(id=1, status="CONFIRMED", review_status="APPROVED")
    demand = SimpleNamespace(id=2, status="DRAFT", review_status="PENDING")
    aligned = SimpleNamespace(id=2, status="CONFIRMED", review_status="APPROVED")

    obj = module.SalesOrderService()
    monkeypatch.setattr(module.SalesOrder, "get_or_none", AsyncMock(return_value=order))
    monkeypatch.setattr(obj, "_assert_sales_order_capability_for_order", AsyncMock())
    monkeypatch.setattr(
        obj,
        "_get_linked_demand",
        AsyncMock(side_effect=[demand, aligned]),
    )
    align = AsyncMock(return_value=True)
    monkeypatch.setattr(obj, "_align_linked_demand_status_from_order", align)
    create = AsyncMock()
    monkeypatch.setattr(obj, "_create_demand_from_sales_order", create)

    push = AsyncMock(return_value={"success": True})
    demand_svc = MagicMock()
    demand_svc.push_to_computation = push
    monkeypatch.setattr(
        "apps.kuaizhizao.services.demand_service.DemandService",
        lambda: demand_svc,
    )

    result = await obj.push_sales_order_to_computation(9, 1, 7)
    assert result["success"] is True
    align.assert_awaited_once_with(9, 1, 7)
    create.assert_not_awaited()
    push.assert_awaited_once_with(tenant_id=9, demand_id=2, created_by=7)
