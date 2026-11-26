"""单据行规格/型号解析（行快照 + 物料主数据）。"""

from __future__ import annotations

from types import SimpleNamespace

from apps.kuaizhizao.utils.document_line_material_snapshot import (
    apply_snapshot_to_line_dict,
    LineMaterialSnapshot,
    resolved_line_material_model,
    resolved_line_material_spec,
)


def test_resolved_line_material_spec_prefers_line_snapshot():
    line = SimpleNamespace(material_spec="行规格 A", material_id=1)
    mat = SimpleNamespace(specification="主数据规格")
    assert resolved_line_material_spec(line, mat) == "行规格 A"


def test_resolved_line_material_spec_fills_from_material_master():
    line = SimpleNamespace(material_spec=None, material_id=1)
    mat = SimpleNamespace(specification="主数据规格")
    assert resolved_line_material_spec(line, mat) == "主数据规格"


def test_resolved_line_material_model_fills_from_material_master():
    line = SimpleNamespace(material_model="", material_id=1)
    mat = SimpleNamespace(model="M-100")
    assert resolved_line_material_model(line, mat) == "M-100"


def test_apply_snapshot_overwrites_hand_edited_spec_and_model():
    line = {"material_spec": "手改 M8*150", "material_model": "手改型号"}
    snap = LineMaterialSnapshot(None, None, "MDL-1", "主数据规格")
    apply_snapshot_to_line_dict(line, snap)
    assert line["material_spec"] == "主数据规格"
    assert line["material_model"] == "MDL-1"