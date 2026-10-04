"""审批实例所属应用（audit manifest 唯一真源）。

消息中心 vs 手机「审批」Tab 边界：
- ``UserMessage`` / IM → 消息中心「通知」「聊天」
- ``ApprovalTask`` 且 audit ``app == kuaizhizao`` → 底栏「审批」
- 其余 ``ApprovalTask``（含个人待办、轻办公等）→ 消息中心「待办」
"""

from __future__ import annotations

from typing import Any, Optional

from core.config.audit_registry import (
    AuditEntry,
    entry_by_entity_type,
    entry_by_entity_type_and_business,
    entry_by_node_key,
    entry_by_resource,
)
from core.models.approval_instance import ApprovalInstance


def _normalize_app(app: Optional[str]) -> Optional[str]:
    text = str(app or "").strip().lower()
    return text or None


def resolve_audit_entry_for_instance_data(
    data: dict[str, Any] | None,
    *,
    process_code: str | None = None,
) -> Optional[AuditEntry]:
    """从 instance.data + 流程 code 解析 manifest 登记项。"""
    payload = data if isinstance(data, dict) else {}
    if payload.get("is_personal"):
        return None

    resource = str(payload.get("audit_resource") or "").strip()
    if resource:
        hit = entry_by_resource(resource)
        if hit:
            return hit

    entity_type = str(payload.get("entity_type") or "").strip()
    business_type = str(payload.get("business_type") or "").strip()
    if entity_type:
        hit = entry_by_entity_type_and_business(
            entity_type,
            business_type or None,
        )
        if hit:
            return hit

    node_key = str(payload.get("audit_node_key") or process_code or "").strip()
    if node_key:
        return entry_by_node_key(node_key)

    return None


def resolve_audit_app_for_instance_data(
    data: dict[str, Any] | None,
    *,
    process_code: str | None = None,
) -> Optional[str]:
    stored = _normalize_app((data or {}).get("app") if isinstance(data, dict) else None)
    if stored:
        return stored
    entry = resolve_audit_entry_for_instance_data(data, process_code=process_code)
    return _normalize_app(entry.app if entry else None)


def enrich_instance_data_audit_app(
    data: dict[str, Any] | None,
    *,
    process_code: str | None,
) -> dict[str, Any]:
    """创建/更新实例前写入 audit 快照字段（来自注册表）。"""
    merged: dict[str, Any] = dict(data) if isinstance(data, dict) else {}
    if merged.get("is_personal"):
        return merged

    entry = resolve_audit_entry_for_instance_data(merged, process_code=process_code)
    if entry:
        merged["app"] = entry.app
        merged["audit_node_key"] = entry.node_key
        merged["audit_resource"] = entry.resource
        if entry.entity_type and not merged.get("entity_type"):
            merged["entity_type"] = entry.entity_type
        if entry.business_type and not merged.get("business_type"):
            merged["business_type"] = entry.business_type
    elif process_code:
        merged["audit_node_key"] = str(process_code).strip()
        app = resolve_audit_app_for_instance_data(merged, process_code=process_code)
        if app:
            merged["app"] = app
    return merged


def is_kuaizhizao_mobile_approval_instance(instance: ApprovalInstance) -> bool:
    """手机底栏「审批」列表/角标口径。"""
    data = instance.data if isinstance(instance.data, dict) else {}
    if data.get("is_personal"):
        return False
    process_code = instance.process.code if getattr(instance, "process", None) else None
    return resolve_audit_app_for_instance_data(data, process_code=process_code) == "kuaizhizao"


def is_mobile_inbox_approval_task(instance: ApprovalInstance) -> bool:
    """消息中心「待办」：个人任务或非快制造 audit 的 pending 审批任务。"""
    data = instance.data if isinstance(instance.data, dict) else {}
    if data.get("is_personal"):
        return True
    process_code = instance.process.code if getattr(instance, "process", None) else None
    app = resolve_audit_app_for_instance_data(data, process_code=process_code)
    return app != "kuaizhizao"
