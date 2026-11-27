"""上游同步深度审查已定缺陷的聚焦单测。不连库。"""

from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaicaiwu.services.purchase_receipt_line_finance_occupancy_service import (
    PurchaseReceiptLineFinanceOccupancyService,
    record_purchase_receipt_payable_occupancy,
)
from apps.kuaicaiwu.services.return_open_balance_offset_service import (
    purchase_return_amount_from_receipt_line,
)
from apps.kuaizhizao.services.finance_settlement_source_query import (
    FinanceSettlementSourceQuery,
    _PURCHASE_RETURN_POSTED_STATUSES,
    _SALES_RETURN_POSTED_STATUSES,
)
from apps.kuaizhizao.services.inventory_service import (
    InventoryService,
    split_manual_aux_deduct_share,
)
from apps.kuaizhizao.services.purchase_service import PurchaseService
from apps.kuaizhizao.services.warehouse_service import (
    SalesDeliveryService,
    sales_delivery_confirm_blocked_by_review,
)
from infra.exceptions.exceptions import BusinessLogicError


def test_sales_delivery_confirm_review_gate():
    assert sales_delivery_confirm_blocked_by_review(
        audit_required=False, review_status="待审核"
    ) is False
    assert sales_delivery_confirm_blocked_by_review(
        audit_required=True, review_status="待审核"
    ) is True
    assert sales_delivery_confirm_blocked_by_review(
        audit_required=True, review_status="已通过"
    ) is False


def test_manual_aux_split_uses_proportion_and_last_remainder():
    first, remaining = split_manual_aux_deduct_share(
        Decimal("10"),
        Decimal("5"),
        Decimal("4"),
        Decimal("5"),
        finishes_quantity=False,
    )
    last, leftover = split_manual_aux_deduct_share(
        Decimal("10"),
        Decimal("5"),
        Decimal("6"),
        remaining,
        finishes_quantity=True,
    )
    assert first == Decimal("2")
    assert last == Decimal("3")
    assert leftover == Decimal("0")


def test_explicit_zero_tax_keeps_inclusive_line_untaxed_equal_gross():
    item = SimpleNamespace(
        total_price=None,
        tax_rate=0,
        display_unit_price=Decimal("113"),
        unit_price=Decimal("113"),
    )
    excl = PurchaseService._po_line_excl_total_from_form_item(
        qty=Decimal("1"),
        item_data=item,
        order_price_type="tax_inclusive",
        header_tax_rate=Decimal("0.13"),
        price_decimal_places=4,
        amount_decimal_places=2,
    )
    assert excl == Decimal("113.00")


def test_purchase_return_amount_is_receipt_gross_share():
    receipt = SimpleNamespace(tax_rate=Decimal("0.13"))
    line = SimpleNamespace(
        receipt_quantity=Decimal("10"),
        unit_price=Decimal("100"),
        display_unit_price=Decimal("113"),
        tax_rate=Decimal("13"),
        purchase_order_item_id=None,
    )
    full = purchase_return_amount_from_receipt_line(receipt, line, {}, Decimal("10"))
    part = purchase_return_amount_from_receipt_line(receipt, line, {}, Decimal("4"))
    assert full == Decimal("1130.00")
    assert part == Decimal("452.00")
    assert -full < 0


def test_unposted_return_statuses_are_not_posted():
    assert "待退货" not in _PURCHASE_RETURN_POSTED_STATUSES
    assert "待退货" not in _SALES_RETURN_POSTED_STATUSES
    assert "已退货" in _PURCHASE_RETURN_POSTED_STATUSES
    assert "已退货" in _SALES_RETURN_POSTED_STATUSES


def test_location_scoped_when_line_has_location_code():
    item = SimpleNamespace(location_code="A-01", location_id=None)
    assert InventoryService.line_item_location_scoped(item) is True
    assert InventoryService.location_kwargs_from_line_item(item) == {"location_code": "A-01"}
    blank = SimpleNamespace(location_code="", location_id=None)
    assert InventoryService.line_item_location_scoped(blank) is False
    assert InventoryService.location_kwargs_from_line_item(blank) == {}


@asynccontextmanager
async def _noop_tx(*_args, **_kwargs):
    conn = MagicMock()
    conn.execute_query = AsyncMock(return_value=None)
    yield conn


@pytest.mark.asyncio
async def test_unapproved_sales_delivery_cannot_confirm():
    delivery = SimpleNamespace(
        status="待出库",
        review_status="待审核",
        sales_order_id=None,
        customer_id=1,
        customer_name="客户",
        total_amount=Decimal("1"),
        items=[],
    )
    svc = SalesDeliveryService()
    svc.get_sales_delivery_by_id = AsyncMock(return_value=delivery)
    svc.business_config_service.check_audit_required = AsyncMock(return_value=True)
    with patch(
        "apps.kuaizhizao.services.document_action_policy.warehouse_outbound_hub.assert_outbound_hub_capability"
    ):
        with pytest.raises(BusinessLogicError, match="尚未审核通过"):
            await svc.confirm_delivery(1, 2, 3)


