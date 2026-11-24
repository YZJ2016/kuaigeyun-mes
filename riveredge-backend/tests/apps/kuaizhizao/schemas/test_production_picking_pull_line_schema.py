"""生产领料工单取单行 schema 契约。"""

from apps.kuaizhizao.schemas.warehouse import ProductionPickingPullLineCreate


def test_pull_line_create_accepts_location_fields():
    line = ProductionPickingPullLineCreate(
        material_id=1,
        material_code="M001",
        material_name="测试物料",
        material_unit="个",
        issue_quantity=2,
        warehouse_id=10,
        warehouse_name="原料仓",
        location_id=99,
        location_code="A-01",
    )
    assert line.location_id == 99
    assert line.location_code == "A-01"