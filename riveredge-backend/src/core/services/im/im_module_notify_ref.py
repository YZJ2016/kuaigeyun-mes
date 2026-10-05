"""IM 模块群系统通知去重键（纯函数，无 ORM 依赖）。"""

from __future__ import annotations

from typing import Optional


def resolve_module_notify_ref_id(
    *,
    message_log_uuid: str,
    entity_uuid: Optional[str] = None,
    business_document: Optional[str] = None,
    business_action: Optional[str] = None,
    variables: Optional[dict] = None,
) -> str:
    """
    同一业务事件会为每位收件人各写一条 MessageLog；群聊同步须共用 ref_id。
    """
    eu = str(entity_uuid or "").strip()
    action = str(business_action or "").strip()
    if eu:
        return f"{eu}:{action}" if action else eu

    vars_map = variables if isinstance(variables, dict) else {}
    doc = str(business_document or "").strip()
    wo = str(vars_map.get("work_order_id") or "").strip()
    if doc and action and wo:
        completed = str(vars_map.get("completed_operation_name") or "").strip()
        next_name = str(vars_map.get("next_operation_name") or "").strip()
        if action == "operation_completed" and completed and next_name:
            return f"{doc}:{action}:{wo}:{completed}:{next_name}"
        return f"{doc}:{action}:{wo}"

    return str(message_log_uuid)