@pytest.mark.asyncio
async def test_sales_delivery_withdraw_uses_line_warehouse_location_and_aux():
    delivery = SimpleNamespace(
        id=2,
        status="已出库",
        warehouse_id=3,
        delivery_code="SD1",
        delivery_time=None,
        sales_order_id=None,
        save=AsyncMock(),
    )
    item = SimpleNamespace(
        id=9,
        material_id=10,
        delivery_quantity=Decimal("2"),
        material_unit="个",
        warehouse_id=15,
        location_id=8,
        location_code="A-01",
        batch_number="B1",
        serial_numbers=None,
        aux_quantity=Decimal("1.5"),
        unit_conversion_rate=None,
        status="已出库",
        delivery_time=None,
        save=AsyncMock(),
    )
    material = SimpleNamespace(id=10, base_unit="个", batch_managed=False, serial_managed=False, name="M")
    item_qs = MagicMock()
    item_qs.all = AsyncMock(return_value=[item])
    mat_qs = MagicMock()
    mat_qs.all = AsyncMock(return_value=[material])
    notice_qs = MagicMock()
    notice_qs.exclude.return_value = notice_qs
    notice_qs.exists = AsyncMock(return_value=False)
    return_qs = MagicMock()
    return_qs.exclude.return_value = return_qs
    return_qs.exists = AsyncMock(return_value=False)
    increase = AsyncMock(return_value=True)
    svc = SalesDeliveryService()
    svc.get_user_info = AsyncMock(return_value={"name": "tester"})
    with patch(
        "apps.kuaizhizao.utils.stock_posting.reuse_or_begin_transaction", _noop_tx
    ), patch(
        "apps.kuaizhizao.utils.stock_posting._lock", new=AsyncMock()
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.in_transaction", _noop_tx
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.SalesDelivery.get_or_none",
        new=AsyncMock(return_value=delivery),
    ), patch(
        "apps.kuaizhizao.services.document_action_policy.warehouse_outbound_hub.assert_outbound_hub_capability"
    ), patch(
        "apps.kuaizhizao.models.delivery_notice.DeliveryNotice.filter",
        return_value=notice_qs,
    ), patch(
        "apps.kuaizhizao.models.sales_return.SalesReturn.filter",
        return_value=return_qs,
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.SalesDeliveryItem.filter",
        return_value=item_qs,
    ), patch(
        "apps.master_data.models.material.Material.filter",
        return_value=mat_qs,
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.BusinessConfigService"
    ) as cfg_cls, patch(
        "apps.kuaizhizao.utils.ledger_dual_quantity_utils.material_ledger_uses_manual_aux_quantity",
        return_value=True,
    ), patch(
        "apps.kuaizhizao.services.inventory_service.InventoryService.increase_stock",
        increase,
    ), patch(
        "apps.kuaizhizao.services.warehouse_service.SalesDeliveryResponse.model_validate",
        return_value=delivery,
    ), patch(
        "apps.kuaiconnect.services.document_push.kingdee_im_warehouse_revoke_service"
        ".sync_im_warehouse_kingdee_after_withdraw",
        new=AsyncMock(return_value=None),
    ):
        cfg_cls.return_value.get_business_config = AsyncMock(
            return_value={"parameters": {"warehouse": {}}}
        )
        await svc.withdraw_delivery_confirmation(1, 2, 7)

    kwargs = increase.await_args.kwargs
    assert kwargs["warehouse_id"] == 15
    assert kwargs["location_code"] == "A-01"
    assert kwargs["location_id"] == 8
    assert kwargs["aux_quantity_delta"] == Decimal("1.5")


