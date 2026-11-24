"""采购申请行建议供应商：物料默认回落与批量名称富化。"""

from types import SimpleNamespace

from apps.kuaizhizao.services.purchase_requisition_service import (
    PurchaseRequisitionService,
    _resolve_requisition_line_supplier_id,
)


def test_resolve_requisition_line_supplier_id_prefers_explicit():
    material = SimpleNamespace(source_config={"default_supplier_id": 99})
    assert _resolve_requisition_line_supplier_id(12, material) == 12
    assert _resolve_requisition_line_supplier_id(None, material) == 99


def test_resolve_requisition_line_supplier_id_from_material_helper():
    material = SimpleNamespace(
        source_config={"default_supplier_id": 0},
        defaults=None,
    )
    assert _resolve_requisition_line_supplier_id(None, material) is None


def test_attach_supplier_names_to_item_dicts():
    svc = PurchaseRequisitionService()
    rows = [{"supplier_id": 3}, {"supplier_id": None}, {"supplier_id": 9}]
    svc._attach_supplier_names_to_item_dicts(rows, {3: "供应商甲", 9: "供应商乙"})
    assert rows[0]["supplier_name"] == "供应商甲"
    assert rows[1].get("supplier_name") is None
    assert rows[2]["supplier_name"] == "供应商乙"