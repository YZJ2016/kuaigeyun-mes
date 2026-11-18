from decimal import Decimal

from apps.kuaicaiwu.services.partner_statement_service import (
    PartnerStatementService,
    _line_doc_key,
)


def test_line_doc_key_statement_ledger_doc_types():
    assert _line_doc_key("销售出库", 101) == ("sales_delivery", 101)
    assert _line_doc_key("采购入库", 202) == ("purchase_receipt", 202)
    assert _line_doc_key("工序委外收货", 303) == ("outsource_process_receipt", 303)


def test_build_line_amount_override_map_accepts_sales_delivery():
    svc = PartnerStatementService()
    overrides = svc._build_line_amount_override_map(
        [{"doc_type": "销售出库", "doc_id": 9, "statement_amount": 3900}]
    )
    assert overrides == {("sales_delivery", 9): Decimal("3900.00")}
