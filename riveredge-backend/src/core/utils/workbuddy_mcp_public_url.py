"""WorkBuddy MCP 公网地址：仅接受域名（或 host:port），落库固定为 https://{host}/mcp。"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from fastapi import HTTPException, status

WORKBUDDY_MCP_PUBLIC_PATH = "/mcp"

_HOST_RE = re.compile(
    r"^(?:"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"|(?:\d{1,3}\.){3}\d{1,3}"
    r"|[a-z0-9.-]+:\d+"
    r")$",
    re.IGNORECASE,
)


def _strip_to_host(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if "://" in s:
        parsed = urlparse(s)
        path = (parsed.path or "").rstrip("/") or ""
        if path and path != WORKBUDDY_MCP_PUBLIC_PATH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"MCP 地址路径须为 {WORKBUDDY_MCP_PUBLIC_PATH}，请只填写域名",
            )
        host = parsed.netloc or parsed.path.split("/")[0]
        return host.strip().lower()
    return s.split("/")[0].split("?")[0].strip().lower()


def normalize_workbuddy_mcp_public_url(raw: str | None) -> str:
    host = _strip_to_host(str(raw or ""))
    if not host:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请填写 MCP 域名")
    if not _HOST_RE.fullmatch(host):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MCP 域名格式无效（勿含路径；系统将自动使用 https 与 /mcp）",
        )
    return f"https://{host}{WORKBUDDY_MCP_PUBLIC_PATH}"


def parse_workbuddy_mcp_public_host(stored_url: str | None) -> str:
    return _strip_to_host(str(stored_url or ""))
