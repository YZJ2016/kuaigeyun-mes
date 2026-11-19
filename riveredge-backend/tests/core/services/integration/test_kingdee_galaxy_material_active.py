from core.services.integration.kingdee_cosmic_material_active import (
    filter_cosmic_material_rows_active,
)
from core.services.integration.kingdee_galaxy_material_active import (
    filter_galaxy_material_rows_active,
    is_galaxy_execute_bill_query_path,
    is_galaxy_material_row_active,
)


def test_is_galaxy_material_row_active():
    assert is_galaxy_material_row_active(
        {"FNumber": "A", "FDocumentStatus": "C", "FForbidStatus": "A"}
    )
    assert not is_galaxy_material_row_active(
        {"FNumber": "B", "FDocumentStatus": "A", "FForbidStatus": "A"}
    )
    assert not is_galaxy_material_row_active(
        {"FNumber": "C", "FDocumentStatus": "C", "FForbidStatus": "B"}
    )
    # FilterString 已收窄、行上无状态字段时仍视为有效
    assert is_galaxy_material_row_active({"FNumber": "D", "FName": "物料"})


def test_filter_galaxy_material_rows_active():
    rows = [
        {"FNumber": "A", "FDocumentStatus": "C", "FForbidStatus": "A"},
        {"FNumber": "B", "FDocumentStatus": "A", "FForbidStatus": "A"},
        {"FNumber": "C", "FDocumentStatus": "C", "FForbidStatus": "B"},
    ]
    kept = filter_galaxy_material_rows_active(rows)
    assert [r["FNumber"] for r in kept] == ["A"]


def test_cosmic_active_filter_must_not_keep_galaxy_rows():
    """回归：对星空行误套苍穹 status/enable 过滤会得到 0 行。"""
    galaxy_rows = [
        {"FNumber": "A", "FName": "物料A", "FDocumentStatus": "C", "FForbidStatus": "A"},
        {"FNumber": "B", "FName": "物料B", "FDocumentStatus": "C", "FForbidStatus": "A"},
    ]
    assert len(filter_cosmic_material_rows_active(galaxy_rows)) == 0
    assert len(filter_galaxy_material_rows_active(galaxy_rows)) == 2


def test_is_galaxy_execute_bill_query_path():
    assert is_galaxy_execute_bill_query_path(
        "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc"
    )
    assert not is_galaxy_execute_bill_query_path("kapi/v2/basedata/bd_material/batchQuery")
