"""从 FastAPI Request 提取客户端 IP、判定请求链路是否为 https。

仅当直连对端命中可信代理名单时才采信 X-Forwarded-For / X-Real-IP /
X-Forwarded-Proto；否则一律回退到 request.client.host 与本连接 scheme，
避免客户端伪造转发头绕过 IP 白名单或把 http 伪装成 https。

可信代理由环境变量（或 infra_settings 同名字段）配置，逗号分隔 IP / CIDR，
可用 ``*`` 表示全部信任（仅限「前面必有可信 LB」的部署）：

- ``TRUSTED_PROXY_IPS``（首选）
- ``FORWARDED_ALLOW_IPS``
- ``TRUSTED_PROXIES``

未配置时默认不信任任何转发头。
"""

import ipaddress
import os
from functools import lru_cache

from fastapi import Request

_TRUSTED_PROXY_KEYS = ("TRUSTED_PROXY_IPS", "FORWARDED_ALLOW_IPS", "TRUSTED_PROXIES")


def _trusted_proxy_raw() -> str:
    try:
        from infra.config.infra_config import infra_settings

        for key in _TRUSTED_PROXY_KEYS:
            value = getattr(infra_settings, key, "")
            if isinstance(value, str) and value.strip():
                return value
    except Exception:
        pass
    for key in _TRUSTED_PROXY_KEYS:
        value = os.environ.get(key)
        if value and value.strip():
            return value
    return ""


@lru_cache(maxsize=32)
def _trusted_networks(raw: str) -> tuple:
    entries = [item.strip() for item in raw.split(",") if item.strip()]
    if "*" in entries:
        return ("*",)
    networks = []
    for entry in entries:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def forwarded_headers_trusted(request: Request) -> bool:
    """直连对端是否在可信代理名单内；未配置名单时永不信任转发头。"""
    raw = _trusted_proxy_raw()
    if not raw.strip():
        return False
    peer = request.client.host if request.client else ""
    if not peer:
        return False
    networks = _trusted_networks(raw)
    if "*" in networks:
        return True
    try:
        ip = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(ip in network for network in networks)


def get_client_ip(request: Request) -> str:
    if forwarded_headers_trusted(request):
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
    if request.client:
        return request.client.host
    return "0.0.0.0"


def request_is_https(request: Request) -> bool:
    """本连接 https，或可信代理经 X-Forwarded-Proto 声明 https 时为真。"""
    if request.url.scheme == "https":
        return True
    if forwarded_headers_trusted(request):
        proto = request.headers.get("X-Forwarded-Proto", "")
        return proto.split(",")[0].strip().lower() == "https"
    return False
