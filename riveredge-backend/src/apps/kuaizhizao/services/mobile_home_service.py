"""手机工作台首屏：一次请求、一次权限装载、并行轻量查询。"""

from __future__ import annotations

import asyncio
from typing import Any

from apps.kuaizhizao.services.menu_badge_counts_service import _section_quality_inspection
from apps.kuaizhizao.services.menu_badge_scope import BadgeScopeCtx
from apps.kuaizhizao.services.mobile_workbench import resolve_mobile_workbench_home
from apps.kuaizhizao.services.work_order_mobile_kpi import fetch_work_order_mobile_kpi
from core.models.approval_task import ApprovalTask
from core.services.approval.approval_instance_service import ApprovalInstanceService
from core.services.authorization.effective_access_service import EffectiveAccessService
from core.models.im_conversation import ImConversationMember
from core.services.im.im_service import ImService
from core.services.user.user_message_service import UserMessageService
from core.services.user.user_task_service import UserTaskService
from infra.models.user import User


async def _count_im_unread(tenant_id: int, user_id: int) -> int:
    member_rows = await ImConversationMember.filter(
        tenant_id=tenant_id,
        user_id=user_id,
        deleted_at__isnull=True,
    ).all()
    if not member_rows:
        return 0
    member_by_conv = {int(m.conversation_id): m for m in member_rows}
    unread_map = await ImService._batch_unread_counts(
        tenant_id=tenant_id,
        user_id=user_id,
        member_by_conv=member_by_conv,
    )
    return sum(int(v or 0) for v in unread_map.values())


async def list_mobile_pending_kuaizhizao_approvals(
    *,
    tenant_id: int,
    user_id: int,
    skip: int = 0,
    limit: int = 100,
) -> list:
    """手机「待我审批」列表与角标唯一真源。"""
    from apps.kuaizhizao.services.kuaizhizao_approval_scope import is_kuaizhizao_approval_instance

    instances = await ApprovalInstanceService.list_approval_instances(
        tenant_id=tenant_id,
        skip=skip,
        limit=limit,
        status="pending",
        pending_for_user_id=user_id,
    )
    return [
        inst
        for inst in instances
        if is_kuaizhizao_approval_instance(inst.data or {}, inst.title or "")
    ]


async def _count_pending_kuaizhizao_approvals(tenant_id: int, user_id: int) -> int:
    rows = await list_mobile_pending_kuaizhizao_approvals(
        tenant_id=tenant_id,
        user_id=user_id,
        skip=0,
        limit=500,
    )
    return len(rows)


async def _count_inbox_pending_tasks(tenant_id: int, user_id: int) -> int:
    """消息中心「待办」：排除快制造审批类 ApprovalTask。"""
    from apps.kuaizhizao.services.kuaizhizao_approval_scope import is_kuaizhizao_approval_pending_task

    tasks = await ApprovalTask.filter(
        tenant_id=tenant_id,
        approver_id=user_id,
        status="pending",
    ).prefetch_related("approval_instance")
    count = 0
    for task in tasks:
        inst = task.approval_instance
        if not inst or getattr(inst, "deleted_at", None) or inst.status != "pending":
            continue
        if is_kuaizhizao_approval_pending_task(inst.data or {}, inst.title or ""):
            continue
        count += 1
    return count


async def fetch_mobile_home_bootstrap(*, tenant_id: int, user: User) -> dict[str, Any]:
    access = await EffectiveAccessService.get(user.id, tenant_id, user=user)
    ctx = BadgeScopeCtx(tenant_id=tenant_id, user=user)

    async def workbench_sections() -> list[dict[str, Any]]:
        return await resolve_mobile_workbench_home(
            tenant_id=tenant_id,
            user=user,
            access=access,
        )

    async def quality_pending() -> int:
        fragment = await _section_quality_inspection(ctx)
        block = fragment.get("quality_inspection") or {}
        return int(block.get("pending") or 0)

    async def message_stats():
        return await UserMessageService.get_user_message_stats(
            tenant_id=tenant_id,
            user_id=user.id,
        )

    async def message_notices():
        listing = await UserMessageService.get_user_messages(
            tenant_id=tenant_id,
            user_id=user.id,
            page=1,
            page_size=5,
            unread_only=True,
        )
        notices: list[dict[str, str]] = []
        for m in listing.items[:3]:
            subject = (m.subject or "").strip()
            content = (m.content or "").strip()
            title = subject or content[:40] or "新消息"
            notices.append({"id": str(m.uuid), "title": title})
        return notices

    async def task_stats():
        return await UserTaskService.get_user_task_stats(
            tenant_id=tenant_id,
            user_id=user.id,
        )

    (
        sections,
        work_order_stats,
        pending_inspection_count,
        msg_stats,
        notices,
        t_stats,
        pending_kuaizhizao_approvals,
        pending_inbox_tasks,
        im_unread,
    ) = await asyncio.gather(
        workbench_sections(),
        fetch_work_order_mobile_kpi(tenant_id),
        quality_pending(),
        message_stats(),
        message_notices(),
        task_stats(),
        _count_pending_kuaizhizao_approvals(tenant_id, user.id),
        _count_inbox_pending_tasks(tenant_id, user.id),
        _count_im_unread(tenant_id, user.id),
    )

    unread = getattr(msg_stats, "unread", None)
    if unread is None and isinstance(msg_stats, dict):
        unread = msg_stats.get("unread", 0)
    pending_tasks = getattr(t_stats, "pending", None)
    if pending_tasks is None and isinstance(t_stats, dict):
        pending_tasks = t_stats.get("pending", 0)

    return {
        "sections": sections,
        "work_order_stats": work_order_stats,
        "pending_inspection_count": pending_inspection_count,
        "unread_message_count": int(unread or 0),
        "im_unread_count": int(im_unread or 0),
        "pending_task_count": int(pending_tasks or 0),
        "pending_inbox_task_count": int(pending_inbox_tasks or 0),
        "pending_kuaizhizao_approval_count": pending_kuaizhizao_approvals,
        "notices": notices,
    }