@pytest.mark.asyncio
async def test_sales_order_open_lines_set_aux_and_notes():
    order = SimpleNamespace(
        id=1,
        order_code="SO1",
        order_date=date(2026, 1, 2),
        status="已审核",
        customer_id=3,
        customer_name="客户",
        customer_contact=None,
        customer_phone=None,
        price_type="tax_exclusive",
        currency_code="CNY",
        exchange_rate=Decimal("1"),
        revenue_recognition=None,
        shipping_address=None,
        shipping_method=None,
    )
    item = SimpleNamespace(
        id=10,
        material_id=20,
        sales_order_id=1,
        order_quantity=Decimal("5"),
        material_code="M1",
        material_name="物料",
        material_spec="",
        material_unit="个",
        unit_price=Decimal("10"),
        tax_rate=Decimal("0"),
        is_gift=False,
        delivery_date=None,
        notes="行备注",
        aux_quantity=Decimal("2"),
        aux_unit="箱",
    )
    so_qs = MagicMock()
    so_qs.filter.return_value = so_qs
    so_qs.only = AsyncMock(return_value=[order])
    item_qs = MagicMock()
    item_qs.all = AsyncMock(return_value=[item])
    with patch(
        "apps.kuaizhizao.models.sales_order.SalesOrder.filter", return_value=so_qs
    ), patch(
        "apps.kuaizhizao.utils.pull_query_date_filter.apply_pull_query_document_date_filter",
        side_effect=lambda query, **_k: query,
    ), patch(
        "apps.kuaizhizao.models.sales_order_item.SalesOrderItem.filter",
        return_value=item_qs,
    ), patch(
        "apps.kuaizhizao.utils.sales_order_push_qty.batch_pushable_qty_by_order_item",
        new=AsyncMock(return_value={1: {10: Decimal("5")}}),
    ), patch(
        "apps.kuaizhizao.utils.sales_order_push_qty.batch_pushable_aux_qty_by_order_item",
        new=AsyncMock(return_value={1: {10: Decimal("1.5")}}),
    ), patch(
        "apps.kuaizhizao.services.sales_order_service.SalesOrderService"
    ) as so_svc:
        so_svc.return_value._is_audited.return_value = True
        result = await SalesDeliveryService().list_sales_order_delivery_pull_lines(1)

    assert result["total"] == 1
    row = result["data"][0]
    assert row["line_notes"] == "行备注"
    assert row["remaining_aux_quantity"] == 1.5


@pytest.mark.asyncio
async def test_payable_occupancy_uses_settlement_gross_caps(monkeypatch):
    captured = {}

    async def fake_caps(_tenant_id, _receipt_id):
        return {7: Decimal("113.00")}

    async def fake_record(self, tenant_id, receipt_id, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        "apps.kuaicaiwu.services.purchase_receipt_line_finance_occupancy_service._line_gross_caps_for_receipt",
        fake_caps,
    )
    monkeypatch.setattr(
        PurchaseReceiptLineFinanceOccupancyService,
        "record_receipt_finance_occupancy",
        fake_record,
    )
    await record_purchase_receipt_payable_occupancy(
        1, 2, 3, Decimal("113.00"), settlement_gross=True
    )
    assert captured["line_amount_caps"][7] == Decimal("113.00")


@pytest.mark.asyncio
async def test_fifo_occupancy_untaxed_cap_rejects_gross_amount(monkeypatch):
    item = SimpleNamespace(
        id=1,
        total_amount=Decimal("100"),
        receipt_quantity=Decimal("1"),
        unit_price=Decimal("100"),
    )

    class _QS:
        def select_for_update(self):
            return self

        def order_by(self, *_args):
            return self

        async def all(self):
            return [item]

    monkeypatch.setattr(
        "apps.kuaizhizao.models.purchase_receipt_item.PurchaseReceiptItem.filter",
        lambda **_kwargs: _QS(),
    )
    svc = PurchaseReceiptLineFinanceOccupancyService()
    monkeypatch.setattr(svc, "_sum_occupied_by_item", AsyncMock(return_value={}))
    with pytest.raises(BusinessLogicError, match="可分摊"):
        await svc._fifo_slices(1, 2, Decimal("113"), "payable")
    slices = await svc._fifo_slices(
        1, 2, Decimal("113"), "payable", line_amount_caps={1: Decimal("113")}
    )
    assert slices[0][2] == Decimal("113.00")


class _EmptyQuery:
    def exclude(self, **_kwargs):
        return self

    def order_by(self, *_args):
        return self

    async def all(self):
        return []


@pytest.mark.asyncio
async def test_monthly_recon_collects_only_posted_returns(monkeypatch):
    captured = {}

    def return_filter(**kwargs):
        captured.update(kwargs)
        return _EmptyQuery()

    monkeypatch.setattr(
        "apps.kuaizhizao.services.finance_settlement_source_query.PurchaseReceipt.filter",
        lambda **_kwargs: _EmptyQuery(),
    )
    monkeypatch.setattr(
        "apps.kuaizhizao.services.finance_settlement_source_query.PurchaseReturn.filter",
        return_filter,
    )
    monkeypatch.setattr(
        "apps.kuaizhizao.services.finance_settlement_source_query._posted_payable_source_ids",
        AsyncMock(return_value=set()),
    )
    monkeypatch.setattr(
        "apps.kuaizhizao.services.finance_settlement_source_query.partner_statement_ledger_posted_doc_ids",
        AsyncMock(return_value=set()),
    )
    monkeypatch.setattr(
        FinanceSettlementSourceQuery,
        "list_outsource_supplier_unposted_lines",
        AsyncMock(return_value=[]),
    )
    lines = await FinanceSettlementSourceQuery().list_supplier_unposted_lines(
        1, 2, date(2026, 1, 1), date(2026, 1, 31)
    )
    assert lines == []
    assert "已退货" in captured["status__in"]
    assert "待退货" not in captured["status__in"]
