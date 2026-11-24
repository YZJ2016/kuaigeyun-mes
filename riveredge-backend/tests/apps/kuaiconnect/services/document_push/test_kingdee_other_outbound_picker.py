"""其他出库推送：领用人按单据 picker/deliverer 工号覆盖连接器默认。"""

from types import SimpleNamespace

import pytest

from apps.kuaiconnect.services.document_push.kingdee_other_outbound_push_service import (
    enrich_other_outbound_pick_header_config,
)


@pytest.mark.asyncio
async def test_enrich_other_outbound_header_uses_picker_employee_over_default(monkeypatch):
    async def fake_resolve(tenant_id, user_id, *, explicit=None):
        assert tenant_id == 2
        assert user_id == 55
        return "ID-000055"

    monkeypatch.setattr(
        "apps.kuaizhizao.utils.kingdee_warehouse_operator_utils.resolve_document_operator_number",
        fake_resolve,
    )
    outbound = SimpleNamespace(
        picker_id=55,
        deliverer_id=None,
        picker_operator_number=None,
        pick_department_code="BM-09",
        customer_number=None,
    )
    cfg = {"pickeroperator_operatornumber": "ID-DEFAULT", "bizuser_number": "ID-DEFAULT"}
    out = await enrich_other_outbound_pick_header_config(2, outbound, 1, cfg)
    assert out["pickeroperator_operatornumber"] == "ID-000055"
    assert out["bizuser_number"] == "ID-000055"


@pytest.mark.asyncio
async def test_enrich_other_outbound_uses_doc_picker_operator_snapshot(monkeypatch):
    async def fake_resolve(tenant_id, user_id, *, explicit=None):
        raise AssertionError("should not resolve when snapshot present")

    monkeypatch.setattr(
        "apps.kuaizhizao.utils.kingdee_warehouse_operator_utils.resolve_document_operator_number",
        fake_resolve,
    )
    outbound = SimpleNamespace(
        picker_id=55,
        deliverer_id=None,
        picker_operator_number="ID-SNAPSHOT",
        pick_department_code=None,
        customer_number=None,
    )
    out = await enrich_other_outbound_pick_header_config(2, outbound, 1, {})
    assert out["pickeroperator_operatornumber"] == "ID-SNAPSHOT"