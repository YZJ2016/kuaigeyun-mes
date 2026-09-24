"""KU-AI MCP 白名单守卫（KR-D11，≈ ktg-ai AiMcpGuard）。

保存路径与运行时建连两侧共用同一套失败关闭规则：

- ``require_http_transport``：仅放行 ``http``（映射 streamable_http；
  stdio/sse/websocket 拒绝——禁本地命令与任意远程形态）；
- ``require_safe_http_url``：仅 http/https、禁 userinfo、禁 localhost/
  metadata 主机名、DNS 必须可解析且禁回环/链路本地/组播/云元数据
  地址（169.254.169.254、100.100.100.200）。同步 DNS 解析，调用方
  自行决定 ``asyncio.to_thread``；
- ``is_forbidden_sql_tool`` / ``is_tool_allowed``：SQL 类工具名黑名单
  + allowed_tools CSV 成员校验（空名单/黑名单名一律拒绝，失败关闭）。
"""

from __future__ import annotations

import ipaddress
import re
import socket
import unicodedata
from typing import List
from urllib.parse import urlparse

from infra.exceptions.exceptions import BusinessLogicError

MCP_TRANSPORT_HTTP = "http"

# SQL 类工具名黑名单（对齐 ktg-ai FORBIDDEN_TOOLS；另含 *_query 后缀与
# execute_sql/run_sql 子串规则，见 is_forbidden_sql_tool）
FORBIDDEN_SQL_TOOL_NAMES = frozenset(
    {
        "execute_sql_query",
        "query_all_tables",
        "execute_sql",
        "sql_query",
        "run_sql",
        "query_database",
        "query_sql",
        "query",
        "list_tables",
        "read_query",
    }
)

_ILLEGAL_URL = "出站地址非法"


def _normalize_tool_name(name: str) -> str:
    """工具名规范化：NFKC + 去内部空白/下划线/连字符 + lower。

    防 "execute  sql"（双空格）/"executeSql"（CamelCase）/全角同形绕过
    黑名单比对。
    """
    return re.sub(r"[\s_\-]+", "", unicodedata.normalize("NFKC", name)).lower()


# 黑名单按同一规范化口径预编译（"execute_sql" → "executesql"）
_FORBIDDEN_SQL_TOOL_KEYS = frozenset(
    _normalize_tool_name(n) for n in FORBIDDEN_SQL_TOOL_NAMES
)


def require_http_transport(value: str | None) -> str:
    """仅放行 http 传输；空值归一为 http，其它值 400。"""
    transport = (value or "").strip() or MCP_TRANSPORT_HTTP
    if transport.lower() != MCP_TRANSPORT_HTTP:
        raise BusinessLogicError("仅支持 http 传输")
    return MCP_TRANSPORT_HTTP


def is_forbidden_sql_tool(tool_name: str | None) -> bool:
    """SQL 类工具名判定；空名失败关闭视为非法。

    比对前经 _normalize_tool_name 规范化，原 *_query 后缀规则等价于
    规范化名 endswith("query")。
    """
    name = _normalize_tool_name(tool_name or "")
    if not name:
        return True
    if name in _FORBIDDEN_SQL_TOOL_KEYS or name.endswith("query"):
        return True
    return "executesql" in name or "runsql" in name


def parse_allowed_tools(allowed_tools: str | None) -> List[str]:
    """CSV → 去空白去重名列表（保持原序）。"""
    items: List[str] = []
    for item in (allowed_tools or "").split(","):
        name = item.strip()
        if name and name not in items:
            items.append(name)
    return items


def is_tool_allowed(allowed_tools: str | None, tool_name: str | None) -> bool:
    """工具调用许可：非 SQL 黑名单且命中 allowed_tools CSV；空名单拒绝。"""
    if is_forbidden_sql_tool(tool_name):
        return False
    name = (tool_name or "").strip()
    return bool(name) and name in parse_allowed_tools(allowed_tools)


def require_allowed_tools(allowed_tools: str | None) -> str:
    """保存路径校验：allowed_tools 必须含至少一个非空名（失败关闭）。"""
    items = parse_allowed_tools(allowed_tools)
    if not items:
        raise BusinessLogicError("允许工具不能为空")
    forbidden = [n for n in items if is_forbidden_sql_tool(n)]
    if forbidden:
        raise BusinessLogicError(f"工具名不允许 SQL 类调用：{', '.join(forbidden)}")
    return ",".join(items)


def require_safe_http_url(raw: str | None) -> str:
    """出站 URL 校验（同步 DNS 解析，失败一律 400 拒绝）。

    仅 http/https；禁 userinfo；禁 localhost/metadata 系主机名；主机必须
    可解析且全部解析结果非回环/链路本地/组播/云元数据地址。
    """
    trimmed = (raw or "").strip()
    if not trimmed:
        raise BusinessLogicError(_ILLEGAL_URL)
    try:
        uri = urlparse(trimmed)
    except ValueError:
        raise BusinessLogicError(_ILLEGAL_URL)
    scheme = (uri.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise BusinessLogicError(_ILLEGAL_URL)
    if uri.username or uri.password:
        raise BusinessLogicError(_ILLEGAL_URL)
    host = (uri.hostname or "").strip().lower()
    if not host or _is_forbidden_hostname(host):
        raise BusinessLogicError(_ILLEGAL_URL)
    try:
        port = uri.port  # 非法端口（:99999/:abc）此处抛 ValueError，归一 400
    except ValueError:
        raise BusinessLogicError(_ILLEGAL_URL)
    try:
        infos = socket.getaddrinfo(host, port or (443 if scheme == "https" else 80))
    except (OSError, UnicodeError):
        # gaierror 是 OSError 子类；其余 OSError（如网络不可达）同归 400
        raise BusinessLogicError(_ILLEGAL_URL)
    addresses = {info[4][0] for info in infos if info and info[4]}
    if not addresses:
        raise BusinessLogicError(_ILLEGAL_URL)
    for addr in addresses:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            raise BusinessLogicError(_ILLEGAL_URL)
        if _is_forbidden_address(ip):
            raise BusinessLogicError(_ILLEGAL_URL)
    return trimmed


def _is_forbidden_hostname(host: str) -> bool:
    return (
        host == "localhost"
        or host.endswith(".localhost")
        or host == "metadata"
        or host.startswith("metadata.")
        or host == "metadata.google.internal"
    )


def _is_forbidden_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # 对齐 ktg-ai：拦回环/链路本地/组播/云元数据；内网 RFC1918 段放行
    # （企业内部 MCP server 是合法部署形态，不过度封禁）
    if isinstance(ip, ipaddress.IPv6Address):
        # v4-mapped（::ffff:a.b.c.d）与 v4-compatible（::/96）先归一为
        # IPv4 再走既有 v4 判定，防 "::ffff:169.254.169.254" 绕过 SSRF
        # 守卫；:: 与 ::1 本身不回落（低 32 位会误成 0.0.0.x），交由下方
        # v6 原生 unspecified/loopback 判定拦截
        mapped = ip.ipv4_mapped
        if mapped is not None:
            ip = mapped
        elif int(ip) >> 32 == 0 and int(ip) not in (0, 1):
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    if (
        ip.is_unspecified
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
    ):
        return True
    if isinstance(ip, ipaddress.IPv4Address):
        a, b, c, d = ip.packed
        if (a, b, c, d) == (169, 254, 169, 254):
            return True
        if (a, b, c, d) == (100, 100, 100, 200):
            return True
    return False
