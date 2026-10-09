import pytest

from apps.kuaioa.utils.form_request_material_issue import (
    material_issue_has_countersign_targets,
    user_is_material_issue_countersign_participant,
    validate_material_issue_on_submit,
)
from infra.exceptions.exceptions import BusinessLogicError


def test_material_issue_countersign_targets():
    assert not material_issue_has_countersign_targets({})
    assert material_issue_has_countersign_targets({"countersign_user_ids": [2]})


def test_validate_material_issue_requires_content_and_countersign():
    base = {
        "issue_purpose": "试产补料",
        "issue_lines": "物料A × 10",
    }
    validate_material_issue_on_submit({**base, "countersign_user_ids": [10]})

    with pytest.raises(BusinessLogicError):
        validate_material_issue_on_submit(base)

    with pytest.raises(BusinessLogicError):
        validate_material_issue_on_submit({"countersign_user_ids": [1], "issue_purpose": "x"})


def test_user_is_material_issue_countersign_participant():
    fd = {"countersign_user_ids": [5]}
    assert user_is_material_issue_countersign_participant(fd, user_id=5)
    assert not user_is_material_issue_countersign_participant(fd, user_id=1)
