from decimal import Decimal

import pytest

from apps.kuaicaiwu.services.partner_statement_service import (
    PartnerStatementService,
    parse_statement_amount_basis,
)
from infra.exceptions.exceptions import ValidationError


def test_line_amount_inputs_from_stored_lines_uses_statement_amount():
    svc = PartnerStatementService()
    lines = [
        {
            "doc_type": "采购入库",
            "doc_id": 10,
            "doc_code": "RK001",
            "statement_amount": 1200,
            "debit": 1000,
            "tree_level": 0,
        },
        {
            "doc_type": "付款单",
            "doc_id": 11,
            "doc_code": "FK001",
            "debit": 0,
            "credit": 500,
            "tree_level": 0,
        },
        {
            "doc_type": "付款单",
            "doc_id": 12,
            "doc_code": "sub",
            "credit": 100,
            "tree_level": 1,
        },
    ]
    inputs = svc._line_amount_inputs_from_stored_lines(lines)
    assert len(inputs) == 2
    assert inputs[0]["doc_type"] == "采购入库"
    assert inputs[0]["statement_amount"] == 1200.0
    assert inputs[1]["statement_amount"] == 500.0


def test_parse_statement_amount_basis_rejects_invalid():
    with pytest.raises(ValidationError):
        parse_statement_amount_basis("unknown")


@pytest.mark.asyncio
async def test_update_statement_header_rejects_by_invoice_for_non_statement_partner(monkeypatch):
    svc = PartnerStatementService()
    from apps.kuaicaiwu.models.partner_statement import PartnerStatement

    class FakeStmt:
        tenant_id = 1
        status = "Draft"
        review_status = "草稿"
        partner_id = 1
        partner_type = "Supplier"
        ledger_posting_mode = "immediate"
        transaction_details = {}

    async def fake_get(*_args, **_kwargs):
        return FakeStmt()

    async def fake_uses(*_args, **_kwargs):
        return False

    monkeypatch.setattr(svc, "get_statement", fake_get)
    monkeypatch.setattr(svc, "_partner_uses_statement_ledger", fake_uses)

    with pytest.raises(ValidationError) as exc:
        await svc.update_statement_header(
            1, 99, ledger_posting_mode="by_invoice", user_id=1
        )
    assert "立即立账" in str(exc.value)