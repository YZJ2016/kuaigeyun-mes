"""AR/AP 列表「未付/未收」分段须排除现金退款执行态。"""

from apps.kuaicaiwu.services.finance_list_core import (
    FINANCE_CASH_REFUND_EXECUTION_STATUSES,
    FINANCE_UNPAID_COLLECTION_STATUS_LABELS,
    apply_finance_ar_ap_collection_status_filter,
)
from apps.kuaicaiwu.services.finance_refund_utils import (
    REFUND_STATUS_FULL,
    REFUND_STATUS_NONE,
    REFUND_STATUS_PARTIAL,
)


class _FakeQuery:
    def __init__(self):
        self.filters = []
        self.excludes = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def exclude(self, **kwargs):
        self.excludes.append(kwargs)
        return self


def test_unpaid_status_excludes_cash_refund_execution():
    q = _FakeQuery()
    apply_finance_ar_ap_collection_status_filter(q, "未付款")
    assert q.filters == [{"status": "未付款"}]
    assert q.excludes == [
        {"refund_execution_status__in": list(FINANCE_CASH_REFUND_EXECUTION_STATUSES)}
    ]


def test_unreceived_status_excludes_cash_refund_execution():
    q = _FakeQuery()
    apply_finance_ar_ap_collection_status_filter(q, "未收款")
    assert q.filters == [{"status": "未收款"}]
    assert len(q.excludes) == 1


def test_partial_paid_status_does_not_exclude_refund_execution():
    q = _FakeQuery()
    apply_finance_ar_ap_collection_status_filter(q, "部分付款")
    assert q.filters == [{"status": "部分付款"}]
    assert q.excludes == []


def test_empty_status_leaves_query_unchanged():
    q = _FakeQuery()
    result = apply_finance_ar_ap_collection_status_filter(q, None)
    assert result is q
    assert q.filters == []
    assert q.excludes == []


def test_unpaid_labels_and_refund_statuses_aligned():
    assert "未付款" in FINANCE_UNPAID_COLLECTION_STATUS_LABELS
    assert REFUND_STATUS_PARTIAL in FINANCE_CASH_REFUND_EXECUTION_STATUSES
    assert REFUND_STATUS_FULL in FINANCE_CASH_REFUND_EXECUTION_STATUSES
    assert REFUND_STATUS_NONE not in FINANCE_CASH_REFUND_EXECUTION_STATUSES
