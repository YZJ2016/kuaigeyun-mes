from core.services.integration.kingdee_cosmic_paths import (
    collapse_material_rows_to_unique_units,
)


def test_collapse_keeps_galaxy_bd_unit_rows():
    rows = [
        {"FUNITID": 1, "FNumber": "kg", "FName": "千克"},
        {"FUNITID": 2, "FNumber": "pcs", "FName": "个"},
        {"FUNITID": 3, "FNumber": "kg", "FName": "千克"},
    ]
    out = collapse_material_rows_to_unique_units(rows)
    assert len(out) == 3
    assert out[0]["FNumber"] == "kg"
    assert out[1]["FName"] == "个"


def test_collapse_material_baseunit_rows():
    rows = [
        {"number": "M1", "baseunit_number": "kg", "baseunit_name": "千克"},
        {"number": "M2", "baseunit_number": "kg", "baseunit_name": "千克"},
        {"number": "M3", "baseunit_number": "pcs", "baseunit_name": "个"},
    ]
    out = collapse_material_rows_to_unique_units(rows)
    assert [r["code"] for r in out] == ["kg", "pcs"]
    assert out[0]["name"] == "千克"


def test_collapse_does_not_use_material_number_as_unit_when_baseunit_present():
    rows = [
        {"number": "MAT-001", "baseunit_number": "kg", "baseunit_name": "千克"},
        {"number": "MAT-002"},  # 缺基础单位，不得冒充单位
    ]
    out = collapse_material_rows_to_unique_units(rows)
    assert [r["code"] for r in out] == ["kg"]
