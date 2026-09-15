"""AI 流式 SSE 桥接：完成后推送 ai.stream.done。"""

from __future__ import annotations

from typing import Any, AsyncIterator

from core.services.realtime.dispatch import schedule_user_realtime_event
from core.services.realtime.events import AI_STREAM_DONE, AI_STREAM_START


async def wrap_ai_sse_stream(
    stream: AsyncIterator[bytes],
    *,
    tenant_id: int,
    user_id: int,
    session_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> AsyncIterator[bytes]:
    schedule_user_realtime_event(
        tenant_id=tenant_id,
        user_id=user_id,
        event=AI_STREAM_START,
        payload={
            "session_id": session_id or "",
            **(meta or {}),
        },
    )
    try:
        async for chunk in stream:
            yield chunk
    finally:
        schedule_user_realtime_event(
            tenant_id=tenant_id,
            user_id=user_id,
            event=AI_STREAM_DONE,
            payload={
                "session_id": session_id or "",
                **(meta or {}),
            },
        )
