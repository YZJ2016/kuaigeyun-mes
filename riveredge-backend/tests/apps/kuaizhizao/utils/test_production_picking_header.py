import pytest

from apps.kuaizhizao.utils.production_picking_header import (
    assert_production_picking_picker_and_department,
)
from infra.exceptions.exceptions import ValidationError


def test_assert_production_picking_header_requires_picker():
    with pytest.raises(ValidationError, match="领用人"):
        assert_production_picking_picker_and_department(
            picker_id=None,
            pick_department_id=1,
            pick_department_code="Org-001",
        )


def test_assert_production_picking_header_requires_department():
    with pytest.raises(ValidationError, match="领用部门"):
        assert_production_picking_picker_and_department(
            picker_id=10,
            pick_department_id=None,
            pick_department_code="",
        )


def test_assert_production_picking_header_accepts_code_without_id():
    assert_production_picking_picker_and_department(
        picker_id=10,
        pick_department_id=None,
        pick_department_code="Org-00024",
    )