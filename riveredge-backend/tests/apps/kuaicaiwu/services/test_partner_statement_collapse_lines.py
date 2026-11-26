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