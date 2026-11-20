"""对账单购销发票源解析（纯函数）。"""

from decimal import Decimal

import pytest

from apps.kuaicaiwu.services.partner_statement_invoice_pull import (
    PartnerStatementInvoiceBudget,
    apply_invoice_budget_to_pull_preview,
    scale_line_push_caps_to_header,
    extract_statement_source_doc_ids,
    invoice_source_doc_type_for_mode,
    invoice_source_type_for_mode,
    parse_partner_statement_id_csv,
    resolve_pull_preview_invoice_cap,
    resolve_statement_invoice_source_ids,
    snapshot_ids_for_api,
)


def test_parse_partner_statement_id_csv():
    assert parse_partner_statement_id_csv("11, 22,,0") == [11, 22]


def test_doc_type_by_mode_customer():
    assert invoice_source_doc_type_for_mode("Customer", "by_invoice") == "销售出库"
    assert invoice_source_doc_type_for_mode("Customer", "immediate") == "应收单"


def test_doc_type_by_mode_supplier():
    assert invoice_source_doc_type_for_mode("Supplier", "by_invoice") == "采购入库"
    assert invoice_source_doc_type_for_mode("Supplier", "immediate") == "应付单"


def test_source_type_mapping():
    assert invoice_source_type_for_mode("Customer", "by_invoice") == "sales_delivery"
    assert invoice_source_type_for_mode("Customer", "immediate") == "receivable"
    assert invoice_source_type_for_mode("Supplier", "by_invoice") == "purchase_receipt"
    assert invoice_source_type_for_mode("Supplier", "immediate") == "payable"


def test_extract_statement_lines_filters():
    details = {
        "lines": [
            {"doc_type": "采购入库", "doc_id": 10, "tree_level": 0, "debit": 100},
            {"doc_type": "采购入库", "doc_id": 10, "tree_level": 0, "debit": 50},
            {"doc_type": "采购入库", "doc_id": 11, "tree_level": 1, "debit": 99},
            {"doc_type": "应付单", "doc_id": 12, "tree_level": 0, "debit": 80},
        ]
    }
    assert extract_statement_source_doc_ids(details, "采购入库") == [10]
    assert extract_statement_source_doc_ids(details, "应付单") == [12]


def test_resolve_and_snapshot_ids_supplier_by_invoice_outsource_only():
    snap = resolve_statement_invoice_source_ids(
        partner_type="Supplier",
        ledger_posting_mode="by_invoice",
        transaction_details={
            "lines": [
                {"doc_type": "工序委外收货", "doc_id": 88, "tree_level": 0, "statement_amount": 1200},
            ]
        },
    )
    assert snap.source_type == "outsource_order_receipt"
    assert snap.outsource_order_receipt_ids == [88]
    api = snapshot_ids_for_api(snap)
    assert api["outsource_order_receipt_ids"] == [88]
    assert api["receipt_ids"] == []


def test_resolve_and_snapshot_ids_supplier_by_invoice():
    snap = resolve_statement_invoice_source_ids(
        partner_type="Supplier",
        ledger_posting_mode="by_invoice",
        transaction_details={
            "lines": [
                {"doc_type": "采购入库", "doc_id": 7, "tree_level": 0, "statement_amount": 1},
            ]
        },
    )
    assert snap.source_type == "purchase_receipt"
    assert snap.source_ids == [7]
    api = snapshot_ids_for_api(snap)
    assert api["receipt_ids"] == [7]
    assert api["payable_ids"] == []


def test_resolve_pull_preview_invoice_cap_priority():
    preview = {
        "partner_statement_invoice_budget": 2500,
        "max_push_total": 2580,
        "items": [{"max_push_quantity": 2580}],
    }
    assert resolve_pull_preview_invoice_cap(preview) == Decimal("2500")


def test_scale_line_push_caps_to_header_for_statement_invoice():
    scaled = scale_line_push_caps_to_header(
        {1: Decimal("1500"), 2: Decimal("1000")},
        Decimal("2580"),
    )
    assert sum(scaled.values()) == Decimal("2580")


def test_apply_invoice_budget_expands_preview_when_statement_cap_exceeds_items():
    preview = {
        "items": [{"max_push_quantity": 2500}],
        "detail_lines": [{"max_push_amount": 1500}, {"max_push_amount": 1000}],
        "max_push_total": 2500.0,
    }
    budget = PartnerStatementInvoiceBudget(
        period_amount=Decimal("2580"),
        source_pushable=Decimal("2580"),
        invoiced=Decimal("0"),
        invoiceable=Decimal("2580"),
    )
    apply_invoice_budget_to_pull_preview(preview, budget)
    assert preview["max_push_total"] == 2580.0
    assert preview["items"][0]["max_push_quantity"] == 2580.0
    assert preview["detail_lines"][0]["max_push_amount"] == 1548.0
    assert preview["detail_lines"][1]["max_push_amount"] == 1032.0


def test_apply_invoice_budget_scales_preview():
    preview = {
        "items": [{"max_push_quantity": 1500}, {"max_push_quantity": 1080}],
        "detail_lines": [{"max_push_amount": 1500}],
        "max_push_total": 2580.0,
    }
    budget = PartnerStatementInvoiceBudget(
        period_amount=Decimal("2580"),
        source_pushable=Decimal("2500"),
        invoiced=Decimal("0"),
        invoiceable=Decimal("2500"),
    )
    apply_invoice_budget_to_pull_preview(preview, budget)
    assert preview["max_push_total"] == 2500.0
    assert preview["partner_statement_invoice_budget"] == 2500.0
    assert resolve_pull_preview_invoice_cap(preview) == Decimal("2500")


@pytest.mark.asyncio
async def test_invoice_pull_metrics_single_caliber(monkeypatch):
    from apps.kuaicaiwu.services import partner_statement_invoice_pull as mod

    async def fake_sum_pushed(_tenant_id, _source_type, source_ids):
        return {int(source_ids[0]): Decimal("0")}

    async def fake_source_pushable(_tenant_id, _source_type, _source_ids):
        return Decimal("2500")

    monkeypatch.setattr(mod, "sum_pushed_by_source_type", fake_sum_pushed)
    monkeypatch.setattr(mod, "sum_source_invoice_pushable_remaining", fake_source_pushable)

    budget = await mod.resolve_partner_statement_invoice_budget(
        1,
        side="purchase",
        source_type="purchase_receipt",
        source_ids=[9],
        statement_period_amount=Decimal("2580"),
    )
    assert budget.invoiceable == Decimal("2580")
    assert budget.source_pushable == Decimal("2500")

    invoiced, remaining, allowed, _reason = await mod.compute_statement_invoice_pull_metrics(
        1,
        side="purchase",
        source_ids=[9],
        source_type="purchase_receipt",
        statement_period_amount=Decimal("2580"),
    )
    assert invoiced == 0
    assert remaining == 2580
    assert allowed is True


def test_resolve_immediate_receivable():
    snap = resolve_statement_invoice_source_ids(
        partner_type="Customer",
        ledger_posting_mode="immediate",
        transaction_details={
            "lines": [
                {"doc_type": "应收单", "doc_id": 3, "tree_level": 0, "debit": 2},
            ]
        },
    )
    assert snap.source_type == "receivable"
    assert snap.source_ids == [3]
    assert snapshot_ids_for_api(snap)["receivable_ids"] == [3]