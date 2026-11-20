"""
API 请求硬截止（纯 ASGI）。

单 worker 下若 await 无上界，网关先 504 而后端仍占满事件循环。
对本进程内 /api 请求施加墙钟超时，超时返回 504 JSON 并取消下游任务。

环境变量：
- RIVEREDGE_API_REQUEST_TIMEOUT_SECONDS（默认 25，普通 API，须低于网关 header 超时）
- RIVEREDGE_API_LONG_REQUEST_TIMEOUT_SECONDS（默认 280，主数据等 sync-from-source /
  流式同步；须低于网关 read/response_header，当前 Caddy 多为 300s）
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Callable, Iterable

from loguru import logger


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning("环境变量 {}={!r} 非法浮点，回退默认 {}", name, raw, default)
        return default
    if value <= 0:
        logger.warning("环境变量 {}={!r} 须为正数，回退默认 {}", name, raw, default)
        return default
    return value


_EXCLUDED_PREFIXES: tuple[str, ...] = (
    "/health",
    "/metrics",
    "/openapi.json",
    "/docs",
    "/redoc",
)

# 主数据 / 业务「从源同步」整批拉取，前端客户端超时约 600s；进程内须放宽，
# 否则计量单位等前置同步常在默认 25s 被掐成 504（物料同步弹「处理超过时限」）。
_LONG_REQUEST_PATH_SUFFIXES: tuple[str, ...] = (
    "/sync-from-source",
)


def _path_excluded(path: str) -> bool:
    for prefix in _EXCLUDED_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def _is_long_request_path(path: str) -> bool:
    for suffix in _LONG_REQUEST_PATH_SUFFIXES:
        if path == suffix or path.endswith(suffix):
            return True
    return False


class RequestTimeoutMiddleware:
    """纯 ASGI：对 /api/ 施加 asyncio.wait_for 墙钟超时。"""

    def __init__(
        self,
        app: Callable[..., Any],
        timeout_seconds: float | None = None,
        long_timeout_seconds: float | None = None,
    ) -> None:
        self.app = app
        self.timeout_seconds = (
            float(timeout_seconds)
            if timeout_seconds is not None
            else _float_env("RIVEREDGE_API_REQUEST_TIMEOUT_SECONDS", 25.0)
        )
        self.long_timeout_seconds = (
            float(long_timeout_seconds)
            if long_timeout_seconds is not None
            else _float_env("RIVEREDGE_API_LONG_REQUEST_TIMEOUT_SECONDS", 280.0)
        )

    def _timeout_for_path(self, path: str) -> float:
        if _is_long_request_path(path):
            return self.long_timeout_seconds
        return self.timeout_seconds

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if not path.startswith("/api/") or _path_excluded(path):
            await self.app(scope, receive, send)
            return

        timeout_seconds = self._timeout_for_path(path)
        response_started = False

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await asyncio.wait_for(
                self.app(scope, receive, send_wrapper),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            method = scope.get("method", "?")
            logger.error(
                "API 请求超时已取消: {} {} timeout={}s",
                method,
                path,
                timeout_seconds,
            )
            if response_started:
                # 已向客户端写过响应头，无法再发 504；任务已取消，连接由 ASGI 收尾
                return
            body = json.dumps(
                {
                    "detail": f"请求处理超时（{timeout_seconds:g}s），请稍后重试",
                    "code": "REQUEST_TIMEOUT",
                },
                ensure_ascii=False,
            ).encode("utf-8")
            headers: Iterable[tuple[bytes, bytes]] = (
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            )
            await send(
                {
                    "type": "http.response.start",
                    "status": 504,
                    "headers": list(headers),
                }
            )
            await send({"type": "http.response.body", "body": body})
