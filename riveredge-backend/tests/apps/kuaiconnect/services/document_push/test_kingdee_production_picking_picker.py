"""生产领料推送：领用人按 picker_id 解析工号（对齐其他出库）。"""

from types import SimpleNamespace

import pytest

from apps.kuaiconnect.services.document_push.kingdee_production_picking_push_service import (
    choose_production_pick_department_code,
    enrich_production_picking_header_config,
)


def test_choose_department_uses_only_synced_code_when_document_empty():
    assert choose_production_pick_department_code(None, ["Org-00024"]) == "Org-00024"


def test_choose_department_keeps_document_code_already_synced():
    assert (
        choose_production_pick_department_code("Org-00015", ["Org-00015", "Org-00024"])
        == "Org-00015"
    )


def test_choose_department_replaces_unsynced_document_when_picker_has_one():
    assert choose_production_pick_department_code("Org-00013", ["Org-00024"]) == "Org-00024"


def test_choose_department_does_not_pick_among_multiple():
    assert choose_production_pick_department_code(None, ["Org-00015", "Org-00024"]) is None


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

    async def no_synced(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "apps.kuaiconnect.services.document_push.kingdee_production_picking_push_service.resolve_synced_production_pick_department",
        no_synced,
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


@pytest.mark.asyncio
async def test_enrich_fills_empty_department_from_synced_picking(monkeypatch):
    async def fake_resolve(tenant_id, user_id, *, explicit=None):
        return "ID-000012"

    async def synced_dept(*_args, **_kwargs):
        return (8, "Org-00024", "机加及产品生产交付部-刀片")

    monkeypatch.setattr(
        "apps.kuaizhizao.utils.kingdee_warehouse_operator_utils.resolve_document_operator_number",
        fake_resolve,
    )
    monkeypatch.setattr(
        "apps.kuaiconnect.services.document_push.kingdee_production_picking_push_service.resolve_synced_production_pick_department",
        synced_dept,
    )
    picking = SimpleNamespace(id=71, picker_id=24, pick_department_code=None, workshop_id=None)
    out = await enrich_production_picking_header_config(
        2,
        picking,
        1,
        {"bizuser_number": "ID-000081", "pickeroperator_operatornumber": "ID-000081"},
    )
    assert out["bizuser_number"] == "ID-000012"
    assert out["pickdept_number"] == "Org-00024"
    assert out["bizdept_number"] == "Org-00024"