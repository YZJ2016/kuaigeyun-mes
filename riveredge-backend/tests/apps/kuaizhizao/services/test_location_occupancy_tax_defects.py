"""无库位撤回、采购入库占用清理、采购订单行税率回落。不连库。"""

from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from apps.kuaicaiwu.services.purchase_receipt_line_finance_occupancy_service import (
    PurchaseReceiptLineFinanceOccupancyService,
)
from apps.kuaicaiwu.services.purchase_settlement import resolve_purchase_line_tax_rate_percent
from apps.kuaizhizao.models.material_stock_movement import MaterialStockMovement
from apps.kuaizhizao.schemas.purchase import PurchaseOrderItemCreate
from apps.kuaizhizao.services.inventory_service import InventoryService
from apps.kuaizhizao.services.purchase_service import PurchaseService
from apps.kuaizhizao.services.semi_finished_goods_receipt_service import (
    SemiFinishedGoodsReceiptService,
)
from apps.kuaizhizao.services.warehouse_service import (
    FinishedGoodsReceiptService,
    OtherOutboundService,
    PurchaseReceiptService,
)
from infra.exceptions.exceptions import BusinessLogicError


@pytest.fixture(autouse=True)
def _stub_kingdee_withdraw_sync():
    """撤回钩子：金蝶回写属外围集成，单测内 stub 掉避免触真 ORM。"""
    with patch(
        "apps.kuaiconnect.services.document_push.kingdee_im_warehouse_revoke_service"
        ".sync_im_warehouse_kingdee_after_withdraw",
        new=AsyncMock(return_value=None),
    ), patch(
        "apps.kuaiconnect.services.document_push.kingdee_purchase_receipt_revoke_service"
        ".sync_purchase_receipt_kingdee_after_withdraw",
        new=AsyncMock(return_value=None),
    ):
        yield


def _po_line(**overrides):
    payload = dict(
        material_id=1,
        material_code="M1",
        material_name="物料",
        ordered_quantity=Decimal("1"),
        unit="个",
        unit_price=Decimal("113"),
        total_price=Decimal("113"),
        required_date=date(2026, 1, 2),
    )
    payload.update(overrides)
    return PurchaseOrderItemCreate(**payload)


def test_purchase_order_line_omitted_tax_uses_header_and_explicit_zero_stays_zero():
    with pytest.raises(ValidationError):
        _po_line()
    explicit_zero = _po_line(tax_rate=Decimal("0"))
    assert explicit_zero.tax_rate == Decimal("0")
    assert resolve_purchase_line_tax_rate_percent(
        line_tax_rate=None,
        header_tax_rate=Decimal("0.13"),
    ) == Decimal("13.00")
    assert resolve_purchase_line_tax_rate_percent(
        line_tax_rate=explicit_zero.tax_rate,
        header_tax_rate=Decimal("0.13"),
    ) == Decimal("0")

    omitted_excl = PurchaseService._po_line_excl_total_from_form_item(
        qty=Decimal("1"),
        item_data=SimpleNamespace(
            total_price=None,
            tax_rate=None,
            display_unit_price=Decimal("113"),
            unit_price=Decimal("113"),
        ),
        order_price_type="tax_inclusive",
        header_tax_rate=Decimal("0.13"),
        price_decimal_places=4,
        amount_decimal_places=2,
    )
    zero_excl = PurchaseService._po_line_excl_total_from_form_item(
        qty=Decimal("1"),
        item_data=SimpleNamespace(
            total_price=None,
            tax_rate=0,
            display_unit_price=Decimal("113"),
            unit_price=Decimal("113"),
        ),
        order_price_type="tax_inclusive",
        header_tax_rate=Decimal("0.13"),
        price_decimal_places=4,
        amount_decimal_places=2,
    )
    assert omitted_excl == Decimal("100.00")
    assert zero_excl == Decimal("113.00")


class _MovementQuery:
    def __init__(self, rows):
        self._rows = rows

    async def all(self):
        return self._rows


