"""RealtimePublisher 抽象与工厂。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from infra.config.infra_config import infra_settings


class RealtimePublisher(ABC):
    @abstractmethod
    async def publish_to_user(
        self,
        *,
        tenant_id: int,
        user_id: int,
        event: str,
        payload: dict[str, Any],
    ) -> bool:
        """向用户私有频道推送事件；失败返回 False，不抛异常。"""

    @abstractmethod
    async def publish_to_channel(
        self,
        *,
        channel: str,
        event: str,
        payload: dict[str, Any],
    ) -> bool:
        """向指定频道推送事件。"""


class NoopRealtimePublisher(RealtimePublisher):
    async def publish_to_user(
        self,
        *,
        tenant_id: int,
        user_id: int,
        event: str,
        payload: dict[str, Any],
    ) -> bool:
        return False

    async def publish_to_channel(
        self,
        *,
        channel: str,
        event: str,
        payload: dict[str, Any],
    ) -> bool:
        return False


_publisher: RealtimePublisher | None = None


def realtime_backend() -> str:
    return (infra_settings.REALTIME_BACKEND or "noop").strip().lower()


def realtime_enabled() -> bool:
    return realtime_backend() in ("centrifugo", "socketio")


def get_realtime_publisher() -> RealtimePublisher:
    global _publisher
    if _publisher is not None:
        return _publisher

    backend = realtime_backend()
    if backend == "socketio":
        from core.services.realtime.socketio_publisher import SocketIORealtimePublisher

        _publisher = SocketIORealtimePublisher()
    elif backend == "centrifugo":
        from core.services.realtime.centrifugo_publisher import CentrifugoRealtimePublisher

        _publisher = CentrifugoRealtimePublisher()
        if not _publisher.is_configured():
            logger.warning(
                "REALTIME_BACKEND=centrifugo 但未配置 CENTRIFUGO_API_URL/API_KEY，回退 noop"
            )
            _publisher = NoopRealtimePublisher()
    else:
        _publisher = NoopRealtimePublisher()
    return _publisher


def reset_realtime_publisher_cache() -> None:
    global _publisher
    _publisher = None
