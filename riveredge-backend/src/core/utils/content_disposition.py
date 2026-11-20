"""HTTP Content-Disposition 文件名（避免 Starlette latin-1 头编码错误）。"""

from __future__ import annotations

from urllib.parse import quote


def build_attachment_content_disposition(filename: str, *, disposition: str = "attachment") -> str:
    """RFC 5987：含中文等非 latin-1 字符时使用 filename*=UTF-8''…"""
    name = (filename or "download").strip() or "download"
    try:
        name.encode("latin-1")
        return f'{disposition}; filename="{name}"'
    except UnicodeEncodeError:
        encoded = quote(name, safe="")
        return f"{disposition}; filename*=UTF-8''{encoded}"
