"""研发交付物下发范围（L53/L57 等 #59/#63 项目侧资料）。"""

from __future__ import annotations

RD_DELIVERABLE_ISSUE_TARGET_USER = "user"
RD_DELIVERABLE_ISSUE_TARGET_ROLE = "role"
RD_DELIVERABLE_ISSUE_TARGET_DEPARTMENT = "department"

RD_DELIVERABLE_ISSUE_TARGET_TYPES = frozenset(
    {
        RD_DELIVERABLE_ISSUE_TARGET_USER,
        RD_DELIVERABLE_ISSUE_TARGET_ROLE,
        RD_DELIVERABLE_ISSUE_TARGET_DEPARTMENT,
    }
)

# 须「批准 + 下发」后，非维护者使用方才可下载现行版
RD_DELIVERABLE_TYPES_ISSUE_SCOPED = frozenset(
    {
        "drawing_silkscreen",
        "drawing_assembly",
        "drawing_packaging",
        "drawing_pcb_assembly",
        "customer_spec",
        "customer_approval",
    }
)

MAINTAINER_PERMISSION_CODES = frozenset(
    {
        "kuaiplm:project:update",
        "kuaiplm:project:create",
        "kuaiplm:project:approve",
    }
)
