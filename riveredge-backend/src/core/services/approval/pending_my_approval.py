"""列表「待我审核」：当前用户在进行中审批实例上仍有 pending 任务的单据 id。"""

from __future__ import annotations

from typing import Optional

from core.models.approval_instance import ApprovalInstance
from core.models.approval_task import ApprovalTask


async def entity_ids_pending_my_approval(
    tenant_id: int,
    entity_type: str,
    viewer_id: Optional[int],
) -> list[int]:
    """返回 entity_type 下、viewer 仍需审批的单据 id。无待办时为空列表。"""
    if viewer_id is None or int(viewer_id) <= 0:
        return []
    wanted = str(entity_type or "").strip()
    if not wanted:
        return []

    instance_ids = await ApprovalTask.filter(
        tenant_id=tenant_id,
        approver_id=int(viewer_id),
        status="pending",
    ).values_list("approval_instance_id", flat=True)
    unique_instance_ids = list({int(item) for item in instance_ids if item})
    if not unique_instance_ids:
        return []

    instances = await ApprovalInstance.filter(
        tenant_id=tenant_id,
        id__in=unique_instance_ids,
        status="pending",
        deleted_at__isnull=True,
    ).all()

    found: list[int] = []
    seen: set[int] = set()
    for instance in instances:
        data = instance.data if isinstance(instance.data, dict) else {}
        if str(data.get("entity_type") or "").strip() != wanted:
            continue
        try:
            entity_id = int(data.get("entity_id"))
        except (TypeError, ValueError):
            continue
        if entity_id in seen:
            continue
        seen.add(entity_id)
        found.append(entity_id)
    return found
