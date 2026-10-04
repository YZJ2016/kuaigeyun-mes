"""快制造移动审批判定（委托 core.approval_audit_scope + audit 注册表）。"""

from __future__ import annotations

from core.models.approval_instance import ApprovalInstance
from core.services.approval.approval_audit_scope import (
    is_kuaizhizao_mobile_approval_instance,
    is_mobile_inbox_approval_task,
    resolve_audit_app_for_instance_data,
)

__all__ = [
    "is_kuaizhizao_approval_instance",
    "is_kuaizhizao_approval_pending_task",
    "resolve_audit_app_for_instance_data",
    "is_mobile_inbox_approval_task",
]


def is_kuaizhizao_approval_instance(instance: ApprovalInstance) -> bool:
    return is_kuaizhizao_mobile_approval_instance(instance)


def is_kuaizhizao_approval_pending_task(instance: ApprovalInstance) -> bool:
    """与消息中心待办拆分同口径：快制造 audit 审批不进收件箱待办。"""
    return is_kuaizhizao_mobile_approval_instance(instance)
