"""对账单购销发票源解析（纯函数）。"""

from apps.kuaicaiwu.services.partner_statement_invoice_pull import (
    extract_statement_source_doc_ids,
    invoice_source_doc_type_for_mode,
    invoice_source_type_for_mode,
    resolve_statement_invoice_source_ids,
    snapshot_ids_for_api,
)


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