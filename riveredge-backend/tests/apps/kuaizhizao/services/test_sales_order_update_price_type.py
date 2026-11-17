from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from apps.common.base_service import AppBaseService
from apps.kuaizhizao.services import sales_order_service as module
from apps.kuaizhizao.schemas.sales_order import SalesOrderUpdate, SalesOrderItemCreate
from apps.kuaizhizao.services.document_relation_service import DocumentRelationService
from apps.kuaizhizao.services.demand_change_event_service import DemandChangeEventService
from apps.kuaizhizao.models.work_order import WorkOrder


@pytest.mark.asyncio
@pytest.mark.parametrize("submitted,stored,expected", [(None, "tax_exclusive", "tax_exclusive"), ("", "tax_exclusive", "tax_exclusive"), (None, None, module.DEFAULT_SALES_PRICE_TYPE), ("tax_inclusive", "tax_exclusive", "tax_inclusive")])
async def test_item_update_resolves_price_type_and_persists(monkeypatch, submitted, stored, expected):
    @asynccontextmanager
    async def transaction():
        yield None
    monkeypatch.setattr(module, "in_transaction", transaction)
    fields = dict.fromkeys(["order_date", "delivery_date", "customer_contact", "customer_phone", "salesman_name", "shipping_address", "shipping_method", "payment_terms", "notes"])
    order = SimpleNamespace(**fields, customer_name="fixture", total_quantity=1, total_amount=10, price_type=stored, status="草稿", order_code="fixture")
    monkeypatch.setattr(module.SalesOrder, "get_or_none", AsyncMock(return_value=order))
    query = MagicMock(); query.update = AsyncMock(); query.delete = AsyncMock()

    class _AwaitableList(list):
        def __await__(self):
            async def _r():
                return self
            return _r().__await__()

    query.order_by = MagicMock(side_effect=lambda *a, **kw: _AwaitableList())
    monkeypatch.setattr(module.SalesOrder, "filter", lambda **kw: query)
    monkeypatch.setattr(module.SalesOrderItem, "filter", lambda **kw: query)
    create = AsyncMock()
    monkeypatch.setattr(module.SalesOrderItem, "create", create)
    bulk_create = AsyncMock()
    monkeypatch.setattr(module.SalesOrderItem, "bulk_create", bulk_create)
    monkeypatch.setattr(AppBaseService, "get_user_name", AsyncMock(return_value="fixture"))
    monkeypatch.setattr(DocumentRelationService, "apply_upstream_change_impact", AsyncMock())
    monkeypatch.setattr(DemandChangeEventService, "create_event", AsyncMock())
    works = MagicMock(); works.values_list = AsyncMock(return_value=[])
    monkeypatch.setattr(WorkOrder, "filter", lambda **kw: works)
    monkeypatch.setattr(module, "SalesOrderResponse", lambda **kw: SimpleNamespace(**kw))
    obj = module.SalesOrderService()
    monkeypatch.setattr(obj, "_assert_sales_order_capability_for_order", AsyncMock())
    monkeypatch.setattr(obj, "_load_material_master_map", AsyncMock(return_value={}))

    async def _passthrough(tenant_id, *, partner_type, partner_id, lines, material_id_key="material_id"):
        return [dict(r) for r in lines]

    monkeypatch.setattr(module, "enrich_line_dicts_with_partner_snapshots", _passthrough)
    monkeypatch.setattr(obj, "get_sales_order_by_id", AsyncMock(return_value=SimpleNamespace(model_dump=lambda: {"id": 1})))
    monkeypatch.setattr(obj, "_log_state_transition", AsyncMock())
    monkeypatch.setattr(obj, "_sync_demand_if_exists", AsyncMock(return_value=False))
    pricing = MagicMock(wraps=obj._process_sales_order_item_pricing)
    monkeypatch.setattr(obj, "_process_sales_order_item_pricing", pricing)
    item = SalesOrderItemCreate(material_id=1, material_code="M1", material_name="fixture", required_quantity=2, delivery_date=date(2026, 9, 7), unit_price=10, tax_rate=0)
    data = SalesOrderUpdate(items=[item], **({"price_type": submitted} if submitted is not None else {}))
    result = await obj.update_sales_order(1, 1, data, 7)
    assert result.id == 1
    assert pricing.call_args.kwargs["price_type"] == expected
    if submitted is not None:
        assert query.update.call_args_list[0].kwargs["price_type"] == expected
    created_items = bulk_create.call_args.args[0]
    assert created_items[0].order_quantity == Decimal(2)
    assert created_items[0].total_amount == Decimal(20)


@pytest.mark.asyncio
async def test_assert_capability_non_update_action_resolves_context(monkeypatch):
    """回归：非 update 动作不得在 asyncio.gather 之前读 production_fulfillable_map。"""
    import apps.kuaizhizao.services.document_action_policy.enricher as enricher_mod
    import apps.kuaizhizao.utils.sales_order_push_qty as push_qty_mod
    import apps.kuaizhizao.services.sales_order_purchase_push as purchase_push_mod
    import apps.kuaizhizao.services.sales_order_code_sync as code_sync_mod

    monkeypatch.setattr(enricher_mod, "resolve_review_submitted_for_document", AsyncMock(return_value=False))
    monkeypatch.setattr(enricher_mod, "_order_prepayment_linked_by_ids", AsyncMock(return_value={}))
    monkeypatch.setattr(push_qty_mod, "get_pushable_qty_for_order_items", AsyncMock(return_value={}))
    monkeypatch.setattr(purchase_push_mod, "batch_has_purchasable_remaining", AsyncMock(return_value={}))
    monkeypatch.setattr(purchase_push_mod, "batch_has_production_fulfillable_remaining", AsyncMock(return_value={}))
    monkeypatch.setattr(purchase_push_mod, "require_purchase_requisition_for_tenant", AsyncMock(return_value=False))
    monkeypatch.setattr(code_sync_mod, "list_sales_order_active_downstream_documents", AsyncMock(return_value=[]))
    monkeypatch.setattr(module, "finance_orm_ready", lambda: False)
    monkeypatch.setattr(module.BusinessConfigService, "require_shipment_notice_before_delivery", AsyncMock(return_value=False))

    obj = module.SalesOrderService()
    monkeypatch.setattr(obj, "_get_linked_demand", AsyncMock(return_value=None))
    monkeypatch.setattr(obj, "_order_has_delivery_project", AsyncMock(return_value=False))
    monkeypatch.setattr(
        obj,
        "business_config_service",
        SimpleNamespace(get_sales_require_audit_before_print=AsyncMock(return_value=False)),
    )

    order = SimpleNamespace(id=1, status="草稿", review_status=None, planning_pushed_to_computation=False)
    await obj._assert_sales_order_capability_for_order(1, order, "delete", items=[])
