"""KR-PG4：内部单据关系删除、更新、创建走统一入口。"""

from __future__ import annotations

from contextlib import ExitStack, asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infra.exceptions.exceptions import BusinessLogicError, NotFoundError


def _txn():
    @asynccontextmanager
    async def _cm():
        yield None

    return _cm()


def _qs(*, rows=None, updated=0):
    query = MagicMock()
    query.all = AsyncMock(return_value=list(rows or []))
    query.update = AsyncMock(return_value=updated)
    query.delete = AsyncMock()
    return query


@pytest.mark.asyncio
async def test_delete_purchase_order_zero_relations_still_soft_deletes():
    from apps.kuaizhizao.services.purchase_service import PurchaseService

    order = SimpleNamespace(id=3, order_code="PO-1")
    order_update = AsyncMock()
    item_delete = AsyncMock()
    rel_svc = MagicMock()
    rel_svc.delete_relation = AsyncMock(return_value=1)
    svc = PurchaseService()
    svc._sync_requisition_on_po_delete = AsyncMock()

    with (
        patch(
            "apps.kuaizhizao.services.purchase_service.PurchaseOrder.get_or_none",
            new=AsyncMock(return_value=order),
        ),
        patch(
            "apps.kuaizhizao.services.document_action_policy.enricher.purchase_order_has_downstream",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "apps.kuaizhizao.services.purchase_service.assert_purchase_order_capability",
        ),
        patch(
            "apps.kuaizhizao.services.purchase_service.in_transaction",
            _txn,
        ),
        patch(
            "apps.kuaizhizao.models.document_relation.DocumentRelation.filter",
            return_value=_qs(rows=[]),
        ),
        patch(
            "apps.kuaizhizao.services.document_relation_new_service.DocumentRelationNewService",
            return_value=rel_svc,
        ),
        patch(
            "apps.kuaizhizao.services.purchase_service.PurchaseOrderItem.filter",
            return_value=_qs(),
        ) as item_filter,
        patch(
            "apps.kuaizhizao.services.purchase_service.PurchaseOrder.filter",
            return_value=MagicMock(update=order_update),
        ),
    ):
        item_filter.return_value.delete = item_delete
        deleted = await svc.delete_purchase_order(1, 3)

    assert deleted is True
    rel_svc.delete_relation.assert_not_called()
    order_update.assert_awaited()
    kwargs = order_update.await_args.kwargs
    assert kwargs["deleted_at"] is not None


@pytest.mark.asyncio
async def test_delete_purchase_order_relation_failure_does_not_soft_delete():
    from apps.kuaizhizao.services.purchase_service import PurchaseService

    order = SimpleNamespace(id=3, order_code="PO-1")
    order_update = AsyncMock()
    item_delete = AsyncMock()
    rel_svc = MagicMock()
    rel_svc.delete_relation = AsyncMock(side_effect=RuntimeError("relation delete failed"))
    svc = PurchaseService()
    svc._sync_requisition_on_po_delete = AsyncMock()

    with (
        patch(
            "apps.kuaizhizao.services.purchase_service.PurchaseOrder.get_or_none",
            new=AsyncMock(return_value=order),
        ),
        patch(
            "apps.kuaizhizao.services.document_action_policy.enricher.purchase_order_has_downstream",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "apps.kuaizhizao.services.purchase_service.assert_purchase_order_capability",
        ),
        patch(
            "apps.kuaizhizao.services.purchase_service.in_transaction",
            _txn,
        ),
        patch(
            "apps.kuaizhizao.models.document_relation.DocumentRelation.filter",
            return_value=_qs(rows=[SimpleNamespace(id=11)]),
        ),
        patch(
            "apps.kuaizhizao.services.document_relation_new_service.DocumentRelationNewService",
            return_value=rel_svc,
        ),
        patch(
            "apps.kuaizhizao.services.purchase_service.PurchaseOrderItem.filter",
            return_value=MagicMock(delete=item_delete),
        ),
        patch(
            "apps.kuaizhizao.services.purchase_service.PurchaseOrder.filter",
            return_value=MagicMock(update=order_update),
        ),
    ):
        with pytest.raises(RuntimeError, match="relation delete failed"):
            await svc.delete_purchase_order(1, 3)

    order_update.assert_not_called()
    item_delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_purchase_order_missing_relation_row_still_soft_deletes():
    from apps.kuaizhizao.services.purchase_service import PurchaseService

    order = SimpleNamespace(id=3, order_code="PO-1")
    order_update = AsyncMock()
    rel_svc = MagicMock()
    rel_svc.delete_relation = AsyncMock(side_effect=NotFoundError("关联关系不存在"))
    svc = PurchaseService()
    svc._sync_requisition_on_po_delete = AsyncMock()

    with (
        patch(
            "apps.kuaizhizao.services.purchase_service.PurchaseOrder.get_or_none",
            new=AsyncMock(return_value=order),
        ),
        patch(
            "apps.kuaizhizao.services.document_action_policy.enricher.purchase_order_has_downstream",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "apps.kuaizhizao.services.purchase_service.assert_purchase_order_capability",
        ),
        patch(
            "apps.kuaizhizao.services.purchase_service.in_transaction",
            _txn,
        ),
        patch(
            "apps.kuaizhizao.models.document_relation.DocumentRelation.filter",
            return_value=_qs(rows=[SimpleNamespace(id=11)]),
        ),
        patch(
            "apps.kuaizhizao.services.document_relation_new_service.DocumentRelationNewService",
            return_value=rel_svc,
        ),
        patch(
            "apps.kuaizhizao.services.purchase_service.PurchaseOrderItem.filter",
            return_value=_qs(),
        ),
        patch(
            "apps.kuaizhizao.services.purchase_service.PurchaseOrder.filter",
            return_value=MagicMock(update=order_update),
        ),
    ):
        deleted = await svc.delete_purchase_order(1, 3)

    assert deleted is True
    order_update.assert_awaited()


