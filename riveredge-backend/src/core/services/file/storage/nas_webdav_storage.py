"""
NAS WebDAV 文件存储适配器（铁威马 TOS 等）。

配置字段与应用连接器 nas_webdav 一致：base_url / username / password / root_path / verify_ssl。
"""

from __future__ import annotations

import asyncio
import os
import re
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional
from urllib.parse import quote, urljoin, urlsplit

import httpx
from loguru import logger

from core.services.file.storage.base import FileStorageBackend
from infra.exceptions.exceptions import NotFoundError, ValidationError

# 写探针路径须与业务上传一致（多级 MKCOL + PUT），避免「浅层探针通过、深路径上传失败」
_NAS_WEBDAV_WRITE_PROBE_KEY = "_riveredge_probe/1/2026/11/writable.txt"


def _validate_path_segments(parts: List[str]) -> List[str]:
    for part in parts:
        if part in (".", ".."):
            raise ValidationError("WebDAV 路径不允许包含相对目录段（. 或 ..）")
    return parts


def _normalize_root_path(root_path: Any) -> str:
    text = str(root_path or "").strip().replace("\\", "/")
    if text in ("", "/"):
        return ""
    parts = _validate_path_segments([p for p in text.strip("/").split("/") if p])
    return "/".join(parts)


def _encode_path_segments(relative: str) -> str:
    parts = _validate_path_segments([p for p in relative.replace("\\", "/").split("/") if p])
    return "/".join(quote(p, safe="") for p in parts)


def _raw_path_segments(relative: str) -> List[str]:
    return _validate_path_segments([p for p in relative.replace("\\", "/").split("/") if p])


def _read_local_file_bytes(local_path: str) -> bytes:
    with open(local_path, "rb") as fh:
        return fh.read()


_PROPFIND_BODY = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:"><d:prop><d:getcontentlength/></d:prop></d:propfind>'
)
_DAV_CONTENT_LENGTH_RE = re.compile(
    r"<(?:[Dd]:)?getcontentlength[^>]*>\s*(\d+)\s*</(?:[Dd]:)?getcontentlength>",
    re.IGNORECASE,
)

# 迁移单文件含 MKCOL + PUT + 存在校验，内网 NAS 也可能超过 60s
_NAS_WEBDAV_TIMEOUT = httpx.Timeout(180.0, connect=30.0)
_NAS_WEBDAV_RETRYABLE = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
)
_NAS_WEBDAV_MAX_ATTEMPTS = 3


def _parse_content_range_total(content_range: str) -> Optional[int]:
    text = (content_range or "").strip()
    if not text or "/" not in text:
        return None
    total = text.rsplit("/", 1)[-1].strip()
    if not total or total == "*":
        return None
    try:
        return int(total)
    except ValueError:
        return None


