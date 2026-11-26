"""物料分组按编码智能归类父级。"""

from apps.kuaiconnect.services.inbound_sync.material_group_sync_service import (
    apply_infer_parent_by_code,
    infer_material_group_parent_code,
    material_group_code_depth,
)


def test_infer_parent_code_dot_segments():
    assert infer_material_group_parent_code("06") is None
    assert infer_material_group_parent_code("06.01") == "06"
    assert infer_material_group_parent_code("06.01.02") == "06.01"
    assert infer_material_group_parent_code("06-01") == "06"
    assert infer_material_group_parent_code("06/01/02") == "06/01"


def test_code_depth():
    assert material_group_code_depth("06") == 1
    assert material_group_code_depth("06.01") == 2
    assert material_group_code_depth("06.01.02") == 3


def test_apply_infer_expands_ancestors_and_sorts():
    pending = [
        ("06.01.02", "三级", None, {"name": "三级"}),
        ("06.02", "二级乙", None, {"name": "二级乙"}),
    ]
    out = apply_infer_parent_by_code(pending)
    codes = [item[0] for item in out]
    assert codes == ["06", "06.01", "06.02", "06.01.02"]
    by_code = {item[0]: item for item in out}
    assert by_code["06"][2] is None
    assert by_code["06.01"][2] == "06"
    assert by_code["06.02"][2] == "06"
    assert by_code["06.01.02"][2] == "06.01"
    # 占位祖先名称用编码
    assert by_code["06"][1] == "06"
    assert by_code["06.01"][1] == "06.01"