@pytest.mark.asyncio
async def test_create_computation_existing_relation_continues():
    from apps.kuaizhizao.schemas.demand_computation import DemandComputationCreate
    from apps.kuaizhizao.services.demand_computation_service import DemandComputationService

    demand = SimpleNamespace(
        id=1,
        business_mode="MTS",
        demand_type="sales_order",
        demand_code="D001",
        source_code="SO1",
    )
    rel_svc = MagicMock()
    rel_svc.create_relation = AsyncMock(side_effect=BusinessLogicError("关联关系已存在"))
    demand_svc = MagicMock()
    demand_svc.sync_upstream_planning_on_push = AsyncMock()
    svc = DemandComputationService()
    svc._generate_computation_code = AsyncMock(return_value="MRP001")
    svc._build_computation_response = AsyncMock(return_value="built")

    with (
        patch(
            "apps.kuaizhizao.services.demand_computation_service.Demand.get_or_none",
            new=AsyncMock(return_value=demand),
        ),
        patch(
            "apps.kuaizhizao.services.document_action_policy.demand.assert_demand_capability",
        ),
        patch(
            "apps.kuaizhizao.services.demand_computation_service.in_transaction",
            _txn,
        ),
        patch(
            "apps.kuaizhizao.services.demand_computation_service.User.get_or_none",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "apps.kuaizhizao.services.demand_computation_service.DemandComputation.create",
            new=AsyncMock(return_value=SimpleNamespace(id=50)),
        ),
        patch(
            "apps.kuaizhizao.services.demand_computation_service.Demand.filter",
            return_value=MagicMock(update=AsyncMock()),
        ),
        patch(
            "apps.kuaizhizao.services.demand_service.DemandService",
            return_value=demand_svc,
        ),
        patch(
            "apps.kuaizhizao.services.document_relation_new_service.DocumentRelationNewService",
            return_value=rel_svc,
        ),
    ):
        result = await svc.create_computation(
            1,
            DemandComputationCreate(demand_id=1, computation_params={}),
            9,
        )

    assert result == "built"
    rel_svc.create_relation.assert_awaited()


