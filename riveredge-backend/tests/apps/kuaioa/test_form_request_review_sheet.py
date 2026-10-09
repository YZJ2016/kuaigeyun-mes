import pytest

from apps.kuaioa.utils.form_request_review_sheet import (
    review_sheet_has_countersign_targets,
    user_is_review_sheet_countersign_participant,
    validate_review_sheet_on_submit,
)
from infra.exceptions.exceptions import BusinessLogicError


def test_review_sheet_countersign_targets():
    assert not review_sheet_has_countersign_targets({})
    assert review_sheet_has_countersign_targets({"countersign_department_ids": [1]})
    assert review_sheet_has_countersign_targets({"countersign_user_ids": [2]})


def test_validate_review_sheet_requires_content_and_countersign():
    base = {
        "review_type": "prototype",
        "review_subject": "主题",
        "review_content": "内容",
    }
    validate_review_sheet_on_submit({**base, "countersign_user_ids": [10]})

    with pytest.raises(BusinessLogicError):
        validate_review_sheet_on_submit(base)

    with pytest.raises(BusinessLogicError):
        validate_review_sheet_on_submit(
            {"countersign_user_ids": [1], "review_subject": "x", "review_content": "y"}
        )


def test_user_is_countersign_participant():
    fd = {"countersign_user_ids": [5], "countersign_department_ids": [3]}
    assert user_is_review_sheet_countersign_participant(fd, user_id=5, department_id=99)
    assert user_is_review_sheet_countersign_participant(fd, user_id=1, department_id=3)
    assert not user_is_review_sheet_countersign_participant(fd, user_id=1, department_id=1)
