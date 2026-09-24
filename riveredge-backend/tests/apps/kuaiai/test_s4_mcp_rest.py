"""KU-AI S4 单测：MCP 白名单管理面 REST + 服务（KR-D11）。

全部 mock Tortoise 查询 + socket.getaddrinfo（守卫同步 DNS），不需要真实
数据库/网络。覆盖：
- MCP server CRUD 全路径（create/get/update/delete/list 分页 {items,total}）
- 跨租户/软删/不存在一律 404
- options 只回 status=启用 行，仅 {id,name,code}，不回 tenant_id
- token 打码不回明文（"****" + token_configured）；写路径打码占位/空白
  保留原值，显式 null 清空
- code 组织内重名 400；name/code 空白 400；status 闭集 400
- 守卫：非 http transport 400；endpoint localhost/metadata/userinfo/
  非 http scheme/解析到回环或云元数据地址 400；allowed_tools 空或含
  SQL 类工具名 400
- 路由注册断言：六条 S4 路径/方法/权限码（options 先于 {server_id}）
"""

from __future__ import annotations

import socket
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.routing import APIRoute

from apps.kuaiai.api.router import router
from apps.kuaiai.models.mcp import KuaiaiMcpServer
from apps.kuaiai.schemas.mcp import (
    McpServerCreate,
    McpServerOut,
    McpServerUpdate,
)
from apps.kuaiai.services.mcp_service import McpService
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

TENANT = 7
OTHER_TENANT = 8
USER_ID = 5

_VALID_PAYLOAD = dict(
    code="mcp-erp",
    name="ERP MCP",
    endpoint="http://mcp.example.com/mcp",
    allowed_tools="query_workorder,list_workorder_tasks",
)


def _user(uid: int = USER_ID):
    return SimpleNamespace(id=uid, full_name="测试用户", username="tester")


@pytest.fixture(autouse=True)
def _public_dns():
    """默认所有主机解析到公网地址（守卫 happy path）；单测内可再 patch 覆盖。"""
    def _resolve(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 80))]

    with patch("socket.getaddrinfo", side_effect=_resolve):
        yield


def _qs(rows=(), count=None):
    """伪 QuerySet：链式方法返回自身，终端方法为 AsyncMock。"""
    q = MagicMock()
    rows = list(rows)
    for m in ("filter", "order_by", "offset"):
        setattr(q, m, MagicMock(return_value=q))
    q.limit = AsyncMock(return_value=rows)
    q.all = AsyncMock(return_value=rows)
    q.first = AsyncMock(return_value=rows[0] if rows else None)
    q.count = AsyncMock(return_value=len(rows) if count is None else count)
    q.exists = AsyncMock(return_value=bool(rows))
    return q


def _self_updating(ns: SimpleNamespace) -> SimpleNamespace:
    """update_from_dict 回自身并对字段生效（对齐 Tortoise Model 行为）。"""

    def _upd(data):
        ns.__dict__.update(data)
        return ns

    ns.update_from_dict = MagicMock(side_effect=_upd)
    ns.save = AsyncMock()
    return ns


def _server(sid=1, code="mcp-erp", tenant=TENANT, **over):
    row = dict(
        id=sid,
        uuid=f"uuid-mcp{sid}",
        tenant_id=tenant,
        code=code,
        name="ERP MCP",
        transport="http",
        endpoint="http://mcp.example.com/mcp",
        token=None,
        allowed_tools="query_workorder,list_workorder_tasks",
        status="启用",
        deleted_at=None,
        created_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
        updated_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
    )
    row.update(over)
    return _self_updating(SimpleNamespace(**row))


# ------------------------------------------------------------ service: CRUD


