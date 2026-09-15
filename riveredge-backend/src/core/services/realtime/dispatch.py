"""异步调度实时推送（不阻塞业务写路径）。"""

from __future__ import annotations

import asyncio
from typing import Any

from core.services.realtime.channels import tenant_scoped_channel
from core.services.realtime.publisher import get_realtime_publisher, realtime_enabled


async def publish_user_realtime_event(
    *,
    tenant_id: int,
    user_id: int,
    event: str,
    payload: dict[str, Any],
) -> None:
    if not realtime_enabled():
        return
    if user_id <= 0:
        return
    publisher = get_realtime_publisher()
    await publisher.publish_to_user(
        tenant_id=tenant_id,
        user_id=user_id,
        event=event,
        payload=payload,
    )


def schedule_user_realtime_event(
    *,
    tenant_id: int,
    user_id: int,
    event: str,
    payload: dict[str, Any],
) -> None:
    if not realtime_enabled():
        return
    if user_id <= 0:
        return

    async def _run() -> None:
        await publish_user_realtime_event(
            tenant_id=tenant_id,
            user_id=user_id,
            event=event,
            payload=payload,
        )

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        asyncio.run(_run())


async def publish_tenant_realtime_event(
    *,
    tenant_id: int,
    scope: str,
    event: str,
    payload: dict[str, Any],
) -> None:
    if not realtime_enabled():
        return
    if tenant_id <= 0:
        return
    channel = tenant_scoped_channel(tenant_id=tenant_id, scope=scope)
    publisher = get_realtime_publisher()
    await publisher.publish_to_channel(channel=channel, event=event, payload=payload)


def schedule_tenant_realtime_event(
    *,
    tenant_id: int,
    scope: str,
    event: str,
    payload: dict[str, Any],
) -> None:
    if not realtime_enabled():
        return
    if tenant_id <= 0:
        return

    async def _run() -> None:
        await publish_tenant_realtime_event(
            tenant_id=tenant_id,
            scope=scope,
            event=event,
            payload=payload,
        )

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        asyncio.run(_run())
