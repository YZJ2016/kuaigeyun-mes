"""采购预付批量补齐：失败留在采购订单上，标记写失败上抛，已成功的不回滚。"""

from __future__ import annotations

from decimal import Decimal

import pytest


class _Tx:
    def __init__(self, events: list):
        self.events = events

    async def __aenter__(self):
        self.events.append("tx-begin")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.events.append("tx-rollback" if exc_type else "tx-commit")
        return False


class _Order:
    def __init__(self, order_id: int, status: str, *, amount: str = "10", mark: str | None = None):
        self.id = order_id
        self.tenant_id = 1
        self.status = status
        self.prepayment_amount = Decimal(amount)
        self.prepayment_bank_account_id = None
        self.order_code = f"PO-{order_id}"
        self.supplier_id = 9
        self.supplier_name = "供应商"
        self.prepayment_backfill_status = mark
        self.save_error: Exception | None = None
        self.events: list = []

    async def save(self, update_fields=None):
        self.events.append(("save", self.id, self.prepayment_backfill_status, update_fields))
        if self.save_error:
            raise self.save_error


class _QS:
    def __init__(self, rows):
        self.rows = rows

    async def all(self):
        return self.rows


def _patch_backfill(monkeypatch, orders, *, linked_ids=None, ensure_impl=None):
    from apps.kuaicaiwu.services import finance_integration_hooks as hooks
    from apps.kuaizhizao.models.purchase_order import PurchaseOrder

    linked = set(linked_ids or [])
    events: list = []

    monkeypatch.setattr(PurchaseOrder, "filter", lambda *a, **k: _QS(orders))

    async def _relation(tenant_id, source_type, source_id, target_type):
        events.append(("relation", source_id))
        return source_id in linked

    async def _ensure(**kwargs):
        events.append(("ensure", kwargs["order_id"]))
        if ensure_impl:
            return await ensure_impl(kwargs)
        return 1000 + int(kwargs["order_id"])

    monkeypatch.setattr(hooks, "_existing_order_prepayment_relation", _relation)
    monkeypatch.setattr(hooks, "ensure_prepayment_payment_for_purchase_order", _ensure)
    monkeypatch.setattr(
        "tortoise.transactions.in_transaction", lambda *a, **k: _Tx(events)
    )
    for order in orders:
        order.events = events
    return events


@pytest.mark.asyncio
async def test_generation_failure_leaves_missing_and_prior_order_stays_backfilled(monkeypatch):
    from apps.kuaicaiwu.services.finance_integration_hooks import (
        backfill_missing_purchase_order_prepayments,
    )

    draft = _Order(1, "DRAFT")
    done = _Order(2, "CONFIRMED")
    failed = _Order(3, "CONFIRMED")

    async def _ensure(kwargs):
        if kwargs["order_id"] == 3:
            raise RuntimeError("payment create failed")
        return 22

    events = _patch_backfill(monkeypatch, [draft, done, failed], ensure_impl=_ensure)

    created = await backfill_missing_purchase_order_prepayments(1, operator_id=7)

    assert created == 1
    assert draft.prepayment_backfill_status is None
    assert ("save", 1, None, None) not in events
    assert done.prepayment_backfill_status == "backfilled"
    assert failed.prepayment_backfill_status == "missing"
    assert ("ensure", 3) in events
    assert events.index(("save", 2, "backfilled", ["prepayment_backfill_status", "updated_at"])) < events.index(
        ("ensure", 3)
    )
    assert "tx-commit" in events


@pytest.mark.asyncio
async def test_existing_relation_marks_backfilled_without_generate(monkeypatch):
    from apps.kuaicaiwu.services.finance_integration_hooks import (
        backfill_missing_purchase_order_prepayments,
    )

    linked = _Order(5, "CONFIRMED")
    events = _patch_backfill(monkeypatch, [linked], linked_ids={5})

    created = await backfill_missing_purchase_order_prepayments(1, operator_id=7)

    assert created == 0
    assert linked.prepayment_backfill_status == "backfilled"
    assert not any(item[0] == "ensure" for item in events)