class TestMcpServerCrud:
    @pytest.mark.asyncio
    async def test_create_happy_path(self):
        created = {}

        async def _create(**kw):
            created.update(kw)
            return _server(code=kw["code"], name=kw["name"])

        payload = McpServerCreate(**{**_VALID_PAYLOAD, "code": "  mcp-erp  ", "name": "  ERP MCP  "})
        with (
            patch.object(
                KuaiaiMcpServer, "get_or_none", new=AsyncMock(return_value=None)
            ),
            patch.object(
                KuaiaiMcpServer, "create", new=AsyncMock(side_effect=_create)
            ),
        ):
            server = await McpService.create_server(TENANT, _user(), payload)
        assert created["tenant_id"] == TENANT
        assert created["code"] == "mcp-erp"  # strip
        assert created["name"] == "ERP MCP"
        assert created["transport"] == "http"  # 缺省归一
        assert created["endpoint"] == "http://mcp.example.com/mcp"
        assert created["allowed_tools"] == "query_workorder,list_workorder_tasks"
        assert created["status"] == "启用"  # 缺省启用
        assert created["token"] is None
        assert created["created_by"] == USER_ID
        assert created["updated_by"] == USER_ID
        assert server.code == "mcp-erp"

    @pytest.mark.asyncio
    async def test_create_duplicate_code_400(self):
        with patch.object(
            KuaiaiMcpServer,
            "get_or_none",
            new=AsyncMock(return_value=_server()),
        ):
            with pytest.raises(BusinessLogicError) as exc:
                await McpService.create_server(
                    TENANT, _user(), McpServerCreate(**_VALID_PAYLOAD)
                )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_blank_name_code_400(self):
        with pytest.raises(BusinessLogicError):
            await McpService.create_server(
                TENANT, _user(), McpServerCreate(**{**_VALID_PAYLOAD, "name": "   "})
            )
        with pytest.raises(BusinessLogicError):
            await McpService.create_server(
                TENANT, _user(), McpServerCreate(**{**_VALID_PAYLOAD, "code": "   "})
            )

    @pytest.mark.asyncio
    async def test_create_bad_status_400(self):
        with pytest.raises(BusinessLogicError):
            await McpService.create_server(
                TENANT,
                _user(),
                McpServerCreate(**{**_VALID_PAYLOAD, "status": "冻结"}),
            )

    @pytest.mark.asyncio
    async def test_get_server_cross_tenant_404(self):
        with patch.object(
            KuaiaiMcpServer, "get_or_none", new=AsyncMock(return_value=None)
        ) as mock_get:
            with pytest.raises(NotFoundError):
                await McpService.get_server(OTHER_TENANT, 1)
        assert mock_get.await_args.kwargs["tenant_id"] == OTHER_TENANT

    @pytest.mark.asyncio
    async def test_update_code_dup_excludes_self(self):
        server = _server(sid=1, code="mcp-erp")
        other = _server(sid=2, code="mcp-wms")
        # get_or_none 顺序：get_server 取本行 → 重名查询取到他人行 → 400
        with patch.object(
            KuaiaiMcpServer,
            "get_or_none",
            new=AsyncMock(side_effect=[server, other]),
        ):
            with pytest.raises(BusinessLogicError):
                await McpService.update_server(
                    TENANT, _user(), 1, McpServerUpdate(code="mcp-wms")
                )
        server.update_from_dict.assert_not_called()

        # 改回自己同名（dup.id == server.id）不算冲突
        server2 = _server(sid=1, code="mcp-erp")
        with patch.object(
            KuaiaiMcpServer,
            "get_or_none",
            new=AsyncMock(side_effect=[server2, server2]),
        ):
            await McpService.update_server(
                TENANT, _user(), 1, McpServerUpdate(code="mcp-erp")
            )
        server2.update_from_dict.assert_called()

    @pytest.mark.asyncio
    async def test_update_same_code_skips_dup_query(self):
        """m7：code 未变更时跳过重名查询（get_or_none 仅归属查询一次）。"""
        server = _server(sid=1, code="mcp-erp")
        with patch.object(
            KuaiaiMcpServer, "get_or_none", new=AsyncMock(return_value=server)
        ) as mock_get:
            await McpService.update_server(
                TENANT, _user(), 1, McpServerUpdate(code="mcp-erp")
            )
        assert mock_get.await_count == 1
        server.update_from_dict.assert_called()

    @pytest.mark.asyncio
    async def test_update_non_nullable_null_400(self):
        server = _server()
        for field in ("code", "name", "transport", "endpoint", "allowed_tools"):
            with patch.object(
                KuaiaiMcpServer, "get_or_none", new=AsyncMock(return_value=server)
            ):
                with pytest.raises(BusinessLogicError):
                    await McpService.update_server(
                        TENANT, _user(), 1, McpServerUpdate(**{field: None})
                    )
        server.update_from_dict.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_writes_audit_and_saves(self):
        server = _server()
        with patch.object(
            KuaiaiMcpServer, "get_or_none", new=AsyncMock(return_value=server)
        ):
            await McpService.update_server(
                TENANT, _user(), 1, McpServerUpdate(name="新名", status="停用")
            )
        data = server.update_from_dict.call_args.args[0]
        assert data["name"] == "新名"
        assert data["status"] == "停用"
        assert data["updated_by"] == USER_ID
        server.save.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_soft_delete(self):
        server = _server()
        with patch.object(
            KuaiaiMcpServer, "get_or_none", new=AsyncMock(return_value=server)
        ):
            await McpService.delete_server(TENANT, _user(), 1)
        assert server.deleted_at is not None
        assert server.update_from_dict.call_args.args[0]["updated_by"] == USER_ID
        server.save.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_cross_tenant_404(self):
        with patch.object(
            KuaiaiMcpServer, "get_or_none", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await McpService.delete_server(OTHER_TENANT, _user(), 1)


class TestListAndOptions:
    @pytest.mark.asyncio
    async def test_list_servers_page_shape(self):
        q = _qs([_server(1), _server(2)], count=9)
        with patch.object(
            KuaiaiMcpServer, "filter", MagicMock(return_value=q)
        ) as mock_filter:
            out = await McpService.list_servers(TENANT, page=2, page_size=2)
        assert set(out.keys()) == {"items", "total"}
        assert out["total"] == 9
        assert len(out["items"]) == 2
        assert mock_filter.call_args.kwargs["tenant_id"] == TENANT
        assert mock_filter.call_args.kwargs["deleted_at__isnull"] is True
        q.offset.assert_called_with(2)
        q.limit.assert_called_with(2)

    @pytest.mark.asyncio
    async def test_list_options_only_enabled(self):
        rows = [_server(1), _server(2, code="mcp-wms")]
        q = _qs(rows)
        with patch.object(
            KuaiaiMcpServer, "filter", MagicMock(return_value=q)
        ) as mock_filter:
            options = await McpService.list_options(TENANT)
        assert mock_filter.call_args.kwargs["status"] == "启用"
        assert mock_filter.call_args.kwargs["tenant_id"] == TENANT
        assert [o["id"] for o in options] == [1, 2]
        for opt in options:
            assert set(opt.keys()) == {"id", "name", "code"}
            assert "tenant_id" not in opt
            assert "token" not in opt
            assert "endpoint" not in opt


# ------------------------------------------------------- token 打码/写路径


class TestTokenMasking:
    def test_server_out_masks_token(self):
        out = McpService.server_out(_server(token="real-secret-token"))
        assert out["token"] == "****"
        assert out["token_configured"] is True
        assert "real-secret-token" not in repr(out)

    def test_server_out_no_token(self):
        out = McpService.server_out(_server(token=None))
        assert out["token"] is None
        assert out["token_configured"] is False

    def test_out_schema_has_no_tenant_id_or_plaintext(self):
        out = McpServerOut.model_validate(
            McpService.server_out(_server(token="real-secret-token"))
        )
        dumped = out.model_dump()
        assert "tenant_id" not in dumped
        assert dumped["token"] == "****"
        assert dumped["token_configured"] is True

    @pytest.mark.asyncio
    async def test_update_masked_placeholder_keeps_original(self):
        """打码占位 "****"/"********"/空白 → 不写库，保留原 token。"""
        for placeholder in ("****", "********", "   "):
            server = _server(token="real-secret-token")
            with patch.object(
                KuaiaiMcpServer, "get_or_none", new=AsyncMock(return_value=server)
            ):
                await McpService.update_server(
                    TENANT, _user(), 1, McpServerUpdate(token=placeholder)
                )
            data = server.update_from_dict.call_args.args[0]
            assert "token" not in data
            assert server.token == "real-secret-token"

    @pytest.mark.asyncio
    async def test_update_token_null_clears(self):
        """显式 null = 清空 token。"""
        server = _server(token="real-secret-token")
        with patch.object(
            KuaiaiMcpServer, "get_or_none", new=AsyncMock(return_value=server)
        ):
            await McpService.update_server(
                TENANT, _user(), 1, McpServerUpdate(token=None)
            )
        data = server.update_from_dict.call_args.args[0]
        assert data["token"] is None
        assert server.token is None

    @pytest.mark.asyncio
    async def test_update_token_new_value(self):
        server = _server(token=None)
        with patch.object(
            KuaiaiMcpServer, "get_or_none", new=AsyncMock(return_value=server)
        ):
            await McpService.update_server(
                TENANT, _user(), 1, McpServerUpdate(token="  new-token  ")
            )
        assert server.token == "new-token"  # strip 后写库

    @pytest.mark.asyncio
    async def test_create_masked_token_stored_as_none(self):
        """create 传打码占位不落库（视同未配置）。"""
        created = {}

        async def _create(**kw):
            created.update(kw)
            return _server()

        with (
            patch.object(
                KuaiaiMcpServer, "get_or_none", new=AsyncMock(return_value=None)
            ),
            patch.object(
                KuaiaiMcpServer, "create", new=AsyncMock(side_effect=_create)
            ),
        ):
            await McpService.create_server(
                TENANT, _user(), McpServerCreate(**{**_VALID_PAYLOAD, "token": "****"})
            )
        assert created["token"] is None


# --------------------------------------------------------- 守卫（保存路径）


class TestGuardOnSavePath:
    @pytest.mark.asyncio
    async def test_non_http_transport_400(self):
        for bad in ("stdio", "sse", "websocket"):
            with pytest.raises(BusinessLogicError) as exc:
                await McpService.create_server(
                    TENANT,
                    _user(),
                    McpServerCreate(**{**_VALID_PAYLOAD, "transport": bad}),
                )
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_illegal_endpoints_400(self):
        for bad in (
            "http://localhost/mcp",
            "http://a.localhost/mcp",
            "http://metadata.google.internal/",
            "http://user:pass@mcp.example.com/mcp",
            "ftp://mcp.example.com/mcp",
            "mcp.example.com/mcp",
            "http://mcp.example.com:99999/mcp",  # 非法端口归一 400（m1）
            "   ",
        ):
            with pytest.raises(BusinessLogicError) as exc:
                await McpService.create_server(
                    TENANT,
                    _user(),
                    McpServerCreate(**{**_VALID_PAYLOAD, "endpoint": bad}),
                )
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_endpoint_resolving_to_forbidden_ip_400(self):
        """公网域名解析到云元数据/回环地址 → 400（DNS rebinding 防线）。"""
        def _resolve(host, port, *args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port or 80))
            ]

        with patch("socket.getaddrinfo", side_effect=_resolve):
            with pytest.raises(BusinessLogicError):
                await McpService.create_server(
                    TENANT, _user(), McpServerCreate(**_VALID_PAYLOAD)
                )

    @pytest.mark.asyncio
    async def test_empty_allowed_tools_400(self):
        for bad in ("   ", ",,,"):
            with pytest.raises(BusinessLogicError) as exc:
                await McpService.create_server(
                    TENANT,
                    _user(),
                    McpServerCreate(**{**_VALID_PAYLOAD, "allowed_tools": bad}),
                )
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_sql_tool_name_400(self):
        for bad in (
            "execute_sql",
            "search_knowledge,sql_query",
            "custom_query",
            "execute  sql",  # 双空格绕过（m3）
            "executeSql",  # CamelCase 绕过（m3）
        ):
            with pytest.raises(BusinessLogicError) as exc:
                await McpService.create_server(
                    TENANT,
                    _user(),
                    McpServerCreate(**{**_VALID_PAYLOAD, "allowed_tools": bad}),
                )
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_update_endpoint_guard_400(self):
        server = _server()
        with patch.object(
            KuaiaiMcpServer, "get_or_none", new=AsyncMock(return_value=server)
        ):
            with pytest.raises(BusinessLogicError):
                await McpService.update_server(
                    TENANT,
                    _user(),
                    1,
                    McpServerUpdate(endpoint="http://localhost/mcp"),
                )
        server.update_from_dict.assert_not_called()

    @pytest.mark.asyncio
    async def test_validation_fails_before_db_write(self):
        """纯字段校验失败先于重名查询/写入（KR-I3）。"""
        with (
            patch.object(
                KuaiaiMcpServer, "get_or_none", new=AsyncMock()
            ) as mock_get,
            patch.object(KuaiaiMcpServer, "create", new=AsyncMock()) as mock_create,
        ):
            with pytest.raises(BusinessLogicError):
                await McpService.create_server(
                    TENANT,
                    _user(),
                    McpServerCreate(**{**_VALID_PAYLOAD, "transport": "stdio"}),
                )
        mock_get.assert_not_called()
        mock_create.assert_not_called()


