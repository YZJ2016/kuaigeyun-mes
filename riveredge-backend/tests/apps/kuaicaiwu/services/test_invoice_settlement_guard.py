import pytest

from apps.kuaicaiwu.services.invoice_settlement_guard import (
    assert_detail_invoice_lines_strict_1_1,
    assert_settlement_mode_items_consistency,
)
from infra.exceptions.exceptions import ValidationError


def test_detail_invoice_requires_source_line_id():
    with pytest.raises(ValidationError):
        assert_detail_invoice_lines_strict_1_1([{"amount": 1}])


def test_detail_invoice_rejects_duplicate_source_line():
    rows = [
        {
            "source_doc_type": "purchase_receipt",
            "source_doc_id": 1,
            "source_line_id": 10,
            "amount": 1,
        },
        {
            "source_doc_type": "purchase_receipt",
            "source_doc_id": 1,
            "source_line_id": 10,
            "amount": 2,
        },
    ]
    with pytest.raises(ValidationError):
        assert_detail_invoice_lines_strict_1_1(rows)


def test_summary_rejects_line_source():
    with pytest.raises(ValidationError):
        assert_settlement_mode_items_consistency(
            "summary",
            [{"source_line_id": 1}],
        )


def test_detail_invoice_rejects_non_positive_source_ids_and_blank_type():
    for bad_row in (
        {"source_doc_type": "", "source_doc_id": 1, "source_line_id": 10},
        {"source_doc_type": "purchase_receipt", "source_doc_id": 0, "source_line_id": 10},
        {"source_doc_type": "purchase_receipt", "source_doc_id": 1, "source_line_id": -5},
    ):
        with pytest.raises(ValidationError):
            assert_detail_invoice_lines_strict_1_1([bad_row])
