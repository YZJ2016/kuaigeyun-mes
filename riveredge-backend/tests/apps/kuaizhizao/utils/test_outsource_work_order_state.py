"""委外工单状态流转单元测试。"""

from datetime import datetime
from decimal import Decimal

from apps.kuaizhizao.services.document_action_policy.outsource_work_order import (
    derive_outsource_work_order_capabilities,
)
from apps.kuaizhizao.utils.outsource_work_order_state import (
    apply_outsource_work_order_execution_start,
    apply_outsource_work_order_receipt_completion,
    apply_outsource_work_order_receipt_reopen,
    outsource_work_order_has_execution_activity,
    resolve_outsource_work_order_product_unit,
    resolve_outsource_work_order_received_delta,
)


class _Owo:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_execution_start_from_released():
    owo = _Owo(status="released", actual_start_date=None)
    changed = apply_outsource_work_order_execution_start(owo, now=datetime(2026, 7, 10, 9, 0, 0))
    assert changed is True
    assert owo.status == "in_progress"
    assert owo.actual_start_date == datetime(2026, 7, 10, 9, 0, 0)


def test_resolve_received_delta_qualified_only():
    assert resolve_outsource_work_order_received_delta(Decimal("2.2")) == Decimal("2.2")
    assert resolve_outsource_work_order_received_delta(0) == Decimal("0")
    assert resolve_outsource_work_order_received_delta(None) == Decimal("0")


def test_receipt_completion_when_fully_received():
    owo = _Owo(status="in_progress", quantity=Decimal("100"), received_quantity=Decimal("100"))
    changed = apply_outsource_work_order_receipt_completion(owo, now=datetime(2026, 7, 31, 18, 0, 0))
    assert changed is True
    assert owo.status == "completed"
    assert owo.actual_end_date == datetime(2026, 7, 31, 18, 0, 0)


def test_receipt_reopen_after_product_return():
    owo = _Owo(
        status="completed",
        quantity=Decimal("100"),
        received_quantity=Decimal("80"),
        actual_end_date=datetime(2026, 7, 31, 18, 0, 0),
    )
    changed = apply_outsource_work_order_receipt_reopen(owo)
    assert changed is True
    assert owo.status == "in_progress"
    assert owo.actual_end_date is None


def test_receipt_reopen_skipped_when_still_full():
    owo = _Owo(status="completed", quantity=Decimal("100"), received_quantity=Decimal("100"))
    assert apply_outsource_work_order_receipt_reopen(owo) is False
    assert owo.status == "completed"


def test_completed_allows_product_return_not_receipt():
    caps = derive_outsource_work_order_capabilities(
        _Owo(
            status="completed",
            issued_quantity=10,
            received_quantity=100,
            quantity=100,
            is_frozen=False,
        )
    )
    assert caps.push_outsource_product_return.allowed is True
    assert caps.push_outsource_material_return.allowed is True
    assert caps.push_outsource_receipt.allowed is False
    assert caps.push_outsource_issue.allowed is False


def test_reopened_in_progress_allows_receipt_again():
    owo = _Owo(
        status="completed",
        quantity=Decimal("100"),
        received_quantity=Decimal("70"),
        issued_quantity=Decimal("10"),
        is_frozen=False,
    )
    apply_outsource_work_order_receipt_reopen(owo)
    caps = derive_outsource_work_order_capabilities(owo)
    assert owo.status == "in_progress"
    assert caps.push_outsource_receipt.allowed is True
    assert caps.push_outsource_issue.allowed is True


def test_has_execution_activity():
    assert outsource_work_order_has_execution_activity(_Owo(issued_quantity=0, received_quantity=0)) is False
    assert outsource_work_order_has_execution_activity(_Owo(issued_quantity=1, received_quantity=0)) is True


def test_cancel_capability_draft_and_released():
    draft_caps = derive_outsource_work_order_capabilities(_Owo(status="draft"))
    assert draft_caps.cancel.allowed is True

    released_caps = derive_outsource_work_order_capabilities(
        _Owo(status="released", issued_quantity=0, received_quantity=0, quantity=100)
    )
    assert released_caps.cancel.allowed is True
    assert released_caps.close.allowed is False


def test_close_capability_in_progress():
    caps = derive_outsource_work_order_capabilities(
        _Owo(status="in_progress", issued_quantity=10, received_quantity=50, quantity=100)
    )
    assert caps.cancel.allowed is False
    assert caps.close.allowed is True
    assert caps.push_outsource_receipt.allowed is True


def test_resolve_product_unit_default_without_product_id():
    import asyncio

    async def _run():
        return await resolve_outsource_work_order_product_unit(1, _Owo())

    assert asyncio.run(_run()) == "件"
