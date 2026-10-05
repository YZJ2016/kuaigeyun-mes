"""自动报工增量与分摊单元测试。"""

from decimal import Decimal

from apps.ind_relay.services.auto_report_math import (
    allocate_increment,
    compute_zscl_increment,
    should_changeover,
)


class TestComputeZsclIncrement:
    def test_missing(self):
        kind, qty = compute_zscl_increment(None, Decimal("10"))
        assert kind == "missing"
        assert qty == 0

    def test_baseline(self):
        kind, qty = compute_zscl_increment(Decimal("100"), None)
        assert kind == "baseline"
        assert qty == 0

    def test_zero(self):
        kind, qty = compute_zscl_increment(Decimal("100"), Decimal("100"))
        assert kind == "zero"
        assert qty == 0

    def test_increment(self):
        kind, qty = compute_zscl_increment(Decimal("120"), Decimal("100"))
        assert kind == "increment"
        assert qty == Decimal("20")

    def test_reset(self):
        kind, qty = compute_zscl_increment(Decimal("5"), Decimal("100"))
        assert kind == "reset"
        assert qty == Decimal("5")


class TestAllocateIncrement:
    def test_fill_then_overflow_last(self):
        alloc = allocate_increment(
            Decimal("30"),
            [Decimal("10"), Decimal("10"), Decimal("5")],
            last_takes_overflow=True,
        )
        assert alloc == [Decimal("10"), Decimal("10"), Decimal("10")]

    def test_no_overflow(self):
        alloc = allocate_increment(
            Decimal("30"),
            [Decimal("10"), Decimal("10")],
            last_takes_overflow=False,
        )
        assert alloc == [Decimal("10"), Decimal("10")]

    def test_empty(self):
        assert allocate_increment(Decimal("10"), []) == []


class TestShouldChangeover:
    def test_no_bound(self):
        assert not should_changeover(
            has_bound=False,
            bound_still_candidate=False,
            bound_in_progress=False,
            bound_product_id=1,
            best_in_progress=True,
            best_wo_id=2,
            best_product_id=1,
            bound_wo_id=1,
        )

    def test_same_product_keep_bound(self):
        assert not should_changeover(
            has_bound=True,
            bound_still_candidate=True,
            bound_in_progress=True,
            bound_product_id=1,
            best_in_progress=True,
            best_wo_id=2,
            best_product_id=1,
            bound_wo_id=1,
        )

    def test_product_changed(self):
        assert should_changeover(
            has_bound=True,
            bound_still_candidate=True,
            bound_in_progress=True,
            bound_product_id=1,
            best_in_progress=True,
            best_wo_id=2,
            best_product_id=9,
            bound_wo_id=1,
        )

    def test_old_not_running_new_in_progress(self):
        assert should_changeover(
            has_bound=True,
            bound_still_candidate=True,
            bound_in_progress=False,
            bound_product_id=1,
            best_in_progress=True,
            best_wo_id=2,
            best_product_id=1,
            bound_wo_id=1,
        )

    def test_bound_gone(self):
        assert should_changeover(
            has_bound=True,
            bound_still_candidate=False,
            bound_in_progress=False,
            bound_product_id=1,
            best_in_progress=True,
            best_wo_id=2,
            best_product_id=1,
            bound_wo_id=1,
        )
