"""python-socketio：与 FastAPI 同进程，uv 可安装。"""

from __future__ import annotations

from typing import Any

import socketio
from loguru import logger

from core.services.realtime.channels import (
    personal_channel,
    tenant_andon_channel,
    tenant_kuaiiot_channel,
)
from infra.config.infra_config import infra_settings

_sio: socketio.AsyncServer | None = None
_sid_context: dict[str, dict[str, Any]] = {}


def realtime_backend() -> str:
    return (infra_settings.REALTIME_BACKEND or "noop").strip().lower()


def socketio_active() -> bool:
    return realtime_backend() == "socketio"


def get_socketio_server() -> socketio.AsyncServer | None:
    return _sio


def _register_handlers(sio: socketio.AsyncServer) -> None:
    @sio.event
    async def connect(sid: str, environ: dict, auth: dict | None) -> bool:
        from infra.domain.security.security import resolve_bearer_payload

        auth_dict = auth if isinstance(auth, dict) else {}
        token = auth_dict.get("token")
        if not token or not isinstance(token, str):
            logger.debug("Socket.IO 连接拒绝 sid={}: 缺少 token", sid)
            return False
        payload = resolve_bearer_payload(token.strip())
        if not payload:
            logger.debug("Socket.IO 连接拒绝 sid={}: token 无效", sid)
            return False
        try:
            user_id = int(payload.get("sub"))
        except (TypeError, ValueError):
            logger.debug("Socket.IO 连接拒绝 sid={}: sub 无效", sid)
            return False
        # 普通用户票带 tenant_id；平台超管须由客户端传选定组织（auth.tenant_id）
        raw_tenant = payload.get("tenant_id")
        if raw_tenant is None and payload.get("is_infra_superadmin"):
            raw_tenant = auth_dict.get("tenant_id")
        try:
            tenant_id = int(raw_tenant)
        except (TypeError, ValueError):
            logger.debug("Socket.IO 连接拒绝 sid={}: tenant_id 无效", sid)
            return False
        if user_id <= 0 or tenant_id <= 0:
            return False
        personal_room = personal_channel(tenant_id=tenant_id, user_id=user_id)
        andon_room = tenant_andon_channel(tenant_id=tenant_id)
        kuaiiot_room = tenant_kuaiiot_channel(tenant_id=tenant_id)
        await sio.enter_room(sid, personal_room)
        await sio.enter_room(sid, andon_room)
        await sio.enter_room(sid, kuaiiot_room)
        _sid_context[sid] = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "room": personal_room,
            "andon_room": andon_room,
            "kuaiiot_room": kuaiiot_room,
        }
        logger.debug("Socket.IO 已连接 sid={} room={}", sid, personal_room)
        return True

    @sio.event
    async def disconnect(sid: str) -> None:
        _sid_context.pop(sid, None)


def init_socketio_server() -> socketio.AsyncServer:
    global _sio
    if _sio is not None:
        return _sio
    _sio = socketio.AsyncServer(
        async_mode="asgi",
        cors_allowed_origins="*",
        logger=False,
        engineio_logger=False,
    )
    _register_handlers(_sio)
    return _sio


def wrap_app_with_socketio(fastapi_app: Any) -> Any:
    """REALTIME_BACKEND=socketio 时用 ASGI 包装 FastAPI。"""
    if not socketio_active():
        return fastapi_app
    sio = init_socketio_server()
    path = (infra_settings.REALTIME_SOCKET_PATH or "/socket.io").strip() or "/socket.io"
    logger.info("实时推送：python-socketio 已挂载 path={}", path)
    return socketio.ASGIApp(sio, fastapi_app, socketio_path=path)
