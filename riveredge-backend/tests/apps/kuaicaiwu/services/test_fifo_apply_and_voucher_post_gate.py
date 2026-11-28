"""Spec 226 守卫回归：预收 FIFO 核销幂等、赠品仓计价排除、未审核拒付负向。

本仓测试为无 DB 的 monkeypatch 单测（与 test_finance_event_no_swallow 同约定）：
用 fake ORM 接缝验证 select_for_update 查询下的逐笔 fresh-read 核销语义。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from infra.exceptions.exceptions import BusinessLogicError, ValidationError


class _AwaitableQS:
    """可 await 的 fake queryset，支持 order_by / select_for_update / all 链。"""

    def __init__(self, rows):
        self._rows = rows

    def order_by(self, *args, **kwargs):
        return self

    def select_for_update(self, *args, **kwargs):
        return self

    def all(self):
        return self

    def __await__(self):
        async def _coro():
            return self._rows

        return _coro().__await__()


def _match(row, kwargs):
    for key, expected in kwargs.items():
        if key in ("tenant_id", "deleted_at__isnull"):
            continue
        if key == "id__in":
            if getattr(row, "id") not in set(expected):
                return False
        elif key == "unsettled_amount__gt":
            if not (Decimal(str(getattr(row, "unsettled_amount"))) > Decimal(str(expected))):
                return False
        elif key.endswith("__in"):
            if getattr(row, key[: -len("__in")]) not in set(expected):
                return False
        else:
            if getattr(row, key) != expected:
                return False
    return True


# ---------------------------------------------------------------------------
# 1) 预收 FIFO 核销幂等（receivable_pull_service.apply_prepayment_to_receivable）
# ---------------------------------------------------------------------------


def _patch_fifo_orm(monkeypatch, *, relations, receipts, receivable):
    from apps.kuaicaiwu.models.receipt import Receipt
    from apps.kuaicaiwu.models.receivable import Receivable
    from apps.kuaizhizao.models.document_relation import DocumentRelation

    monkeypatch.setattr(
        DocumentRelation,
        "filter",
        lambda **kwargs: _AwaitableQS([r for r in relations if _match(r, kwargs)]),
    )
    monkeypatch.setattr(
        Receipt,
        "filter",
        lambda **kwargs: _AwaitableQS([r for r in receipts if _match(r, kwargs)]),
    )

    async def _receipt_get(**kwargs):
        rid = kwargs.get("id")
        return next((r for r in receipts if r.id == rid), None)

    async def _receivable_get(**kwargs):
        return receivable

    monkeypatch.setattr(Receipt, "get_or_none", _receipt_get)
    monkeypatch.setattr(Receivable, "get_or_none", _receivable_get)


def _fake_apply(monkeypatch, calls, receipts, receivable):
    from apps.kuaicaiwu.services.prepayment_service import PrepaymentService

    async def _apply(self, tenant_id, *, receipt_id, receivable_id, amount, operator_id):
        amt = Decimal(str(amount)).quantize(Decimal("0.01"))
        calls.append((receipt_id, amt))
        receipt = next(r for r in receipts if r.id == receipt_id)
        receipt.unsettled_amount -= amt
        receivable.remaining_amount -= amt

    monkeypatch.setattr(PrepaymentService, "apply_receipt_to_receivable", _apply)


@pytest.mark.asyncio
async def test_fifo_apply_repeated_call_does_not_over_settle(monkeypatch):
    """核销后重入：应收剩余为 0 时第二次调用应返回 0，不得重复核销。"""
    from apps.kuaicaiwu.services.receivable_pull_service import ReceivablePullService

    receipts = [
        SimpleNamespace(
            id=10,
            settlement_type="prepayment",
            status="Confirmed",
            unsettled_amount=Decimal("100.00"),
            customer_id=1,
            deleted_at=None,
        )
    ]
    receivable = SimpleNamespace(id=20, remaining_amount=Decimal("80.00"), customer_id=1)
    relations = [SimpleNamespace(source_type="sales_order", source_id=5, target_type="receipt", target_id=10)]
    calls = []

    _patch_fifo_orm(monkeypatch, relations=relations, receipts=receipts, receivable=receivable)
    _fake_apply(monkeypatch, calls, receipts, receivable)

    svc = ReceivablePullService()
    first = await svc.apply_prepayment_to_receivable(
        1, receivable_id=20, sales_order_id=5, amount=Decimal("80"), operator_id=1
    )
    assert first == Decimal("80.00")
    assert receipts[0].unsettled_amount == Decimal("20.00")
    assert receivable.remaining_amount == Decimal("0.00")
    assert calls == [(10, Decimal("80.00"))]

    second = await svc.apply_prepayment_to_receivable(
        1, receivable_id=20, sales_order_id=5, amount=Decimal("50"), operator_id=1
    )
    assert second == Decimal("0.00")
    assert calls == [(10, Decimal("80.00"))]
    assert receipts[0].unsettled_amount == Decimal("20.00")


@pytest.mark.asyncio
async def test_fifo_apply_no_candidate_raises(monkeypatch):
    """预收已全部核销（unsettled=0）时仍要求核销，应明确报错而非静默返回。"""
    from apps.kuaicaiwu.services.receivable_pull_service import ReceivablePullService

    receipts = [
        SimpleNamespace(
            id=10,
            settlement_type="prepayment",
            status="Confirmed",
            unsettled_amount=Decimal("0.00"),
            customer_id=1,
            deleted_at=None,
        )
    ]
    receivable = SimpleNamespace(id=20, remaining_amount=Decimal("50.00"), customer_id=1)
    relations = [SimpleNamespace(source_type="sales_order", source_id=5, target_type="receipt", target_id=10)]

    _patch_fifo_orm(monkeypatch, relations=relations, receipts=receipts, receivable=receivable)
    _fake_apply(monkeypatch, [], receipts, receivable)

    with pytest.raises(BusinessLogicError, match="未找到可核销预收收款单"):
        await ReceivablePullService().apply_prepayment_to_receivable(
            1, receivable_id=20, sales_order_id=5, amount=Decimal("50"), operator_id=1
        )


@pytest.mark.asyncio
async def test_fifo_apply_oldest_first(monkeypatch):
    """FIFO：按收款单 id 顺序核销，先核销最早预收。"""
    from apps.kuaicaiwu.services.receivable_pull_service import ReceivablePullService

    receipts = [
        SimpleNamespace(
            id=10,
            settlement_type="prepayment",
            status="Confirmed",
            unsettled_amount=Decimal("30.00"),
            customer_id=1,
            deleted_at=None,
        ),
        SimpleNamespace(
            id=11,
            settlement_type="prepayment",
            status="Confirmed",
            unsettled_amount=Decimal("70.00"),
            customer_id=1,
            deleted_at=None,
        ),
    ]
    receivable = SimpleNamespace(id=20, remaining_amount=Decimal("50.00"), customer_id=1)
    relations = [SimpleNamespace(source_type="sales_order", source_id=5, target_type="receipt", target_id=10), SimpleNamespace(source_type="sales_order", source_id=5, target_type="receipt", target_id=11)]
    calls = []

    _patch_fifo_orm(monkeypatch, relations=relations, receipts=receipts, receivable=receivable)
    _fake_apply(monkeypatch, calls, receipts, receivable)

    applied = await ReceivablePullService().apply_prepayment_to_receivable(
        1, receivable_id=20, sales_order_id=5, amount=Decimal("50"), operator_id=1
    )
    assert applied == Decimal("50.00")
    assert calls == [(10, Decimal("30.00")), (11, Decimal("20.00"))]
    assert receipts[0].unsettled_amount == Decimal("0.00")
    assert receipts[1].unsettled_amount == Decimal("50.00")


# ---------------------------------------------------------------------------
# 2) 赠品仓（只计数量仓）计价排除
# ---------------------------------------------------------------------------


class _WarehouseQS:
    def __init__(self, rows):
        self._rows = rows

    async def exists(self):
        return bool(self._rows)

    def exclude(self, **kwargs):
        return _WarehouseQS([w for w in self._rows if not _match(w, kwargs)])

    def values_list(self, field, flat=False):
        return _AwaitableQS([getattr(w, field) for w in self._rows])


@pytest.mark.asyncio
async def test_costing_warehouse_ids_none_when_no_gift_warehouse(monkeypatch):
    from apps.kuaicaiwu.services.inventory_cost_service import InventoryCostService
    from apps.master_data.models.warehouse import Warehouse

    warehouses = [
        SimpleNamespace(id=1, warehouse_type="normal", deleted_at=None),
        SimpleNamespace(id=2, warehouse_type="finished", deleted_at=None),
    ]
    monkeypatch.setattr(
        Warehouse,
        "filter",
        lambda **kwargs: _WarehouseQS([w for w in warehouses if _match(w, kwargs)]),
    )

    result = await InventoryCostService().resolve_costing_warehouse_ids(1)
    assert result is None


@pytest.mark.asyncio
async def test_costing_warehouse_ids_excludes_gift_warehouse(monkeypatch):
    from apps.kuaicaiwu.services.inventory_cost_service import InventoryCostService
    from apps.master_data.models.warehouse import Warehouse

    warehouses = [
        SimpleNamespace(id=1, warehouse_type="normal", deleted_at=None),
        SimpleNamespace(id=9, warehouse_type="gift", deleted_at=None),
        SimpleNamespace(id=3, warehouse_type="finished", deleted_at=None),
    ]
    monkeypatch.setattr(
        Warehouse,
        "filter",
        lambda **kwargs: _WarehouseQS([w for w in warehouses if _match(w, kwargs)]),
    )

    result = await InventoryCostService().resolve_costing_warehouse_ids(1)
    assert result == [1, 3]


# ---------------------------------------------------------------------------
# 3) 未审核拒付（FinanceVoucherPostingService.post_receipt / post_payment）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("review_status", ["待审核", "SUBMITTED", "草稿"])
async def test_post_receipt_rejects_unapproved_draft(monkeypatch, review_status):
    from apps.kuaicaiwu.models.receipt import Receipt
    from apps.kuaicaiwu.services.finance_voucher_posting_service import (
        FinanceVoucherPostingService,
    )

    fake = SimpleNamespace(
        id=1, status="Draft", review_status=review_status, settlement_type="normal"
    )

    async def _get(**kwargs):
        return fake

    monkeypatch.setattr(Receipt, "get_or_none", _get)

    with pytest.raises(ValidationError, match="收款单尚未审核通过"):
        await FinanceVoucherPostingService().post_receipt(1, 1, operator_id=1)


@pytest.mark.asyncio
async def test_post_receipt_rejects_posted_status(monkeypatch):
    from apps.kuaicaiwu.models.receipt import Receipt
    from apps.kuaicaiwu.services.finance_voucher_posting_service import (
        FinanceVoucherPostingService,
    )

    fake = SimpleNamespace(id=1, status="Posted", review_status="已审核")

    async def _get(**kwargs):
        return fake

    monkeypatch.setattr(Receipt, "get_or_none", _get)

    with pytest.raises(ValidationError, match="只有草稿或待补流水"):
        await FinanceVoucherPostingService().post_receipt(1, 1, operator_id=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("review_status", ["待审核", "SUBMITTED"])
async def test_post_payment_rejects_unapproved_draft(monkeypatch, review_status):
    from apps.kuaicaiwu.models.payment import Payment
    from apps.kuaicaiwu.services.finance_voucher_posting_service import (
        FinanceVoucherPostingService,
    )

    fake = SimpleNamespace(
        id=1, status="Draft", review_status=review_status, settlement_type="normal"
    )

    async def _get(**kwargs):
        return fake

    monkeypatch.setattr(Payment, "get_or_none", _get)

    with pytest.raises(ValidationError, match="付款单尚未审核通过"):
        await FinanceVoucherPostingService().post_payment(1, 1, operator_id=1)


@pytest.mark.asyncio
async def test_post_payment_refund_rejection_uses_refund_wording(monkeypatch):
    from apps.kuaicaiwu.models.payment import Payment
    from apps.kuaicaiwu.services.finance_voucher_posting_service import (
        FinanceVoucherPostingService,
    )

    fake = SimpleNamespace(
        id=1, status="Draft", review_status="待审核", settlement_type="refund"
    )

    async def _get(**kwargs):
        return fake

    monkeypatch.setattr(Payment, "get_or_none", _get)

    with pytest.raises(ValidationError, match="付款退款尚未审核通过，不能确认退款"):
        await FinanceVoucherPostingService().post_payment(1, 1, operator_id=1)
