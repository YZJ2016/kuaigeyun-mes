"""L50 结构试验委托：general 审核链常量（无 seed）。"""

from apps.kuaiplm.constants.lab_request_types import (
    LAB_REQUEST_TYPE_GENERAL,
    LAB_REQUEST_TYPE_RD,
    LAB_REQUEST_TYPES_REQUIRE_MANAGER_REVIEW,
)


def test_general_requires_manager_review_with_rd():
    assert LAB_REQUEST_TYPE_RD in LAB_REQUEST_TYPES_REQUIRE_MANAGER_REVIEW
    assert LAB_REQUEST_TYPE_GENERAL in LAB_REQUEST_TYPES_REQUIRE_MANAGER_REVIEW
