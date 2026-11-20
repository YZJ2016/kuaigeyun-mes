from datetime import date

import pytest

from apps.kuaicaiwu.services.partner_statement_service import PartnerStatementService


class _FakeSettlementQuery:
    async def list_supplier_unposted_lines(self, *args, **kwargs):
        return [
            {
                "date": "2026-11-19",
                "sort_date": date(2026, 11, 19),
                "doc_type": "采购入库",
                "doc_code": "RK001",
                "debit": 100.0,
                "credit": 0.0,
                "doc_id": 1,
                "doc_amount": 100.0,
            }
        ]


@pytest.mark.asyncio
async def test_statement_ledger_period_lines_exclude_payment_docs(monkeypatch):
    svc = PartnerStatementService()
    payment_queries = []
    payable_queries = []

    def payment_filter_spy(*args, **kwargs):
        payment_queries.append(1)

        class _Q:
            def order_by(self, *_a, **_k):
                return self

            async def all(self):
                return []

        return _Q()

    def payable_filter_spy(*args, **kwargs):
        payable_queries.append(1)

        class _Q:
            def exclude(self, *_a, **_k):
                return self

            def order_by(self, *_a, **_k):
                return self

            async def all(self):
                return []

        return _Q()

    async def noop_attach(_tenant_id, _lines):
        return None

    async def partner_not_statement(*_a, **_k):
        return False

    monkeypatch.setattr(
        "apps.kuaizhizao.services.finance_settlement_source_query.FinanceSettlementSourceQuery",
        _FakeSettlementQuery,
    )
    monkeypatch.setattr(svc, "_attach_purchase_receipt_amount_parts", noop_attach)
    monkeypatch.setattr(svc, "_partner_uses_statement_ledger", partner_not_statement)
    monkeypatch.setattr(
        "apps.kuaicaiwu.services.partner_statement_service.Payment.filter",
        payment_filter_spy,
    )
    monkeypatch.setattr(
        "apps.kuaicaiwu.services.partner_statement_service.Payable.filter",
        payable_filter_spy,
    )

    lines = await svc._collect_period_raw_lines(
        1, 2, "Supplier", date(2026, 11, 19), date(2026, 11, 19)
    )
    assert payment_queries == []
    assert payable_queries == []
    assert all(ln.get("doc_type") not in ("付款单", "应付单") for ln in lines)
    assert any(ln.get("doc_type") == "采购入库" for ln in lines)