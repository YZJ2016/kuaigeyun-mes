"""研发交付物命名校验。"""

import pytest

from apps.kuaiplm.utils.rd_deliverable_naming import validate_deliverable_catalog
from infra.exceptions.exceptions import ValidationError


def test_test_report_requires_material_code():
    with pytest.raises(ValidationError, match="关联料号"):
        validate_deliverable_catalog(
            deliverable_type="test_report",
            material_code=None,
            legacy_material_code=None,
            file_name="report.pdf",
        )


def test_test_report_accepts_legacy_material_code():
    validate_deliverable_catalog(
        deliverable_type="test_report",
        material_code="MAT-001",
        legacy_material_code="MAT-OLD",
        file_name="report.pdf",
    )


def test_part_spec_filename_must_include_material_code():
    with pytest.raises(ValidationError, match="料号"):
        validate_deliverable_catalog(
            deliverable_type="part_spec",
            material_code="MAT-001",
            legacy_material_code=None,
            file_name="wrong_name.pdf",
        )


def test_drawing_requires_version_suffix():
    with pytest.raises(ValidationError, match="版本后缀"):
        validate_deliverable_catalog(
            deliverable_type="drawing_3d",
            material_code=None,
            legacy_material_code=None,
            file_name="model.stp",
        )


def test_software_spec_requires_project_version_date():
    with pytest.raises(ValidationError, match="项目号_版本号_更新日期"):
        validate_deliverable_catalog(
            deliverable_type="software_spec",
            material_code=None,
            legacy_material_code=None,
            file_name="RD001_A1.pdf",
            project_code="RD001",
        )


def test_software_spec_accepts_project_version_date():
    validate_deliverable_catalog(
        deliverable_type="software_spec",
        material_code=None,
        legacy_material_code=None,
        file_name="RD001_A1_20260926.pdf",
        project_code="RD001",
    )


def test_software_spec_rejects_wrong_project_prefix():
    with pytest.raises(ValidationError, match="项目代号"):
        validate_deliverable_catalog(
            deliverable_type="software_spec",
            material_code=None,
            legacy_material_code=None,
            file_name="OTHER_A1_20260926.pdf",
            project_code="RD001",
        )


def test_schematic_requires_pcb_code():
    with pytest.raises(ValidationError, match="PCB料号"):
        validate_deliverable_catalog(
            deliverable_type="schematic",
            material_code=None,
            legacy_material_code=None,
            file_name="PCB001_A1_20260926.pdf",
        )


def test_gerber_requires_pcb_version_date():
    with pytest.raises(ValidationError, match="PCB料号_版本号_更新日期"):
        validate_deliverable_catalog(
            deliverable_type="gerber",
            material_code="PCB001",
            legacy_material_code=None,
            file_name="PCB001_A1.zip",
        )


def test_layout_accepts_pcb_version_date():
    validate_deliverable_catalog(
        deliverable_type="layout",
        material_code="PCB001",
        legacy_material_code=None,
        file_name="PCB001_A1_20260926.brd",
    )


def test_panelization_accepts_pcb_version_date():
    validate_deliverable_catalog(
        deliverable_type="panelization",
        material_code="PCB001",
        legacy_material_code=None,
        file_name="PCB001_R02_2026-09-26.pdf",
    )
