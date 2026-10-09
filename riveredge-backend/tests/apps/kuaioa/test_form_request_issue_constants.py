from apps.kuaioa.constants.form_request_issue import (
    FORM_REQUEST_BUSINESS_TYPES_ISSUE_SCOPED,
    FORM_REQUEST_ISSUE_ATTACHMENT_FIELD_BY_BUSINESS,
)
from apps.kuaioa.utils.form_request_confirmation import validate_confirmation_on_submit
from infra.exceptions.exceptions import BusinessLogicError
import pytest


def test_tech_work_contact_in_issue_scope():
    assert "tech_work_contact" in FORM_REQUEST_BUSINESS_TYPES_ISSUE_SCOPED


def test_tech_work_contact_attachment_field():
    assert (
        FORM_REQUEST_ISSUE_ATTACHMENT_FIELD_BY_BUSINESS["tech_work_contact"]
        == "contact_attachment"
    )


def test_confirmation_in_issue_scope():
    assert "confirmation" in FORM_REQUEST_BUSINESS_TYPES_ISSUE_SCOPED


def test_confirmation_attachment_field():
    assert (
        FORM_REQUEST_ISSUE_ATTACHMENT_FIELD_BY_BUSINESS["confirmation"]
        == "confirmation_attachment"
    )


def test_review_sheet_in_issue_scope():
    assert "review_sheet" in FORM_REQUEST_BUSINESS_TYPES_ISSUE_SCOPED


def test_review_sheet_attachment_field():
    assert (
        FORM_REQUEST_ISSUE_ATTACHMENT_FIELD_BY_BUSINESS["review_sheet"]
        == "review_attachment"
    )


def test_material_issue_in_issue_scope():
    assert "material_issue" in FORM_REQUEST_BUSINESS_TYPES_ISSUE_SCOPED


def test_material_issue_attachment_field():
    assert (
        FORM_REQUEST_ISSUE_ATTACHMENT_FIELD_BY_BUSINESS["material_issue"]
        == "issue_attachment"
    )


def test_material_confirmation_requires_attachment():
    with pytest.raises(BusinessLogicError):
        validate_confirmation_on_submit(
            {
                "confirmation_kind": "material",
                "confirmation_subject": "s",
                "confirmation_content": "c",
                "confirmation_result": "agree",
            }
        )
