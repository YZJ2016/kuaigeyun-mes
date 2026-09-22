"""PLM 审批 auto_pass 写回与人工审核门控（与 audit_flow_guard 同一契约）。"""

from __future__ import annotations

from typing import Any, Optional

from core.services.approval.audit_binding_service import AuditBindingService
from core.services.approval.audit_flow_guard import (
    approval_instance_finished_on_submit,
    assert_manual_approval_action_allowed,
    get_approval_gate_status,
)


async def assert_plm_manual_approval_action(
    tenant_id: int,
    *,
    audit_node: str,
    entity_type: str,
    entity_id: int,
    doc_label: str,
    verb: str = "审核",
) -> None:
    if not await AuditBindingService.is_audit_enabled(tenant_id, audit_node):
        return
    gate = await get_approval_gate_status(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    assert_manual_approval_action_allowed(
        gate,
        doc_label=doc_label,
        verb=verb,
    )


def submit_instance_auto_passed(instance: Optional[Any]) -> bool:
    return bool(instance and approval_instance_finished_on_submit(instance))
