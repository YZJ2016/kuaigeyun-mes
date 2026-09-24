"""KU-AI MCP 白名单管理服务（KR-D11，S4）：mcp_servers CRUD + options。

- 归属校验统一入口 get_server：tenant_id 强过滤，跨租户/软删/不存在
  一律 404（KR-I1）。
- 保存路径守卫（create/update 共用，与运行时建连同口径失败关闭）：
  transport 仅 http、endpoint 出站 URL 校验（同步 DNS，经
  asyncio.to_thread 离 loop）、allowed_tools 非空且禁 SQL 类工具名、
  status 闭集 启用|停用、name/code 去空白非空。
- token 复用 IntegrationConfig/api_key 口径（KR-D5 惯例）：列存，
  出参打码 {"token": "****"|None, "token_configured": bool}，不回明文；
  写路径打码占位（"****"/"********"）/空白视为保留原值，显式 null 清空。
- delete_server 仅软删本行；档案侧引用按 deleted_at/status 过滤，
  重建同名 code 受部分唯一索引保护。
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from apps.kuaiai.constants import CATALOG_STATUSES, STATUS_ENABLED
from apps.kuaiai.models.mcp import KuaiaiMcpServer
from apps.kuaiai.schemas.mcp import McpServerCreate, McpServerUpdate
from apps.kuaiai.services.catalog_service import (
    _is_masked_or_blank,
    masked_api_key_fields,
)
from apps.kuaiai.services.mcp_guard import (
    require_allowed_tools,
    require_http_transport,
    require_safe_http_url,
)
from core.utils.timezone_utils import now_utc
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError
from infra.models.user import User


def masked_token_fields(token: Optional[str]) -> Dict[str, Any]:
    """token 出参打码：完全复刻 catalog_service.masked_api_key_fields 口径，
    键名映射 api_key→token（"****"|None + token_configured）。"""
    masked = masked_api_key_fields(token)
    return {
        "token": masked["api_key"] or None,
        "token_configured": masked["api_key_configured"],
    }


def _audit_create(user: Optional[User]) -> Dict[str, Any]:
    if user is None or getattr(user, "id", None) is None:
        return {}
    name = getattr(user, "full_name", None) or getattr(user, "username", None)
    return {
        "created_by": user.id,
        "created_by_name": name,
        "updated_by": user.id,
        "updated_by_name": name,
    }


def _audit_update(user: Optional[User]) -> Dict[str, Any]:
    if user is None or getattr(user, "id", None) is None:
        return {}
    return {
        "updated_by": user.id,
        "updated_by_name": getattr(user, "full_name", None)
        or getattr(user, "username", None),
    }


def _require_status(value: Optional[str]) -> str:
    stripped = (value or "").strip()
    if stripped not in CATALOG_STATUSES:
        raise BusinessLogicError("status 仅允许 启用|停用")
    return stripped


def _require_non_blank(field: str, value: Optional[str]) -> str:
    stripped = (value or "").strip()
    if not stripped:
        raise BusinessLogicError(f"{field} 不允许为空")
    return stripped


class McpService:
    """MCP 白名单管理面（类方法风格，对齐 KnowledgeService）。"""

    @classmethod
    def server_out(cls, server: KuaiaiMcpServer) -> Dict[str, Any]:
        """服务器行响应 dict：token 打码回显，不含明文/tenant_id。"""
        return {
            "id": server.id,
            "uuid": str(server.uuid),
            "code": server.code,
            "name": server.name,
            "transport": server.transport,
            "endpoint": server.endpoint,
            "allowed_tools": server.allowed_tools,
            "status": server.status,
            "created_at": server.created_at,
            "updated_at": server.updated_at,
            **masked_token_fields(server.token),
        }

    @classmethod
    async def get_server(cls, tenant_id: int, server_id: int) -> KuaiaiMcpServer:
        """本租户服务器查询：跨租户/软删/不存在一律 404（KR-I1）。"""
        server = await KuaiaiMcpServer.get_or_none(
            tenant_id=tenant_id, id=server_id, deleted_at__isnull=True
        )
        if server is None:
            raise NotFoundError("MCP 服务器", str(server_id))
        return server

    @classmethod
    async def list_servers(
        cls, tenant_id: int, *, page: int = 1, page_size: int = 20
    ) -> Dict[str, Any]:
        """管理 list：本租户 MCP 服务器分页 {items,total}。"""
        q = KuaiaiMcpServer.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        total = await q.count()
        items = await q.order_by("id").offset((page - 1) * page_size).limit(page_size)
        return {"items": items, "total": total}

    @classmethod
    async def list_options(cls, tenant_id: int) -> List[Dict[str, Any]]:
        """启用服务器下拉项（档案勾选 mcp_server_ids 用）；不含 token/endpoint。"""
        rows = await KuaiaiMcpServer.filter(
            tenant_id=tenant_id, status=STATUS_ENABLED, deleted_at__isnull=True
        ).order_by("id").all()
        return [{"id": r.id, "name": r.name, "code": r.code} for r in rows]

    @classmethod
    async def create_server(
        cls, tenant_id: int, user: User, payload: McpServerCreate
    ) -> KuaiaiMcpServer:
        # 先校验纯字段规则（不触库），再做重名查询（KR-I3：失败先于 DB 写入）
        name = _require_non_blank("name", payload.name)
        code = _require_non_blank("code", payload.code)
        transport = require_http_transport(payload.transport)
        # require_safe_http_url 内含同步 DNS，to_thread 离 loop
        # （与 mcp_client_service 建连侧一致，避免阻塞事件循环）
        endpoint = await asyncio.to_thread(require_safe_http_url, payload.endpoint)
        allowed_tools = require_allowed_tools(payload.allowed_tools)
        status = (
            _require_status(payload.status)
            if payload.status is not None
            else STATUS_ENABLED
        )
        dup = await KuaiaiMcpServer.get_or_none(
            tenant_id=tenant_id, code=code, deleted_at__isnull=True
        )
        if dup is not None:
            raise BusinessLogicError(f"服务器代码 {code} 已存在")
        # IntegrationConfig 惯例：打码占位/空串/None → 不写库（create 即 None）
        token = None if _is_masked_or_blank(payload.token) else payload.token.strip()
        return await KuaiaiMcpServer.create(
            tenant_id=tenant_id,
            code=code,
            name=name,
            transport=transport,
            endpoint=endpoint,
            token=token,
            allowed_tools=allowed_tools,
            status=status,
            **_audit_create(user),
        )

    @classmethod
    async def update_server(
        cls, tenant_id: int, user: User, server_id: int, payload: McpServerUpdate
    ) -> KuaiaiMcpServer:
        server = await cls.get_server(tenant_id, server_id)
        data = payload.model_dump(exclude_unset=True)

        # 非空列显式传 null 视为非法（避免写入 NULL）；token 例外（null=清空）
        for non_nullable in ("code", "name", "transport", "endpoint", "allowed_tools"):
            if non_nullable in data and data[non_nullable] is None:
                raise BusinessLogicError(f"{non_nullable} 不允许为空")
        if "name" in data:
            data["name"] = _require_non_blank("name", data["name"])
        if "code" in data:
            code = _require_non_blank("code", data["code"])
            if code != server.code:  # 未变更 code 跳过重名查询
                dup = await KuaiaiMcpServer.get_or_none(
                    tenant_id=tenant_id, code=code, deleted_at__isnull=True
                )
                if dup is not None and dup.id != server.id:
                    raise BusinessLogicError(f"服务器代码 {code} 已存在")
            data["code"] = code
        if "transport" in data:
            data["transport"] = require_http_transport(data["transport"])
        if "endpoint" in data:
            data["endpoint"] = await asyncio.to_thread(
                require_safe_http_url, data["endpoint"]
            )
        if "allowed_tools" in data:
            data["allowed_tools"] = require_allowed_tools(data["allowed_tools"])
        if "status" in data:
            data["status"] = _require_status(data["status"])
        if "token" in data:
            # 显式 null=清空；打码占位/空白=保留原值不写库；其余写新值
            new_token = data.pop("token")
            if new_token is None:
                data["token"] = None
            elif not _is_masked_or_blank(new_token):
                data["token"] = new_token.strip()

        data.update(_audit_update(user))
        await server.update_from_dict(data).save()
        return server

    @classmethod
    async def delete_server(cls, tenant_id: int, user: User, server_id: int) -> None:
        """软删服务器行；档案引用按 deleted_at/status 过滤，不做级联。"""
        server = await cls.get_server(tenant_id, server_id)
        server.deleted_at = now_utc()
        server.update_from_dict(_audit_update(user))
        await server.save()
