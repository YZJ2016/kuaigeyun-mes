"""往来对账单：业务确认先于审核（状态门禁单测，无库）。"""

import pytest

from apps.kuaicaiwu.services.partner_statement_service import (
    PartnerStatementService,
    _net_statement_ledger_amount,
)


class _Stmt:
    def __init__(self, status: str, review_status: str):
        self.status = status
        self.review_status = review_status


def test_statement_content_editable_draft():
    svc = PartnerStatementService()
    assert svc._statement_content_editable(_Stmt("Draft", "草稿")) is True
    assert svc._statement_content_editable(_Stmt("Draft", "待审核")) is False


def test_statement_content_editable_confirmed_rejected():
    svc = PartnerStatementService()
    assert svc._statement_content_editable(_Stmt("Confirmed", "驳回")) is True
    assert svc._statement_content_editable(_Stmt("Confirmed", "草稿")) is True
    assert svc._statement_content_editable(_Stmt("Confirmed", "已审核")) is False
    assert svc._statement_content_editable(_Stmt("Confirmed", "待审核")) is False


def test_net_statement_ledger_amount_debit_minus_credit():
    lines = [
        {"statement_amount": 100, "debit": 100, "credit": 0},
        {"statement_amount": 30, "debit": 0, "credit": 30},
    ]
    assert _net_statement_ledger_amount(lines) == 70


def test_lines_support_statement_ledger_by_doc_type():
    assert PartnerStatementService._lines_support_statement_ledger(
        [{"doc_type": "采购入库", "doc_id": 1, "tree_level": 0}]
    ) is True
    assert PartnerStatementService._lines_support_statement_ledger(
        [{"doc_type": "付款单", "doc_id": 1, "tree_level": 0}]
    ) is False
    assert PartnerStatementService._lines_support_statement_ledger(
        [{"doc_type": "采购入库", "doc_id": 1, "tree_level": 1}]
    ) is False


class _StmtLedger:
    def __init__(
        self,
        *,
        ledger_posting_mode: str = "immediate",
        ledger_posted_at=None,
        review_status: str = "已审核",
        status: str = "Confirmed",
        transaction_details=None,
        tenant_id: int = 1,
        partner_id: int = 2,
        partner_type: str = "Supplier",
    ):
        self.ledger_posting_mode = ledger_posting_mode
        self.ledger_posted_at = ledger_posted_at
        self.review_status = review_status
        self.status = status
        self.transaction_details = transaction_details or {
            "lines": [{"doc_type": "采购入库", "doc_id": 1, "tree_level": 0}],
        }
        self.tenant_id = tenant_id
        self.partner_id = partner_id
        self.partner_type = partner_type


@pytest.mark.asyncio
async def test_immediate_ledger_auto_posts_after_review_approve(monkeypatch):
    svc = PartnerStatementService()
    posted: list[int] = []

    async def fake_get(_tenant_id: int, _statement_id: int):
        return _StmtLedger()

    async def fake_supports(_obj):
        return True

    async def fake_post_ledger(tenant_id: int, statement_id: int, operator_id: int):
        posted.append(operator_id)
        return _StmtLedger(ledger_posted_at="2026-11-19T12:00:00+00:00", status="LedgerPosted")

    monkeypatch.setattr(svc, "get_statement", fake_get)
    monkeypatch.setattr(svc, "_statement_supports_ledger_modes", fake_supports)
    monkeypatch.setattr(svc, "post_ledger", fake_post_ledger)

    out = await svc._auto_post_ledger_if_immediate_after_review_approve(1, 9, 77)
    assert posted == [77]
    assert out.status == "LedgerPosted"


@pytest.mark.asyncio
async def test_finance_auto_approve_triggers_partner_statement_immediate_post(monkeypatch):
    from apps.kuaicaiwu.services.finance_audit_workflow import _auto_approve_finance

    posts: list[tuple[int, int, int]] = []

    class _Doc:
        status = "Confirmed"
        confirmed_at = object()

    class _Model:
        @staticmethod
        async def get_or_none(**_kwargs):
            return _Doc()

        @staticmethod
        def filter(**_kwargs):
            class _Q:
                async def update(self, **_patch):
                    return 1

            return _Q()

    class _UserQS:
        async def first(self):
            return None

    monkeypatch.setattr(
        "apps.kuaicaiwu.services.finance_audit_workflow.User.filter",
        lambda **_kw: _UserQS(),
    )

    async def fake_auto_post(_self, tenant_id, statement_id, operator_id):
        posts.append((tenant_id, statement_id, operator_id))

    monkeypatch.setattr(
        PartnerStatementService,
        "_auto_post_ledger_if_immediate_after_review_approve",
        fake_auto_post,
    )

    await _auto_approve_finance(
        model=_Model,
        tenant_id=1,
        doc_id=11,
        updated_by=99,
        node_key="partner_statement",
    )
    assert posts == [(1, 11, 99)]


@pytest.mark.asyncio
async def test_by_invoice_skips_auto_post_until_invoice(monkeypatch):
    svc = PartnerStatementService()
    posted: list[int] = []

    async def fake_get(_tenant_id: int, _statement_id: int):
        return _StmtLedger(ledger_posting_mode="by_invoice")

    async def fake_post_ledger(tenant_id: int, statement_id: int, operator_id: int):
        posted.append(operator_id)
        raise AssertionError("by_invoice 不得在审核通过时自动立账")

    monkeypatch.setattr(svc, "get_statement", fake_get)
    monkeypatch.setattr(svc, "post_ledger", fake_post_ledger)

    out = await svc._auto_post_ledger_if_immediate_after_review_approve(1, 9, 77)
    assert posted == []
    assert out.status == "Confirmed"
    assert out.ledger_posting_mode == "by_invoice"