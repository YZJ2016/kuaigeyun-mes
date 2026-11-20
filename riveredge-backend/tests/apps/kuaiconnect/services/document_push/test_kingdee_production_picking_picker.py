"""生产领料推送：领用人按 picker_id 解析工号（对齐其他出库）。"""

from types import SimpleNamespace

import pytest

from apps.kuaiconnect.services.document_push.kingdee_production_picking_push_service import (
    enrich_production_picking_header_config,
)


@pytest.mark.asyncio
async def test_enrich_production_picking_header_uses_picker_employee_over_default(monkeypatch):
    async def fake_resolve(tenant_id, user_id, *, explicit=None):
        assert tenant_id == 2
        assert user_id == 43
        return "ID-000042"

    monkeypatch.setattr(
        "apps.kuaizhizao.utils.kingdee_warehouse_operator_utils.resolve_document_operator_number",
        fake_resolve,
    )
    picking = SimpleNamespace(picker_id=43, pick_department_code="BM-00001")
    cfg = {
        "pickeroperator_operatornumber": "ID-000081",
        "bizuser_number": "ID-000081",
    }
    out = await enrich_production_picking_header_config(2, picking, 1, cfg)
    assert out["pickeroperator_operatornumber"] == "ID-000042"
    assert out["picker_number"] == "ID-000042"
    assert out["bizuser_number"] == "ID-000042"
    assert out["pickdept_number"] == "BM-00001"


@pytest.mark.asyncio
async def test_enrich_production_picking_header_keeps_default_without_picker(monkeypatch):
    async def fake_resolve(tenant_id, user_id, *, explicit=None):
        assert user_id is None
        return None

    monkeypatch.setattr(
        "apps.kuaizhizao.utils.kingdee_warehouse_operator_utils.resolve_document_operator_number",
        fake_resolve,
    )
    picking = SimpleNamespace(picker_id=None, pick_department_code=None)
    cfg = {"pickeroperator_operatornumber": "ID-000081"}
    out = await enrich_production_picking_header_config(2, picking, 1, cfg)
    assert out["pickeroperator_operatornumber"] == "ID-000081"