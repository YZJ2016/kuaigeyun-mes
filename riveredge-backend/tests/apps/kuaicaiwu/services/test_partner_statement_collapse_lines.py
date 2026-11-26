from apps.kuaicaiwu.config.finance_settlement_contract import (
    PARTNER_STATEMENT_LINE_KIND_MATERIAL,
)
from apps.kuaicaiwu.services.partner_statement_service import (
    collapse_material_lines_to_document_lines,
)


def test_collapse_material_lines_merges_same_receipt():
  material = [
    {
      "line_kind": PARTNER_STATEMENT_LINE_KIND_MATERIAL,
      "doc_type": "采购入库",
      "doc_id": 652,
      "doc_code": "CGSD652",
      "statement_amount": 7079.6,
      "debit": 7079.6,
      "credit": 0,
      "prior_stated_amount": 0,
      "remaining_amount": 7079.6,
      "inbound_detail_doc_type": "purchase_receipt",
      "inbound_detail_doc_id": 652,
      "material_code": "00000001",
    },
    {
      "line_kind": PARTNER_STATEMENT_LINE_KIND_MATERIAL,
      "doc_type": "采购入库",
      "doc_id": 652,
      "doc_code": "CGSD652",
      "statement_amount": 8849.6,
      "debit": 8849.6,
      "credit": 0,
      "prior_stated_amount": 0,
      "remaining_amount": 8849.6,
      "inbound_detail_doc_type": "purchase_receipt",
      "inbound_detail_doc_id": 652,
      "material_code": "00000002",
    },
  ]
  merged = collapse_material_lines_to_document_lines(material)
  assert len(merged) == 1
  assert merged[0]["doc_id"] == 652
  assert float(merged[0]["statement_amount"]) == 15929.2


def test_collapse_material_lines_sums_doc_amount_and_preserves_order():
  lines = [
    {
      "line_kind": "document",
      "doc_type": "期初调整",
      "doc_id": 1,
      "doc_code": "ADJ1",
      "doc_amount": 100,
      "statement_amount": 100,
    },
    {
      "line_kind": PARTNER_STATEMENT_LINE_KIND_MATERIAL,
      "doc_type": "采购入库",
      "doc_id": 652,
      "doc_code": "CGSD652",
      "doc_amount": 300,
      "statement_amount": 300,
      "debit": 300,
      "credit": 0,
    },
    {
      "line_kind": "document",
      "doc_type": "应付单",
      "doc_id": 2,
      "doc_code": "AP2",
      "doc_amount": 50,
      "statement_amount": 50,
    },
    {
      "line_kind": PARTNER_STATEMENT_LINE_KIND_MATERIAL,
      "doc_type": "采购入库",
      "doc_id": 652,
      "doc_code": "CGSD652",
      "doc_amount": 200,
      "statement_amount": 200,
      "debit": 200,
      "credit": 0,
    },
  ]
  merged = collapse_material_lines_to_document_lines(lines)
  assert [m["doc_code"] for m in merged] == ["ADJ1", "CGSD652", "AP2"]
  assert float(merged[1]["doc_amount"]) == 500.0
  assert float(merged[1]["statement_amount"]) == 500.0