def _parse_dav_getcontentlength(xml_text: str) -> Optional[int]:
    match = _DAV_CONTENT_LENGTH_RE.search(xml_text or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _coerce_verify_ssl(raw: Any) -> bool:
    if raw is False or raw is None:
        return False
    if isinstance(raw, str) and raw.strip().lower() in {"0", "false", "no", "off"}:
        return False
    return bool(raw)


def build_nas_webdav_relative_key(root_path: str, object_key: str) -> str:
    """root_path + 业务 key → WebDAV 相对路径（无 scheme/host）。"""
    root = _normalize_root_path(root_path)
    key_parts = _raw_path_segments(str(object_key or "").lstrip("/"))
    key = "/".join(key_parts)
    if root and key:
        return f"{root}/{key}"
    return root or key


def _http_error_message(exc: Exception, *, base_url: str) -> str:
    if isinstance(exc, httpx.ConnectError):
        return (
            f"服务器无法连接 NAS WebDAV（{base_url}）。"
            "请确认 WebDAV URL 对应用服务器可达，不要填仅本机浏览器能打开的地址。"
        )
    if isinstance(exc, httpx.TimeoutException):
        return f"访问 NAS WebDAV 超时（{base_url}）。请检查网络或稍后重试。"
    if isinstance(exc, (httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError)):
        return (
            f"访问 NAS WebDAV 连接中断（{base_url}）。"
            "请确认 NAS 未休眠、WebDAV 服务稳定，或在网络空闲时重试迁移。"
        )
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else "?"
        return f"NAS WebDAV 返回 HTTP {status}（{base_url}）"
    text = str(exc).strip() or exc.__class__.__name__
    lowered = text.lower()
    if "certificate" in lowered or "ssl" in lowered or "tls" in lowered:
        return (
            f"NAS WebDAV HTTPS 证书校验失败（{base_url}）。"
            "铁威马等自签证书请在连接器中关闭「校验证书」，保存后再试。"
        )
    return f"访问 NAS WebDAV 失败（{base_url}）：{exc.__class__.__name__}"


class NasWebDavStorage(FileStorageBackend):
    backend_name = "nas_webdav"

    def __init__(self, config: Dict[str, Any], connection_uuid: Optional[str] = None):
        self.config = config
        self.connection_uuid = connection_uuid
        base = str(config.get("base_url") or "").strip().rstrip("/")
        if not base:
            raise ValidationError("NAS WebDAV 配置缺少 WebDAV URL（base_url）")
        if not base.startswith("http://") and not base.startswith("https://"):
            base = f"https://{base}"
        parsed = urlsplit(base)
        if parsed.username is not None or parsed.password is not None:
            raise ValidationError("WebDAV URL 不允许包含用户名或密码，请填写在独立账号密码字段中")
        if not parsed.hostname:
            raise ValidationError("NAS WebDAV URL 格式无效")
        host_port = f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname
        sanitized_base = f"{parsed.scheme}://{host_port}{parsed.path.rstrip('/')}"
        self.base_url = sanitized_base
        self.display_base_url = sanitized_base
        self._origin = (parsed.scheme.lower(), parsed.hostname.lower(), parsed.port)
        self.root_path = _normalize_root_path(config.get("root_path"))
        username = str(config.get("username") or "").strip()
        password = str(config.get("password") or "")
        if not username:
            raise ValidationError("NAS WebDAV 配置缺少用户名")
        if not password or password == "****":
            raise ValidationError("NAS WebDAV 配置缺少密码")
        self._auth = httpx.BasicAuth(username, password)
        # 铁威马等常见自签证书：默认不校验，避免上传直接 500；需要强制校验时可显式打开。
        self.verify_ssl = _coerce_verify_ssl(config.get("verify_ssl"))

    def object_href(self, key: str) -> str:
        relative = build_nas_webdav_relative_key(self.root_path, key)
        encoded = _encode_path_segments(relative) if relative else ""
        if encoded:
            return f"{self.base_url}/{encoded}"
        return f"{self.base_url}/"

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[httpx.AsyncClient]:
        # 禁止自动跨源重定向，防止 BasicAuth 凭据泄露；同源重定向由 _send_same_origin 控制
        async with httpx.AsyncClient(
            timeout=_NAS_WEBDAV_TIMEOUT,
            follow_redirects=False,
            verify=self.verify_ssl,
        ) as client:
            yield client

    def _is_same_origin(self, target_url: str) -> bool:
        parsed = urlsplit(target_url)
        if not parsed.scheme or not parsed.hostname:
            return False
        return (parsed.scheme.lower(), parsed.hostname.lower(), parsed.port) == self._origin

    async def _send_same_origin(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        cur_url = url
        for _ in range(4):
            resp = await client.request(method, cur_url, **kwargs, **self._request_kwargs())
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = (resp.headers.get("Location") or "").strip()
                if not loc:
                    return resp
                next_url = urljoin(cur_url, loc)
                if not self._is_same_origin(next_url):
                    raise ValidationError("WebDAV 服务器返回了跨源重定向，已拦截以保护凭据")
                cur_url = next_url
                continue
            return resp
        return resp

    def _request_kwargs(self) -> Dict[str, Any]:
        return {"auth": self._auth, "timeout": _NAS_WEBDAV_TIMEOUT}

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(_NAS_WEBDAV_MAX_ATTEMPTS):
            try:
                async with self._client() as client:
                    return await self._send_same_origin(client, method, url, **kwargs)
            except ValidationError:
                raise
            except _NAS_WEBDAV_RETRYABLE as exc:
                last_exc = exc
                if attempt + 1 < _NAS_WEBDAV_MAX_ATTEMPTS:
                    await asyncio.sleep(float(attempt + 1))
                    continue
                logger.warning("NAS WebDAV 请求异常 base={} err={}", self.display_base_url, exc)
                raise ValidationError(_http_error_message(exc, base_url=self.display_base_url)) from exc
            except Exception as exc:
                logger.warning("NAS WebDAV 请求异常 base={} err={}", self.display_base_url, exc)
                raise ValidationError(_http_error_message(exc, base_url=self.display_base_url)) from exc
        if last_exc is not None:
            raise ValidationError(_http_error_message(last_exc, base_url=self.display_base_url)) from last_exc
        raise ValidationError(f"访问 NAS WebDAV 失败（{self.display_base_url}）")

    async def _request_on_client(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """同一 TCP 连接上连续 MKCOL/PUT，减轻部分 NAS 对频繁短连接上传的 ReadError。"""
        last_exc: Optional[Exception] = None
        for attempt in range(_NAS_WEBDAV_MAX_ATTEMPTS):
            try:
                return await self._send_same_origin(client, method, url, **kwargs)
            except ValidationError:
                raise
            except _NAS_WEBDAV_RETRYABLE as exc:
                last_exc = exc
                if attempt + 1 < _NAS_WEBDAV_MAX_ATTEMPTS:
                    await asyncio.sleep(float(attempt + 1))
                    continue
                logger.warning("NAS WebDAV 请求异常 base={} err={}", self.display_base_url, exc)
                raise ValidationError(_http_error_message(exc, base_url=self.display_base_url)) from exc
            except Exception as exc:
                logger.warning("NAS WebDAV 请求异常 base={} err={}", self.display_base_url, exc)
                raise ValidationError(_http_error_message(exc, base_url=self.display_base_url)) from exc
        if last_exc is not None:
            raise ValidationError(_http_error_message(last_exc, base_url=self.display_base_url)) from last_exc
        raise ValidationError(f"访问 NAS WebDAV 失败（{self.display_base_url}）")

    async def _ensure_parent_collections(
        self,
        object_key: str,
        *,
        client: httpx.AsyncClient,
    ) -> None:
        """按未编码路径段递归 MKCOL，避免对已编码路径再次 quote。"""
        relative = build_nas_webdav_relative_key(self.root_path, object_key)
        parts = _raw_path_segments(relative)
        if len(parts) <= 1:
            return
        dir_parts = parts[:-1]
        base = self.base_url.rstrip("/") + "/"
        built: List[str] = []
        for part in dir_parts:
            built.append(part)
            coll_href = base + "/".join(quote(p, safe="") for p in built) + "/"
            resp = await self._request_on_client(client, "MKCOL", coll_href)
            if resp.status_code in (201, 405, 301, 302, 307, 308, 409):
                continue
            if resp.status_code >= 400:
                logger.warning(
                    "WebDAV 创建目录失败 status={} url={} body={}",
                    resp.status_code,
                    coll_href,
                    (resp.text or "")[:200],
                )
                raise ValidationError(
                    f"WebDAV 创建目录失败 HTTP {resp.status_code}（{self.display_base_url}）"
                )

    async def put(self, key: str, data: bytes, content_type: Optional[str] = None) -> None:
        href = self.object_href(key)
        headers: Dict[str, str] = {}
        ct = (content_type or "").strip()
        if ct:
            headers["Content-Type"] = ct
        async with self._client() as client:
            await self._ensure_parent_collections(key, client=client)
            resp = await self._request_on_client(
                client,
                "PUT",
                href,
                content=data,
                headers=headers or None,
            )
        if resp.status_code not in (200, 201, 204):
            logger.warning(
                "WebDAV 上传失败 status={} url={} body={}",
                resp.status_code,
                href,
                (resp.text or "")[:200],
            )
            raise ValidationError(
                f"WebDAV 上传失败 HTTP {resp.status_code}（{self.display_base_url}）"
            )

    async def put_file(self, key: str, local_path: str, content_type: Optional[str] = None) -> None:
        if not os.path.isfile(local_path):
            logger.warning("WebDAV 上传失败，本地文件不存在 path={}", local_path)
            raise ValidationError("本地待上传文件不存在")
        href = self.object_href(key)
        headers: Dict[str, str] = {}
        ct = (content_type or "").strip()
        if ct:
            headers["Content-Type"] = ct
        body = await asyncio.to_thread(_read_local_file_bytes, local_path)
        async with self._client() as client:
            await self._ensure_parent_collections(key, client=client)
            resp = await self._request_on_client(
                client,
                "PUT",
                href,
                content=body,
                headers=headers or None,
            )
        if resp.status_code not in (200, 201, 204):
            logger.warning(
                "WebDAV 上传失败 status={} url={} body={}",
                resp.status_code,
                href,
                (resp.text or "")[:200],
            )
            raise ValidationError(
                f"WebDAV 上传失败 HTTP {resp.status_code}（{self.display_base_url}）"
            )

    async def get(self, key: str) -> bytes:
        href = self.object_href(key)
        resp = await self._request("GET", href)
        if resp.status_code == 404:
            raise NotFoundError("文件")
        if resp.status_code >= 400:
            logger.warning(
                "WebDAV 下载失败 status={} url={} body={}",
                resp.status_code,
                href,
                (resp.text or "")[:200],
            )
            raise ValidationError(
                f"WebDAV 下载失败 HTTP {resp.status_code}（{self.display_base_url}）"
            )
        return resp.content

    async def delete(self, key: str) -> bool:
        href = self.object_href(key)
        try:
            resp = await self._request("DELETE", href)
        except ValidationError:
            return False
        if resp.status_code in (200, 204, 404):
            return True
        return False

    async def _propfind_content_length(self, href: str) -> Optional[int]:
        resp = await self._request(
            "PROPFIND",
            href,
            headers={"Depth": "0", "Content-Type": "application/xml; charset=utf-8"},
            content=_PROPFIND_BODY,
        )
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            return None
        return _parse_dav_getcontentlength(resp.text or "")

    async def _length_via_range_get(self, href: str) -> Optional[int]:
        resp = await self._request("GET", href, headers={"Range": "bytes=0-0"})
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400 and resp.status_code not in (200, 206):
            logger.warning(
                "WebDAV 读取失败 status={} url={} body={}",
                resp.status_code,
                href,
                (resp.text or "")[:200],
            )
            raise ValidationError(
                f"WebDAV 读取失败 HTTP {resp.status_code}（{self.display_base_url}）"
            )
        total = _parse_content_range_total(resp.headers.get("Content-Range") or "")
        if total is not None:
            return total
        raw = resp.headers.get("Content-Length")
        if raw is not None:
            try:
                return int(raw)
            except ValueError:
                pass
        if resp.status_code == 200 and resp.content is not None:
            return len(resp.content)
        return None

    async def head_content_length(self, key: str) -> Optional[int]:
        href = self.object_href(key)
        resp = await self._request("HEAD", href)
        if resp.status_code == 404:
            return None
        if resp.status_code in (405, 501):
            dav_len = await self._propfind_content_length(href)
            if dav_len is not None:
                return dav_len
            return await self._length_via_range_get(href)
        if resp.status_code >= 400:
            logger.warning(
                "WebDAV HEAD 失败 status={} url={} body={}",
                resp.status_code,
                href,
                (resp.text or "")[:200],
            )
            raise ValidationError(
                f"WebDAV HEAD 失败 HTTP {resp.status_code}（{self.display_base_url}）"
            )
        raw = resp.headers.get("Content-Length")
        if raw is not None:
            try:
                return int(raw)
            except ValueError:
                pass
        dav_len = await self._propfind_content_length(href)
        if dav_len is not None:
            return dav_len
        return await self._length_via_range_get(href)

    async def exists(self, key: str) -> bool:
        return (await self.head_content_length(key)) is not None


async def probe_nas_webdav_storage(
    config: Dict[str, Any],
    *,
    write_probe: bool = True,
) -> Dict[str, Any]:
    """
    连接测试：PROPFIND root + 可选写探针（与文件迁移前置探测一致）。
    """
    storage = NasWebDavStorage(config)
    root_href = storage.object_href("")
    propfind_url = root_href if root_href.endswith("/") else f"{root_href.rstrip('/')}/"
    resp = await storage._request(
        "PROPFIND",
        propfind_url,
        headers={"Depth": "0"},
    )
    if resp.status_code >= 400 and resp.status_code not in (404,):
        opt = await storage._request("OPTIONS", storage.base_url)
        if opt.status_code >= 400:
            raise ValueError(
                f"无法访问 WebDAV（PROPFIND HTTP {resp.status_code}，OPTIONS HTTP {opt.status_code}）"
            )
    if not write_probe:
        return {"message": "WebDAV 连接成功（只读探测）"}
    probe_key = _NAS_WEBDAV_WRITE_PROBE_KEY
    body = b"riveredge-nas-webdav-probe"
    await storage.put(probe_key, body, content_type="text/plain")
    if not await storage.exists(probe_key):
        raise ValueError(
            "WebDAV 写探针失败：上传后无法 HEAD 读回"
            f"（{storage.display_base_url}）。请核对 WebDAV URL、Root Path 与账号对该目录的读写权限。"
        )
    await storage.delete(probe_key)
    return {"message": "WebDAV 连接成功（读写探针通过）"}