# ------------------------------------------------------- 路由注册与权限码

_EXPECTED_MCP_ROUTES = {
    ("GET", "/mcp-servers"): {"kuaiai:mcp:list"},
    ("POST", "/mcp-servers"): {"kuaiai:mcp:add"},
    ("GET", "/mcp-servers/options"): {"kuaiai:mcp:query"},
    ("GET", "/mcp-servers/{server_id}"): {"kuaiai:mcp:query"},
    ("PUT", "/mcp-servers/{server_id}"): {"kuaiai:mcp:edit"},
    ("DELETE", "/mcp-servers/{server_id}"): {"kuaiai:mcp:remove"},
}


def _required_permissions(route: APIRoute):
    """从 require_access 依赖闭包中取出 required_permissions。"""
    perms = set()
    for dep in route.dependencies or []:
        fn = getattr(dep, "dependency", None)
        closure = getattr(fn, "__closure__", None)
        if fn is None or closure is None:
            continue
        for name, cell in zip(fn.__code__.co_freevars, closure):
            if name == "required_permissions":
                perms.update(cell.cell_contents or [])
    return perms


class TestMcpRouteRegistration:
    """六条 S4 路由：路径/方法/权限码（契约 mcp:{list|query|add|edit|remove}）。"""

    def test_all_s4_routes_registered_with_permission_codes(self):
        table = {}
        for r in router.routes:
            if not isinstance(r, APIRoute):
                continue
            for method in r.methods:
                table[(method, r.path)] = _required_permissions(r)
        for key, perms in _EXPECTED_MCP_ROUTES.items():
            assert key in table, f"路由未注册: {key}"
            assert table[key] == perms, f"{key} 权限码不符: {table[key]}"

    def test_options_registered_before_server_id(self):
        """/mcp-servers/options 必须先于 /mcp-servers/{server_id} 注册。"""
        get_paths = [
            r.path
            for r in router.routes
            if isinstance(r, APIRoute) and "GET" in r.methods
        ]
        assert get_paths.index("/mcp-servers/options") < get_paths.index(
            "/mcp-servers/{server_id}"
        )