@pytest.mark.asyncio
async def test_create_computation_other_relation_error_propagates():
    from apps.kuaizhizao.schemas.demand_computation import DemandComputationCreate
    from apps.kuaizhizao.services.demand_computation_service import DemandComputationService

    demand = SimpleNamespace(
        id=1,
        business_mode="MTS",
        demand_type="sales_order",
        demand_code="D001",
        source_code="SO1",
    )
    rel_svc = MagicMock()
    rel_svc.create_relation = AsyncMock(side_effect=BusinessLogicError("关系写入失败"))
    demand_svc = MagicMock()
    demand_svc.sync_upstream_planning_on_push = AsyncMock()
    svc = DemandComputationService()
    svc._generate_computation_code = AsyncMock(return_value="MRP001")
    svc._build_computation_response = AsyncMock(return_value="built")

    with (
        patch(
            "apps.kuaizhizao.services.demand_computation_service.Demand.get_or_none",
            new=AsyncMock(return_value=demand),
        ),
        patch(
            "apps.kuaizhizao.services.document_action_policy.demand.assert_demand_capability",
        ),
        patch(
            "apps.kuaizhizao.services.demand_computation_service.in_transaction",
            _txn,
        ),
        patch(
            "apps.kuaizhizao.services.demand_computation_service.User.get_or_none",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "apps.kuaizhizao.services.demand_computation_service.DemandComputation.create",
            new=AsyncMock(return_value=SimpleNamespace(id=50)),
        ),
        patch(
            "apps.kuaizhizao.services.demand_computation_service.Demand.filter",
            return_value=MagicMock(update=AsyncMock()),
        ),
        patch(
            "apps.kuaizhizao.services.demand_service.DemandService",
            return_value=demand_svc,
        ),
        patch(
            "apps.kuaizhizao.services.document_relation_new_service.DocumentRelationNewService",
            return_value=rel_svc,
        ),
    ):
        with pytest.raises(BusinessLogicError, match="关系写入失败"):
            await svc.create_computation(
                1,
                DemandComputationCreate(demand_id=1, computation_params={}),
                9,
            )

    svc._build_computation_response.assert_not_called()


@pytest.mark.asyncio
async def test_invoice_repair_skips_notes_when_amount_already_matches():
    from apps.kuaicaiwu.services.invoice_merge_allocation_repair import (
        InvoiceMergeAllocationRepairService,
    )
    from apps.kuaicaiwu.services.invoice_source_allocation import (
        encode_relation_allocated_amount,
    )

    amount = Decimal("12.50")
    rel = SimpleNamespace(
        id=4,
        source_id=2,
        notes=encode_relation_allocated_amount(amount),
    )
    rel_svc = MagicMock()
    rel_svc.update_relation_notes = AsyncMock()
    rel_svc.create_relation = AsyncMock()
    svc = InvoiceMergeAllocationRepairService()

    with patch(
        "apps.kuaizhizao.services.document_relation_new_service.DocumentRelationNewService",
        return_value=rel_svc,
    ):
        changed = await svc._apply_relation_allocations(
            tenant_id=1,
            rels=[rel],
            source_type="receivable",
            target_type="sales_invoice",
            invoice_id=8,
            invoice_code="INV-8",
            allocations={2: amount},
            code_by_id={2: "R2"},
            dry_run=False,
        )

    assert changed is False
    rel_svc.update_relation_notes.assert_not_called()
    rel_svc.create_relation.assert_not_called()


@pytest.mark.asyncio
async def test_invoice_repair_existing_relation_writes_target_notes():
    from apps.kuaicaiwu.services.invoice_merge_allocation_repair import (
        InvoiceMergeAllocationRepairService,
    )
    from apps.kuaicaiwu.services.invoice_source_allocation import (
        encode_relation_allocated_amount,
    )

    amount = Decimal("3.50")
    rel_svc = MagicMock()
    rel_svc.create_relation = AsyncMock(side_effect=BusinessLogicError("关联关系已存在"))
    rel_svc.update_relation_notes = AsyncMock()
    existing = SimpleNamespace(id=77)
    svc = InvoiceMergeAllocationRepairService()

    with (
        patch(
            "apps.kuaizhizao.services.document_relation_new_service.DocumentRelationNewService",
            return_value=rel_svc,
        ),
        patch(
            "apps.kuaicaiwu.services.invoice_merge_allocation_repair.DocumentRelation.get_or_none",
            new=AsyncMock(return_value=existing),
        ),
    ):
        changed = await svc._apply_relation_allocations(
            tenant_id=1,
            rels=[],
            source_type="payable",
            target_type="purchase_invoice",
            invoice_id=6,
            invoice_code="PI-6",
            allocations={2: amount},
            code_by_id={2: "P2"},
            dry_run=False,
        )

    assert changed is True
    rel_svc.update_relation_notes.assert_awaited_once_with(
        1,
        77,
        encode_relation_allocated_amount(amount),
    )


