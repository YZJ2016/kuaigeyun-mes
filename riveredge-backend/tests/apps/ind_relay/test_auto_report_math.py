"""自动报工增量与分摊单元测试。"""

from decimal import Decimal

from apps.ind_relay.services.auto_report_math import allocate_increment, compute_zscl_increment


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
