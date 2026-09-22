"""python-socketio 发布实现（同进程，无需独立服务）。"""

from __future__ import annotations

from typing import Any

from loguru import logger

from core.services.realtime.channels import personal_channel
from core.services.realtime.publisher import RealtimePublisher
from core.services.realtime.socketio_server import get_socketio_server
from core.utils.timezone_utils import resolve_business_datetime, to_api_isoformat


class SocketIORealtimePublisher(RealtimePublisher):
    def _envelope(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "event": event,
            "payload": payload,
            "ts": to_api_isoformat(resolve_business_datetime()),
        }

    async def publish_to_channel(
        self,
        *,
        channel: str,
        event: str,
        payload: dict[str, Any],
    ) -> bool:
        sio = get_socketio_server()
        if sio is None:
            logger.warning("Socket.IO 未初始化，跳过 publish channel={}", channel)
            return False
        try:
            await sio.emit("realtime", self._envelope(event, payload), room=channel)
            return True
        except Exception as exc:
            logger.warning("Socket.IO publish 失败 channel={}: {}", channel, exc)
            return False

    async def publish_to_user(
        self,
        *,
        tenant_id: int,
        user_id: int,
        event: str,
        payload: dict[str, Any],
    ) -> bool:
        channel = personal_channel(tenant_id=tenant_id, user_id=user_id)
        return await self.publish_to_channel(channel=channel, event=event, payload=payload)