def _movement(**kwargs):
    base = dict(
        id=1,
        idempotency_key="other_outbound:5:dec:9@scope1",
        quantity=Decimal("-10"),
        base_quantity=Decimal("-10"),
        location_code="A-01",
        location_id=3,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_unscoped_outbound_restore_adds_back_posted_locations():
    rows = [
        _movement(
            id=1,
            idempotency_key="other_outbound:5:dec:9@old",
            quantity=Decimal("-10"),
            location_code="Z-OLD",
        ),
        _movement(
            id=2,
            idempotency_key="other_outbound:5:dec:9@new",
            quantity=Decimal("-4"),
            base_quantity=Decimal("-4"),
            location_code="B-02",
            location_id=8,
        ),
        _movement(
            id=3,
            idempotency_key="other_outbound:5:dec:9@new#p1",
            quantity=Decimal("-6"),
            base_quantity=Decimal("-6"),
            location_code="A-01",
            location_id=3,
        ),
        _movement(
            id=4,
            idempotency_key="other_outbound:5:dec:90@new",
            quantity=Decimal("-6"),
            location_code="NO",
        ),
    ]
    increase = AsyncMock(return_value=True)
    with patch.object(MaterialStockMovement, "filter", return_value=_MovementQuery(rows)), patch.object(
        InventoryService, "increase_stock", increase
    ):
        await InventoryService.restore_unscoped_outbound_by_posted_locations(
            tenant_id=1,
            material_id=10,
            quantity=Decimal("10"),
            confirm_source_type="other_outbound",
            line_idempotency_key="other_outbound:5:dec:9",
            withdraw_idempotency_key="other_outbound:5:withdraw:9",
            source_doc_id=5,
            warehouse_id=2,
        )
    codes = [call.kwargs["location_code"] for call in increase.await_args_list]
    qtys = [call.kwargs["quantity"] for call in increase.await_args_list]
    assert codes == ["A-01", "B-02"]
    assert qtys == [Decimal("6"), Decimal("4")]
    assert "" not in codes


@pytest.mark.asyncio
async def test_unscoped_outbound_restore_fails_without_movements():
    increase = AsyncMock(return_value=True)
    with patch.object(MaterialStockMovement, "filter", return_value=_MovementQuery([])), patch.object(
        InventoryService, "increase_stock", increase
    ):
        with pytest.raises(BusinessLogicError, match="没有库存流水"):
            await InventoryService.restore_unscoped_outbound_by_posted_locations(
                tenant_id=1,
                material_id=10,
                quantity=Decimal("10"),
                confirm_source_type="other_outbound",
                line_idempotency_key="other_outbound:5:dec:9",
                withdraw_idempotency_key="other_outbound:5:withdraw:9",
                source_doc_id=5,
            )
    increase.assert_not_awaited()


@pytest.mark.asyncio
async def test_unscoped_outbound_restore_fails_when_location_not_recorded():
    increase = AsyncMock(return_value=True)
    row = _movement(location_code=None)
    with patch.object(MaterialStockMovement, "filter", return_value=_MovementQuery([row])), patch.object(
        InventoryService, "increase_stock", increase
    ):
        with pytest.raises(BusinessLogicError, match="未记录库位"):
            await InventoryService.restore_unscoped_outbound_by_posted_locations(
                tenant_id=1,
                material_id=10,
                quantity=Decimal("10"),
                confirm_source_type="other_outbound",
                line_idempotency_key="other_outbound:5:dec:9",
                withdraw_idempotency_key="other_outbound:5:withdraw:9",
                source_doc_id=5,
            )
    increase.assert_not_awaited()


@pytest.mark.asyncio
async def test_unscoped_outbound_restore_adds_posted_batches_not_default():
    rows = [
        _movement(
            id=2,
            idempotency_key="other_outbound:5:dec:9@new",
            quantity=Decimal("-4"),
            base_quantity=Decimal("-4"),
            location_code="",
            location_id=None,
            batch_no="LOT-A",
        ),
        _movement(
            id=3,
            idempotency_key="other_outbound:5:dec:9@new#p1",
            quantity=Decimal("-6"),
            base_quantity=Decimal("-6"),
            location_code="",
            location_id=None,
            batch_no="LOT-B",
        ),
    ]
    increase = AsyncMock(return_value=True)
    with patch.object(MaterialStockMovement, "filter", return_value=_MovementQuery(rows)), patch.object(
        InventoryService, "increase_stock", increase
    ):
        await InventoryService.restore_unscoped_outbound_by_posted_locations(
            tenant_id=1,
            material_id=10,
            quantity=Decimal("10"),
            confirm_source_type="other_outbound",
            line_idempotency_key="other_outbound:5:dec:9",
            withdraw_idempotency_key="other_outbound:5:withdraw:9",
            source_doc_id=5,
            warehouse_id=2,
            batch_no=None,
        )
    batches = [call.kwargs["batch_no"] for call in increase.await_args_list]
    qtys = [call.kwargs["quantity"] for call in increase.await_args_list]
    assert batches == ["LOT-A", "LOT-B"]
    assert qtys == [Decimal("4"), Decimal("6")]
    assert "DEFAULT" not in batches
    assert all(call.kwargs["exact_batch_no"] is True for call in increase.await_args_list)


@pytest.mark.asyncio
async def test_null_location_batch_restore_does_not_create_blank_location_row():
    batch = SimpleNamespace(
        id=8,
        location_code=None,
        location_id=None,
        quantity=Decimal("2"),
        base_quantity=Decimal("2"),
        aux_quantity=Decimal("2"),
        batch_no="LOT-1",
        deleted_at=None,
        warehouse_name="主仓",
        status="out_stock",
        production_date=date(2026, 1, 1),
        expiry_date=date(2026, 12, 1),
        save=AsyncMock(),
    )
    locked = MagicMock()
    locked.filter.return_value = locked
    locked.select_for_update.return_value = locked
    locked.first = AsyncMock(return_value=batch)
    create = AsyncMock()
    with patch(
        "apps.master_data.models.material_batch.MaterialBatch.filter",
        return_value=locked,
    ), patch(
        "apps.master_data.models.material_batch.MaterialBatch.create",
        create,
    ), patch(
        "apps.master_data.models.material.Material.get_or_none",
        new=AsyncMock(return_value=None),
    ):
        await InventoryService._material_batch_increase_or_restore(
            tenant_id=1,
            material_id=10,
            batch_no="LOT-1",
            quantity=Decimal("3"),
            base_quantity=Decimal("3"),
            warehouse_id=2,
            warehouse_name="主仓",
            match_null_location=True,
            exact_batch_no=True,
        )
    assert batch.quantity == Decimal("5")
    assert batch.location_code is None
    create.assert_not_awaited()

    rows = [
        _movement(
            id=2,
            idempotency_key="sales_delivery:5:dec:9@new",
            quantity=Decimal("-3"),
            base_quantity=Decimal("-3"),
            location_code=None,
            location_id=0,
            batch_no="LOT-1",
        )
    ]
    increase = AsyncMock(return_value=True)
    with patch.object(MaterialStockMovement, "filter", return_value=_MovementQuery(rows)), patch.object(
        InventoryService, "increase_stock", increase
    ), patch.object(
        InventoryService, "_null_location_restore_kind", AsyncMock(return_value="batch")
    ):
        await InventoryService.restore_unscoped_outbound_by_posted_locations(
            tenant_id=1,
            material_id=10,
            quantity=Decimal("3"),
            confirm_source_type="sales_delivery",
            line_idempotency_key="sales_delivery:5:dec:9",
            withdraw_idempotency_key="sales_delivery:5:withdraw:9",
            source_doc_id=5,
            warehouse_id=2,
            batch_no="",
        )
    assert increase.await_args.kwargs["batch_no"] == "LOT-1"
    assert increase.await_args.kwargs["match_null_location"] is True
    assert "location_code" not in increase.await_args.kwargs

    line_increase = AsyncMock(return_value=True)
    with patch.object(MaterialStockMovement, "filter", return_value=_MovementQuery(rows)), patch.object(
        InventoryService, "increase_stock", line_increase
    ), patch.object(
        InventoryService, "_null_location_restore_kind", AsyncMock(return_value="line_side")
    ), patch(
        "apps.master_data.models.material_batch.MaterialBatch.create",
        create,
    ):
        await InventoryService.restore_unscoped_outbound_by_posted_locations(
            tenant_id=1,
            material_id=10,
            quantity=Decimal("3"),
            confirm_source_type="sales_delivery",
            line_idempotency_key="sales_delivery:5:dec:9",
            withdraw_idempotency_key="sales_delivery:5:withdraw:9",
            source_doc_id=5,
            warehouse_id=8,
            batch_no="LOT-1",
        )
    assert "location_code" not in line_increase.await_args.kwargs
    assert line_increase.await_args.kwargs.get("match_null_location") is not True
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_finished_goods_revoke_negative_does_not_deduct_other_location():
    wh = MagicMock()
    wh.warehouse_type = "normal"
    other_bin = SimpleNamespace(
        id=4,
        location_code="OTHER",
        batch_no="DEFAULT",
        quantity=Decimal("9"),
        warehouse_id=2,
    )
    find_other = AsyncMock(return_value=other_bin)
    empty_qs = MagicMock()
    empty_qs.filter.return_value = empty_qs
    empty_qs.select_for_update.return_value = empty_qs
    empty_qs.order_by.return_value = empty_qs
    empty_qs.all = AsyncMock(return_value=[])
    empty_qs.first = AsyncMock(return_value=None)
    create_mock = AsyncMock()

    @asynccontextmanager
    async def _noop_posting_tx():
        conn = MagicMock()
        conn.execute_query = AsyncMock(return_value=None)
        yield conn

    dedup = MagicMock()
    dedup.using_db.return_value = dedup
    dedup.values_list = AsyncMock(return_value=[])
    with patch(
        "apps.kuaizhizao.utils.stock_posting.reuse_or_begin_transaction",
        _noop_posting_tx,
    ), patch(
        "apps.kuaizhizao.models.material_stock_movement.MaterialStockMovement.filter",
        return_value=dedup,
    ), patch(
        "apps.kuaizhizao.services.inventory_service.InventoryService._get_allow_negative_inventory",
        new=AsyncMock(return_value=True),
    ), patch(
        "apps.master_data.models.warehouse.Warehouse.get_or_none",
        new=AsyncMock(return_value=wh),
    ), patch(
        "apps.kuaizhizao.services.inventory_service.InventoryService._get_warehouse_management_flags",
        new=AsyncMock(return_value=(False, False)),
    ), patch(
        "apps.kuaizhizao.services.inventory_service.BusinessConfigService"
    ) as cfg_cls, patch(
        "apps.master_data.models.material.Material.get_or_none",
        new=AsyncMock(return_value=MagicMock(batch_managed=False, name="M", code="M1", main_code="M1")),
    ), patch(
        "apps.master_data.models.material_batch.MaterialBatch.filter",
        return_value=empty_qs,
    ), patch(
        "apps.master_data.models.material_batch.MaterialBatch.create",
        create_mock,
    ), patch(
        "apps.kuaizhizao.services.inventory_service.InventoryService._find_in_stock_material_batch",
        find_other,
    ), patch(
        "apps.kuaizhizao.services.inventory_service.InventoryService._record_stock_movement",
        new=AsyncMock(),
    ), patch(
        "apps.kuaizhizao.services.inventory_service.InventoryService._mark_serials_out_stock",
        new=AsyncMock(),
    ), patch(
        "apps.kuaizhizao.services.work_order_readiness_service.notify_inventory_changed",
        return_value=None,
    ), patch(
        "apps.kuaizhizao.services.inventory_service.InventoryService._resolve_warehouse_name",
        new=AsyncMock(return_value="成品仓"),
    ):
        cfg_cls.return_value.get_business_config = AsyncMock(
            return_value={"parameters": {"warehouse": {"lifo": False, "fifo_mode": "batch_id"}}}
        )
        ok = await InventoryService._decrease_stock_no_atomic(
            tenant_id=1,
            material_id=10,
            quantity=Decimal("5"),
            warehouse_id=2,
            location_code="FG-01",
            location_scoped=True,
            movement_type="fg_receipt_withdraw",
            source_type="finished_goods_receipt_revoke",
            source_doc_id=4,
            operator_id=7,
            operator_name="tester",
            idempotency_key="finished_goods_receipt:4:revoke:8",
        )
    assert ok is True
    find_other.assert_not_awaited()
    assert other_bin.quantity == Decimal("9")
    assert other_bin.location_code == "OTHER"
    create_mock.assert_awaited_once()
    assert create_mock.await_args.kwargs["location_code"] == "FG-01"
    assert create_mock.await_args.kwargs["quantity"] == Decimal("-5")


@asynccontextmanager
async def _noop_tx(*_args, **_kwargs):
    yield MagicMock()


@asynccontextmanager
async def _noop_guard(*_args, **_kwargs):
    yield


@pytest.mark.asyncio
async def test_other_outbound_withdraw_without_location_uses_posted_locations():
    outbound = SimpleNamespace(id=5, status="已出库", warehouse_id=2, outbound_code="OB1")
    item = SimpleNamespace(
        id=9,
        material_id=10,
        outbound_quantity=Decimal("10"),
        material_unit="个",
        batch_number=None,
        serial_numbers=None,
        location_code="",
        location_id=None,
        aux_quantity=None,
        unit_conversion_rate=None,
    )
    item_qs = MagicMock()
    item_qs.all = AsyncMock(return_value=[item])
    item_qs.update = AsyncMock()
    header_qs = MagicMock()
    header_qs.update = AsyncMock()
    restore = AsyncMock()
    increase = AsyncMock()
    svc = OtherOutboundService()
    svc.get_other_outbound_by_id = AsyncMock(return_value=outbound)
    with patch(
        "apps.kuaizhizao.services.warehouse_service.in_transaction", _noop_tx
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.stock_document_guard", _noop_guard
    ), patch(
        "apps.kuaizhizao.services.document_action_policy.warehouse_outbound_hub.assert_outbound_hub_capability"
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.OtherOutbound.get",
        new=AsyncMock(return_value=outbound),
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.OtherOutboundItem.filter",
        return_value=item_qs,
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.OtherOutbound.filter",
        return_value=header_qs,
    ), patch(
        "apps.kuaizhizao.services.warehouse_service._load_materials_by_ids",
        new=AsyncMock(return_value={}),
    ), patch.object(
        InventoryService, "restore_unscoped_outbound_by_posted_locations", restore
    ), patch.object(
        InventoryService, "increase_stock", increase
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.OtherOutboundResponse.model_validate",
        return_value=outbound,
    ):
        await svc.withdraw_confirmation(1, 5, 7)
    increase.assert_not_awaited()
    restore.assert_awaited()
    assert restore.await_args.kwargs["line_idempotency_key"] == "other_outbound:5:dec:9"
    assert restore.await_args.kwargs["confirm_source_type"] == "other_outbound"
    assert "location_code" not in restore.await_args.kwargs


@pytest.mark.asyncio
async def test_other_outbound_withdraw_with_location_still_uses_that_location():
    outbound = SimpleNamespace(id=5, status="已出库", warehouse_id=2, outbound_code="OB1")
    item = SimpleNamespace(
        id=9,
        material_id=10,
        outbound_quantity=Decimal("10"),
        material_unit="个",
        batch_number="B1",
        serial_numbers=None,
        location_code="A-01",
        location_id=3,
        aux_quantity=None,
        unit_conversion_rate=None,
    )
    item_qs = MagicMock()
    item_qs.all = AsyncMock(return_value=[item])
    item_qs.update = AsyncMock()
    header_qs = MagicMock()
    header_qs.update = AsyncMock()
    restore = AsyncMock()
    increase = AsyncMock()
    svc = OtherOutboundService()
    svc.get_other_outbound_by_id = AsyncMock(return_value=outbound)
    with patch(
        "apps.kuaizhizao.services.warehouse_service.in_transaction", _noop_tx
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.stock_document_guard", _noop_guard
    ), patch(
        "apps.kuaizhizao.services.document_action_policy.warehouse_outbound_hub.assert_outbound_hub_capability"
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.OtherOutbound.get",
        new=AsyncMock(return_value=outbound),
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.OtherOutboundItem.filter",
        return_value=item_qs,
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.OtherOutbound.filter",
        return_value=header_qs,
    ), patch(
        "apps.kuaizhizao.services.warehouse_service._load_materials_by_ids",
        new=AsyncMock(return_value={}),
    ), patch.object(
        InventoryService, "restore_unscoped_outbound_by_posted_locations", restore
    ), patch.object(
        InventoryService, "increase_stock", increase
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.OtherOutboundResponse.model_validate",
        return_value=outbound,
    ):
        await svc.withdraw_confirmation(1, 5, 7)
    restore.assert_not_awaited()
    assert increase.await_args.kwargs["location_code"] == "A-01"
    assert increase.await_args.kwargs["location_id"] == 3


async def _withdraw_blank_location_receipt(service, method_name, item_model_path, header_model_path, extra_patches):
    receipt = SimpleNamespace(
        id=4,
        status="已入库",
        warehouse_id=6,
        receipt_code="R1",
        work_order_id=None,
    )
    item = SimpleNamespace(
        id=8,
        material_id=10,
        receipt_quantity=Decimal("3"),
        qualified_quantity=Decimal("3"),
        material_unit="个",
        warehouse_id=None,
        location_id=None,
        location_code="",
        batch_number=None,
        serial_numbers=None,
        aux_quantity=None,
        unit_conversion_rate=None,
    )
    item_qs = MagicMock()
    item_qs.all = AsyncMock(return_value=[item])
    item_qs.update = AsyncMock()
    header_qs = MagicMock()
    header_qs.update = AsyncMock()
    decrease = AsyncMock()
    svc = service()
    if hasattr(svc, "get_finished_goods_receipt_by_id"):
        svc.get_finished_goods_receipt_by_id = AsyncMock(return_value=receipt)
    if hasattr(svc, "get_semi_finished_goods_receipt_by_id"):
        svc.get_semi_finished_goods_receipt_by_id = AsyncMock(return_value=receipt)
    patches = [
        patch("apps.kuaizhizao.utils.stock_posting.reuse_or_begin_transaction", _noop_tx),
        patch("apps.kuaizhizao.utils.stock_posting._lock", new=AsyncMock()),
        patch(header_model_path + ".get_or_none", new=AsyncMock(return_value=receipt)),
        patch(item_model_path + ".filter", return_value=item_qs),
        patch(header_model_path + ".filter", return_value=header_qs),
        patch(
            "apps.kuaizhizao.services.inventory_service.InventoryService._decrease_stock_no_atomic",
            decrease,
        ),
        *extra_patches,
    ]
    for item_patch in patches:
        item_patch.start()
    try:
        await getattr(svc, method_name)(1, 4, 7)
    finally:
        for item_patch in reversed(patches):
            item_patch.stop()
    assert decrease.await_args.kwargs["location_scoped"] is True
    assert "location_code" not in decrease.await_args.kwargs


@pytest.mark.asyncio
async def test_finished_goods_withdraw_without_location_does_not_touch_other_bins():
    binding_qs = MagicMock()
    binding_qs.exists = AsyncMock(return_value=False)
    await _withdraw_blank_location_receipt(
        FinishedGoodsReceiptService,
        "withdraw_receipt_confirmation",
        "apps.kuaizhizao.services.warehouse_service.FinishedGoodsReceiptItem",
        "apps.kuaizhizao.services.warehouse_service.FinishedGoodsReceipt",
        [
            patch(
                "apps.kuaizhizao.services.warehouse_service.reuse_or_begin_transaction",
                _noop_tx,
            ),
            patch(
                "apps.kuaizhizao.models.packing_binding.PackingBinding.filter",
                return_value=binding_qs,
            ),
            patch(
                "apps.kuaizhizao.services.warehouse_service._load_materials_by_ids",
                new=AsyncMock(return_value={}),
            ),
        ],
    )


@pytest.mark.asyncio
async def test_semi_finished_withdraw_without_location_does_not_touch_other_bins():
    mat_qs = MagicMock()
    mat_qs.all = AsyncMock(return_value=[])
    await _withdraw_blank_location_receipt(
        SemiFinishedGoodsReceiptService,
        "withdraw_receipt_confirmation",
        "apps.kuaizhizao.models.semi_finished_goods_receipt_item.SemiFinishedGoodsReceiptItem",
        "apps.kuaizhizao.models.semi_finished_goods_receipt.SemiFinishedGoodsReceipt",
        [
            patch(
                "apps.kuaizhizao.services.semi_finished_goods_receipt_service.reuse_or_begin_transaction",
                _noop_tx,
            ),
            patch("apps.master_data.models.material.Material.filter", return_value=mat_qs),
        ],
    )


class _ItemQuery:
    def order_by(self, *_args):
        return self

    async def all(self):
        return [
            SimpleNamespace(
                id=1,
                total_amount=Decimal("113"),
                receipt_quantity=Decimal("1"),
                unit_price=Decimal("100"),
            )
        ]


@pytest.mark.asyncio
async def test_reconfirm_after_occupancy_cleared_is_not_short():
    svc = PurchaseReceiptLineFinanceOccupancyService()
    with patch(
        "apps.kuaizhizao.models.purchase_receipt_item.PurchaseReceiptItem.filter",
        return_value=_ItemQuery(),
    ):
        svc._sum_occupied_by_item = AsyncMock(return_value={1: Decimal("113.00")})
        with pytest.raises(BusinessLogicError, match="可分摊"):
            await svc._fifo_slices(
                1,
                2,
                Decimal("113"),
                "payable",
                line_amount_caps={1: Decimal("113.00")},
            )
        svc._sum_occupied_by_item = AsyncMock(return_value={})
        slices = await svc._fifo_slices(
            1,
            2,
            Decimal("113"),
            "payable",
            line_amount_caps={1: Decimal("113.00")},
        )
    assert slices[0][2] == Decimal("113.00")


@pytest.mark.asyncio
async def test_purchase_receipt_withdraw_clears_occupancy_before_stock_reversal():
    receipt = SimpleNamespace(
        id=2,
        status="已入库",
        receipt_code="PR1",
        order_type="标准采购",
        warehouse_id=3,
    )
    item = SimpleNamespace(
        id=7,
        material_id=10,
        receipt_quantity=Decimal("1"),
        material_unit="个",
        batch_number=None,
        serial_numbers=None,
        location_code="A-01",
        location_id=1,
        warehouse_id=3,
        aux_quantity=None,
        unit_conversion_rate=None,
    )
    order = []
    item_qs = MagicMock()
    item_qs.all = AsyncMock(return_value=[item])
    item_qs.update = AsyncMock()
    header_qs = MagicMock()
    header_qs.update = AsyncMock()

    async def _clear(*_args, **_kwargs):
        order.append("occupancy")

    async def _cleanup(*_args, **_kwargs):
        order.append("payable")

    async def _decrease(*_args, **_kwargs):
        order.append("stock")

    svc = PurchaseReceiptService()
    svc.get_user_info = AsyncMock(return_value={"name": "tester"})
    svc.get_purchase_receipt_by_id = AsyncMock(return_value=receipt)
    with patch(
        "apps.kuaizhizao.utils.stock_posting.reuse_or_begin_transaction", _noop_tx
    ), patch(
        "apps.kuaizhizao.utils.stock_posting._lock", new=AsyncMock()
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.in_transaction", _noop_tx
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.PurchaseReceipt.get_or_none",
        new=AsyncMock(return_value=receipt),
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.PurchaseReceipt.get",
        new=AsyncMock(return_value=receipt),
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.PurchaseReceipt.filter",
        return_value=header_qs,
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.PurchaseReceiptItem.filter",
        return_value=item_qs,
    ), patch(
        "apps.kuaicaiwu.services.purchase_receipt_line_finance_occupancy_service.PurchaseReceiptLineFinanceOccupancyService.soft_delete_by_receipt",
        new=_clear,
    ), patch(
        "apps.kuaicaiwu.services.finance_integration_hooks.cleanup_payables_for_purchase_receipt",
        new=_cleanup,
    ), patch(
        "apps.kuaizhizao.services.warehouse_service._load_materials_by_ids",
        new=AsyncMock(return_value={}),
    ), patch(
        "apps.kuaizhizao.services.warehouse_service._resolve_purchase_receipt_line_warehouse_id_for_stock",
        new=AsyncMock(return_value=3),
    ), patch(
        "apps.kuaizhizao.services.inventory_service.InventoryService._decrease_stock_no_atomic",
        new=_decrease,
    ), patch(
        "apps.kuaizhizao.services.receipt_notice_service.sync_receipt_notice_status_from_purchase_receipt",
        new=AsyncMock(),
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.sync_purchase_orders_after_receipt",
        new=AsyncMock(),
    ):
        await svc.withdraw_receipt_confirmation(1, 2, 7)
    assert order == ["occupancy", "payable", "stock"]
