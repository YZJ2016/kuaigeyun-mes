import pytest

from apps.kuaiplm.constants.lab_request_types import (
    LAB_REQUEST_AUDIT_NODE_BY_BUSINESS_TYPE,
    LAB_REQUEST_AUDIT_NODE_OUTSOURCE,
    LAB_REQUEST_TYPES_REQUIRE_MANAGER_REVIEW,
    LAB_REQUEST_TYPE_OUTSOURCE,
)
from apps.kuaiplm.utils.lab_request_outsource import (
    compute_outsource_capabilities,
    validate_outsource_on_submit,
)
from infra.exceptions.exceptions import ValidationError


def test_outsource_requires_manager_review_and_audit_node():
    assert LAB_REQUEST_TYPE_OUTSOURCE in LAB_REQUEST_TYPES_REQUIRE_MANAGER_REVIEW
    assert (
        LAB_REQUEST_AUDIT_NODE_BY_BUSINESS_TYPE[LAB_REQUEST_TYPE_OUTSOURCE]
        == LAB_REQUEST_AUDIT_NODE_OUTSOURCE
    )


def test_validate_outsource_on_submit():
    validate_outsource_on_submit(title="名称", test_reason="原由")
    with pytest.raises(ValidationError):
        validate_outsource_on_submit(title="名称", test_reason="")


def test_compute_outsource_capabilities():
    class Row:
        business_type = "outsource"
        title = "T"
        test_reason = "R"
        status = "pending_review"
        submitted_at = object()
        outsource_price = None
        accepted_at = None

    caps = compute_outsource_capabilities(Row())
    assert caps["filled"] is True
    assert caps["dept_approved"] is False
    assert caps["price_filled"] is False

    Row.status = "pending"
    Row.outsource_price = 100
    caps2 = compute_outsource_capabilities(Row())
    assert caps2["dept_approved"] is True
    assert caps2["price_filled"] is True
