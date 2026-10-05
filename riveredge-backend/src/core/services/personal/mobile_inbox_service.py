"""手机消息中心：单次 HTTP 内并行取聊天/通知/待办（共享登录用户上下文）。"""

from __future__ import annotations

import asyncio
from typing import Any

from core.services.im.im_service import ImService
from core.services.user.user_display_service import UserDisplayService
from core.services.user.user_message_service import UserMessageService
from core.services.user.user_task_service import UserTaskService
from infra.models.user import User


async def fetch_mobile_inbox_snapshot(*, tenant_id: int, user: User) -> dict[str, Any]:
    user_id = user.id

    async def conversations():
        res = await ImService.list_conversations(
            tenant_id=tenant_id,
            user_id=user_id,
            skip=0,
            limit=200,
        )
        return res.model_dump() if hasattr(res, "model_dump") else res

    async def contacts():
        result = await UserDisplayService.search(
            tenant_id=tenant_id,
            page=1,
            page_size=200,
            is_active=True,
        )
        items = []
        for row in result.get("items") or []:
            dumped = row.model_dump() if hasattr(row, "model_dump") else row
            if int(dumped.get("id") or 0) == int(user_id):
                continue
            items.append(dumped)
        return items

    async def messages():
        return await UserMessageService.get_user_messages(
            tenant_id=tenant_id,
            user_id=user_id,
            page=1,
            page_size=80,
        )

    async def message_stats():
        return await UserMessageService.get_user_message_stats(
            tenant_id=tenant_id,
            user_id=user_id,
        )

    async def tasks():
        return await UserTaskService.get_mobile_inbox_pending_tasks(
            tenant_id=tenant_id,
            user_id=user_id,
            page=1,
            page_size=50,
        )

    async def task_stats():
        return await UserTaskService.get_user_task_stats(
            tenant_id=tenant_id,
            user_id=user_id,
        )

    conv_res, msg_res, msg_stats, task_res, t_stats, contact_rows = await asyncio.gather(
        conversations(),
        messages(),
        message_stats(),
        tasks(),
        task_stats(),
        contacts(),
    )

    def _dump(obj: Any) -> Any:
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        return obj

    return {
        "conversations": conv_res.get("items", []) if isinstance(conv_res, dict) else [],
        "contacts": contact_rows,
        "messages": _dump(msg_res).get("items", []) if msg_res else [],
        "message_stats": _dump(msg_stats),
        "tasks": _dump(task_res).get("items", []) if task_res else [],
        "task_stats": _dump(t_stats),
    }