@pytest.mark.asyncio
async def test_invoice_repair_notes_write_failure_propagates():
    from apps.kuaicaiwu.services.invoice_merge_allocation_repair import (
        InvoiceMergeAllocationRepairService,
    )

    rel = SimpleNamespace(id=4, source_id=2, notes=None)
    rel_svc = MagicMock()
    rel_svc.update_relation_notes = AsyncMock(side_effect=RuntimeError("notes write failed"))
    rel_svc.create_relation = AsyncMock()
    svc = InvoiceMergeAllocationRepairService()

    with patch(
        "apps.kuaizhizao.services.document_relation_new_service.DocumentRelationNewService",
        return_value=rel_svc,
    ):
        with pytest.raises(RuntimeError, match="notes write failed"):
            await svc._apply_relation_allocations(
                tenant_id=1,
                rels=[rel],
                source_type="receivable",
                target_type="sales_invoice",
                invoice_id=8,
                invoice_code="INV-8",
                allocations={2: Decimal("9.00")},
                code_by_id={2: "R2"},
                dry_run=False,
            )

    rel_svc.create_relation.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_source_only_leaves_target_untouched_when_zero_rows():
    from apps.kuaizhizao.services.document_relation_new_service import (
        DocumentRelationNewService,
    )

    source_qs = _qs(updated=0)
    target_qs = _qs(updated=3)

    def _filter(**kwargs):
        if "source_type" in kwargs:
            return source_qs
        if "target_type" in kwargs:
            return target_qs
        raise AssertionError(kwargs)

    with patch(
        "apps.kuaizhizao.services.document_relation_new_service.DocumentRelation.filter",
        side_effect=_filter,
    ):
        updated = await DocumentRelationNewService().refresh_document_code_snapshots(
            1,
            document_type="sales_order",
            document_id=5,
            code="SO-9",
            refresh_source=True,
            refresh_target=False,
        )

    assert updated == 0
    source_qs.update.assert_awaited()
    target_qs.update.assert_not_called()


@pytest.mark.asyncio
async def test_sales_order_code_sync_refreshes_source_only():
    from apps.kuaizhizao.services.sales_order_code_sync import sync_sales_order_code_snapshots

    empty = SimpleNamespace(_meta=SimpleNamespace(fields_map={}))
    loaders = (
        "_lazy_work_order_model",
        "_lazy_sales_delivery_model",
        "_lazy_shipment_notice_model",
        "_lazy_sales_return_model",
        "_lazy_delivery_notice_model",
        "_lazy_delivery_project_model",
        "_lazy_oqc_inspection_model",
        "_lazy_finished_goods_receipt_model",
        "_lazy_finished_goods_inspection_model",
        "_lazy_after_sales_ticket_model",
        "_lazy_after_sales_service_model",
        "_lazy_quotation_model",
    )
    rel_svc = MagicMock()
    rel_svc.refresh_document_code_snapshots = AsyncMock(return_value=0)
    demand_qs = MagicMock()
    demand_qs.update = AsyncMock()

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "apps.kuaizhizao.models.demand.Demand.filter",
                return_value=demand_qs,
            )
        )
        stack.enter_context(
            patch(
                "apps.kuaizhizao.services.document_relation_new_service.DocumentRelationNewService",
                return_value=rel_svc,
            )
        )
        for name in loaders:
            stack.enter_context(
                patch(
                    f"apps.kuaizhizao.services.sales_order_code_sync.{name}",
                    return_value=empty,
                )
            )
        await sync_sales_order_code_snapshots(1, 9, "SO-NEW")

    rel_svc.refresh_document_code_snapshots.assert_awaited_once_with(
        1,
        document_type="sales_order",
        document_id=9,
        code="SO-NEW",
        refresh_source=True,
        refresh_target=False,
    )


@pytest.mark.asyncio
async def test_non_sales_code_sync_refreshes_both_sides_sales_order_does_not():
    from core.services.document_code_service import sync_document_code_snapshots

    sales_sync = AsyncMock()
    both = MagicMock()
    both.refresh_document_code_snapshots = AsyncMock(return_value=0)

    with (
        patch(
            "core.services.document_code_service.resolve_document_code_page_entry",
            return_value=None,
        ),
        patch(
            "apps.kuaizhizao.services.sales_order_code_sync.sync_sales_order_code_snapshots",
            new=sales_sync,
        ),
        patch(
            "apps.kuaizhizao.services.document_relation_new_service.DocumentRelationNewService",
            return_value=both,
        ),
    ):
        await sync_document_code_snapshots(
            1,
            "kuaizhizao-sales-order",
            9,
            "SO-NEW",
            document_type="sales_order",
        )
        await sync_document_code_snapshots(
            1,
            "kuaizhizao-purchase-order",
            4,
            "PO-NEW",
            document_type="purchase_order",
        )

    sales_sync.assert_awaited_once()
    both.refresh_document_code_snapshots.assert_awaited_once_with(
        1,
        document_type="purchase_order",
        document_id=4,
        code="PO-NEW",
        refresh_source=True,
        refresh_target=True,
    )
