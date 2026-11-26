import pytest

from apps.kuaicaiwu.config.finance_settlement_contract import (
    PARTNER_STATEMENT_LINE_KIND_MATERIAL,
)
from apps.kuaicaiwu.services.partner_statement_line_service import (
    PartnerStatementLineService,
)


class _ExpandStubStatementSvc:
    call_count = 0

    async def get_statement_line_detail(self, tenant_id, doc_type, doc_id):
        type(self).call_count += 1
        return {
            "items": [
                {"id": 850, "source_line_id": 850, "material_code": "M1", "amount": 100},
                {"id": 851, "source_line_id": 851, "material_code": "M2", "amount": 50},
            ]
        }


@pytest.mark.asyncio
async def test_expand_skips_already_materialized_lines():
    """预览已是物料行时不得按单据头再次展开，否则会重复 source_line_id。"""
    _ExpandStubStatementSvc.call_count = 0
    svc = PartnerStatementLineService()
    stub = _ExpandStubStatementSvc()
    already = {
        "line_kind": PARTNER_STATEMENT_LINE_KIND_MATERIAL,
        "doc_type": "采购入库",
        "doc_id": 652,
        "source_doc_type": "purchase_receipt",
        "source_doc_id": 652,
        "source_line_id": 850,
        "statement_amount": 80,
    }
    out = await svc.expand_preview_lines_to_material_lines(1, [already], stub)
    assert len(out) == 1
    assert out[0]["source_line_id"] == 850
    assert _ExpandStubStatementSvc.call_count == 0


@pytest.mark.asyncio
async def test_expand_document_header_still_loads_detail():
    _ExpandStubStatementSvc.call_count = 0
    svc = PartnerStatementLineService()
    stub = _ExpandStubStatementSvc()
    header = {
        "doc_type": "采购入库",
        "doc_id": 652,
        "statement_amount": 150,
        "doc_amount": 150,
    }
    out = await svc.expand_preview_lines_to_material_lines(1, [header], stub)
    assert len(out) == 2
    assert {r["source_line_id"] for r in out} == {850, 851}
    assert _ExpandStubStatementSvc.call_count == 1