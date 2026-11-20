"""
全局共享的 httpx.AsyncClient 单例

大多数模块以前会在每次请求里 `async with httpx.AsyncClient(...) as client:`，
这会频繁新建 TCP 连接池、握手 TLS、解析 DNS，浪费资源。

本模块提供一个按 FastAPI lifespan 管理的全局 AsyncClient，调用方改为：

    from infra.infrastructure.http import get_http_client
    client = get_http_client()
    response = await client.get(url, timeout=3.0)

每次调用可以通过 ``timeout=`` / ``headers=`` / ``auth=`` 等参数覆盖默认行为，
不再需要 ``async with``。

SaaS 约束：全局 Client **不得持久化 Set-Cookie**。多租户共用进程时，
金蝶星空 LoginByAppSecret 会写 kdservice-sessionid；若进共享 CookieJar，
后一租户请求可能带上前一租户会话导致串账/鉴权失败。会话须由调用方用
请求头显式携带（见 kingdee_galaxy_service.apply_kingdee_galaxy_session_headers）。
"""

from __future__ import annotations

from http.cookiejar import CookieJar
from typing import Optional

import httpx
from loguru import logger


_DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_DEFAULT_LIMITS = httpx.Limits(max_keepalive_connections=20, max_connections=100)

_client: Optional[httpx.AsyncClient] = None


class DiscardCookieJar(CookieJar):
    """不落地任何 Cookie（httpx 会把传入的 CookieJar 挂到 client.cookies.jar）。"""

    def set_cookie(self, cookie, *args, **kwargs):  # type: ignore[no-untyped-def]
        return

    def extract_cookies(self, response, request):  # type: ignore[no-untyped-def]
        return


def _client_uses_discard_jar(client: httpx.AsyncClient) -> bool:
    jar = getattr(getattr(client, "cookies", None), "jar", None)
    return isinstance(jar, DiscardCookieJar)


def init_http_client() -> httpx.AsyncClient:
    """初始化全局 AsyncClient（由 lifespan 调用）。"""
    global _client
    if _client is not None and not _client.is_closed:
        if not _client_uses_discard_jar(_client):
            try:
                _client.cookies.clear()
            except Exception:
                pass
            _client.cookies = httpx.Cookies(DiscardCookieJar())
            logger.info("✅ 全局 httpx.AsyncClient Cookie jar 已切换为不落库")
        return _client
    _client = httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        limits=_DEFAULT_LIMITS,
        follow_redirects=True,
        cookies=DiscardCookieJar(),
    )
    logger.info("✅ 全局 httpx.AsyncClient 已初始化（Cookie 不落 jar）")
    return _client


async def close_http_client() -> None:
    """关闭全局 AsyncClient（由 lifespan 关闭阶段调用）。"""
    global _client
    if _client is not None and not _client.is_closed:
        try:
            await _client.aclose()
            logger.info("✅ 全局 httpx.AsyncClient 已关闭")
        except Exception as e:
            logger.warning(f"关闭全局 httpx.AsyncClient 时出错: {e}")
    _client = None


def get_http_client() -> httpx.AsyncClient:
    """取用全局 AsyncClient；首次调用若尚未初始化则即时初始化。"""
    if _client is None or _client.is_closed:
        return init_http_client()
    return _client
