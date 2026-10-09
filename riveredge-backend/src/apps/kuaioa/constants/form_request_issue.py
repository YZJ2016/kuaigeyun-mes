"""轻办公会签单下发范围（L54 技术工作联系单等）。"""

from __future__ import annotations

FORM_REQUEST_ISSUE_TARGET_USER = "user"
FORM_REQUEST_ISSUE_TARGET_ROLE = "role"
FORM_REQUEST_ISSUE_TARGET_DEPARTMENT = "department"

FORM_REQUEST_ISSUE_TARGET_TYPES = frozenset(
    {
        FORM_REQUEST_ISSUE_TARGET_USER,
        FORM_REQUEST_ISSUE_TARGET_ROLE,
        FORM_REQUEST_ISSUE_TARGET_DEPARTMENT,
    }
)

# 须「批准 + 下发」后，非维护者使用方才可查看附件 / 下载
FORM_REQUEST_BUSINESS_TYPES_ISSUE_SCOPED = frozenset(
    {
        "tech_work_contact",
        "confirmation",
        "review_sheet",
        "material_issue",
    }
)

# 各业务类型附件字段（form_data 内 file_uuid 字符串）
FORM_REQUEST_ISSUE_ATTACHMENT_FIELD_BY_BUSINESS: dict[str, str] = {
    "tech_work_contact": "contact_attachment",
    "confirmation": "confirmation_attachment",
    "review_sheet": "review_attachment",
    "material_issue": "issue_attachment",
}

MAINTAINER_PERMISSION_CODES = frozenset(
    {
        "kuaioa:form-request:update",
        "kuaioa:form-request:approve",
    }
)
