"""单据行规格/型号解析（行快照 + 物料主数据）。"""

from __future__ import annotations

from types import SimpleNamespace

from apps.kuaizhizao.utils.document_line_material_snapshot import (
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