@pytest.mark.asyncio
async def test_mark_write_failure_propagates_and_skips_later_orders(monkeypatch):
    from apps.kuaicaiwu.services.finance_integration_hooks import (
        backfill_missing_purchase_order_prepayments,
    )

    earlier = _Order(8, "CONFIRMED")
    broken = _Order(9, "CONFIRMED")
    later = _Order(10, "CONFIRMED")
    broken.save_error = RuntimeError("mark write failed")

    async def _ensure(kwargs):
        if kwargs["order_id"] == 9:
            raise RuntimeError("payment create failed")
        return 80 + int(kwargs["order_id"])

    events = _patch_backfill(
        monkeypatch, [earlier, broken, later], ensure_impl=_ensure
    )

    with pytest.raises(RuntimeError, match="mark write failed"):
        await backfill_missing_purchase_order_prepayments(1, operator_id=7)

    assert earlier.prepayment_backfill_status == "backfilled"
    assert ("ensure", 10) not in events
    assert any(item == ("save", 8, "backfilled", ["prepayment_backfill_status", "updated_at"]) for item in events)
    assert "tx-rollback" in events


@pytest.mark.asyncio
async def test_later_generation_failure_does_not_rollback_committed_mark(monkeypatch):
    from apps.kuaicaiwu.services.finance_integration_hooks import (
        backfill_missing_purchase_order_prepayments,
    )

    first = _Order(11, "CONFIRMED")
    second = _Order(12, "CONFIRMED")

    async def _ensure(kwargs):
        if kwargs["order_id"] == 12:
            raise RuntimeError("payment create failed")
        return 111

    events = _patch_backfill(monkeypatch, [first, second], ensure_impl=_ensure)

    await backfill_missing_purchase_order_prepayments(1, operator_id=7)

    assert first.prepayment_backfill_status == "backfilled"
    assert second.prepayment_backfill_status == "missing"
    first_save = events.index(("save", 11, "backfilled", ["prepayment_backfill_status", "updated_at"]))
    second_save = events.index(("save", 12, "missing", ["prepayment_backfill_status", "updated_at"]))
    assert first_save < second_save
    assert events[first_save + 1] == "tx-commit"


@pytest.mark.asyncio
async def test_unchanged_mark_skips_save_but_status_change_still_commits(monkeypatch):
    from apps.kuaicaiwu.services.finance_integration_hooks import (
        backfill_missing_purchase_order_prepayments,
    )

    already_backfilled = _Order(21, "CONFIRMED", mark="backfilled")
    still_missing = _Order(22, "CONFIRMED", mark="missing")
    newly_linked = _Order(23, "CONFIRMED", mark="missing")

    async def _ensure(kwargs):
        if kwargs["order_id"] == 22:
            raise RuntimeError("payment create failed")
        return 200

    events = _patch_backfill(
        monkeypatch,
        [already_backfilled, still_missing, newly_linked],
        linked_ids={21, 23},
        ensure_impl=_ensure,
    )

    created = await backfill_missing_purchase_order_prepayments(1, operator_id=7)

    assert created == 0
    assert already_backfilled.prepayment_backfill_status == "backfilled"
    assert still_missing.prepayment_backfill_status == "missing"
    assert newly_linked.prepayment_backfill_status == "backfilled"
    assert ("ensure", 21) not in events
    assert ("ensure", 22) in events
    assert ("ensure", 23) not in events
    assert not any(
        isinstance(item, tuple) and item[0] == "save" and item[1] in (21, 22) for item in events
    )
    save = ("save", 23, "backfilled", ["prepayment_backfill_status", "updated_at"])
    save_at = events.index(save)
    assert events[save_at - 1] == "tx-begin"
    assert events[save_at + 1] == "tx-commit"
    assert events.count("tx-begin") == 1
    assert events.count("tx-commit") == 1
