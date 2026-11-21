from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.kuaizhizao.services import finance_settlement_source_query as source_module
from apps.kuaizhizao.services.finance_settlement_source_query import (
    FinanceSettlementSourceQuery,
)


class _QueryRows:
    def __init__(self, rows):
        self.rows = rows

    def exclude(self, **_kwargs):
        return self

    def order_by(self, *_args):
        return self

    async def all(self):
        return self.rows


@pytest.mark.asyncio
async def test_monthly_customer_includes_completed_delivery_with_old_header_strategy(monkeypatch):
    delivery = SimpleNamespace(
        id=17,
        delivery_code="XSFH-17",
        delivery_time=datetime(2026, 11, 17, 8, tzinfo=timezone.utc),
        review_time=None,
        total_amount=Decimal("100.00"),
        revenue_recognition="on_shipment",
    )
    monkeypatch.setattr(
        source_module.SalesDelivery,
        "filter",
        lambda **_kwargs: _QueryRows([delivery]),
    )
    monkeypatch.setattr(
        source_module.SalesReturn,
        "filter",
        lambda **_kwargs: _QueryRows([]),
    )

    async def _none_posted(*_args, **_kwargs):
        return set()

    monkeypatch.setattr(source_module, "_posted_receivable_source_ids", _none_posted)
    monkeypatch.setattr(
        source_module, "partner_statement_ledger_posted_doc_ids", _none_posted
    )

    query = FinanceSettlementSourceQuery()
    strict = await query.list_customer_unposted_lines(
        1,
        2,
        date(2026, 11, 1),
        date(2026, 11, 30),
    )
    monthly_customer = await query.list_customer_unposted_lines(
        1,
        2,
        date(2026, 11, 1),
        date(2026, 11, 30),
        require_statement_strategy=False,
    )

    assert strict == []
    assert [(row["doc_type"], row["doc_id"], row["debit"]) for row in monthly_customer] == [
        ("销售出库", 17, 100.0)
    ]
