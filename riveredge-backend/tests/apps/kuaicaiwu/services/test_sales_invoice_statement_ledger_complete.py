"""销项发票审核后补跑对账单「根据发票立账」。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.kuaicaiwu.services.partner_statement_service import PartnerStatementService


@pytest.mark.asyncio
async def test_try_complete_ledger_after_sales_invoice_approved_calls_post_ledger(monkeypatch):
    svc = PartnerStatementService()
    post_ledger = AsyncMock()
    monkeypatch.setattr(svc, "post_ledger", post_ledger)

    invoice = SimpleNamespace(
        id=9,
        partner_id=100,
        review_status="已审核",
    )

    async def _get_invoice(**_kwargs):
        return invoice

    rel = SimpleNamespace(source_type="sales_delivery", source_id=501)

    class _RelManager:
        def filter(self, **_kwargs):
            return self

        async def all(self):
            return [rel]

    stmt = SimpleNamespace(
        id=77,
        review_status="已审核",
        status="Confirmed",
        ledger_posted_at=None,
        transaction_details={
            "lines": [{"doc_type": "销售出库", "doc_id": 501, "statement_amount": 100}]
        },
    )

    class _StmtManager:
        def filter(self, **_kwargs):
            return self

        async def all(self):
            return [stmt]

    monkeypatch.setattr(
        "apps.kuaicaiwu.models.invoice.Invoice.get_or_none",
        _get_invoice,
    )
    monkeypatch.setattr(
        "apps.kuaizhizao.models.document_relation.DocumentRelation",
        MagicMock(filter=lambda **_k: _RelManager()),
    )
    monkeypatch.setattr(
        "apps.kuaicaiwu.services.partner_statement_service.PartnerStatement",
        MagicMock(filter=lambda **_k: _StmtManager()),
    )

    await svc.try_complete_ledger_after_sales_invoice_approved(
        tenant_id=1,
        invoice_id=9,
        operator_id=2,
    )
    post_ledger.assert_awaited_once_with(1, 77, 2)