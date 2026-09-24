"""KU-AI S4 单测：MCP 运行面（建连 + 工具装配 + 调用侧守卫）。

全部 mock ORM / MultiServerMCPClient / DNS 校验 / 审计写入，不需要真实
端点与数据库。覆盖：
- 行解析：仅本租户启用白名单子集（停用/跨租户/已删 id 静默过滤）
- connection：http→streamable_http、endpoint→url、token→Bearer 头
- 工具过滤：allowed_tools CSV + SQL 黑名单名剔除 + 撞注册表闭集名/
  跨 server 同名丢弃
- interceptor：空 ctx 失败关闭 / 非白名单名 403 / SQL 名 403 /
  endpoint 调用期复核 403 / 超时与异常 500 / 审计字段
  （route=ai/mcp/<tool> 控制字符清洗、不落参数）
- 组合守卫：MCP 名放行直连 handler，闭集名走 core guard
- assembler 并入：profile.mcp_server_ids → tools 增长 + 组合守卫装配；
  load 外层异常降级按无 MCP 工具继续
- 单 server 建连失败跳过不炸整次装配
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import ToolMessage
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from mcp.types import CallToolResult, TextContent

import apps.kuaiai.services.agent_assembler as agent_assembler
import apps.kuaiai.services.mcp_client_service as mcs
from apps.kuaiai.models.agent import KuaiaiAgentProfile
from core.ai.runtime.context import (
    AiRuntimeContext,
    reset_ai_context,
    set_ai_context,
)
from core.models.ai_audit_log import AiAuditLog

TENANT = 7
USER_ID = 5
AGENT_ID = 3


class _QS:
    """Tortoise ``Model.filter(...)`` 返回值的替身：可直接 await → list。"""

    def __init__(self, rows):
        self._rows = list(rows)

    def __await__(self):
        async def _go():
            return self._rows

        return _go().__await__()


def _user(uid=USER_ID):
    return SimpleNamespace(id=uid, full_name="测试", username="tester")


def _ctx(uid=USER_ID):
    return AiRuntimeContext(tenant_id=TENANT, user=_user(uid))


def _server_row(**over):
    """KuaiaiMcpServer 行替身（SimpleNamespace + decrypt_token 钩子）。"""
    base = dict(
        id=11,
        tenant_id=TENANT,
        code="srv-a",
        name="服务器A",
        transport="http",
        endpoint="https://mcp-a.example.com/mcp",
        token=None,
        allowed_tools="tool_a,tool_b",
        status="启用",
        deleted_at=None,
    )
    base.update(over)
    row = SimpleNamespace(**base)
    token = base["token"]
    row.decrypt_token = lambda: (token or "").strip()
    return row


def _lc_tool(name):
    return SimpleNamespace(name=name)


def _ok_result(text="ok"):
    return CallToolResult(
        content=[TextContent(type="text", text=text)], isError=False
    )


def _mcp_request(name="tool_a", args=None, server_name="srv-a"):
    return MCPToolCallRequest(
        name=name, args=args or {}, server_name=server_name
    )


def _patch_servers(rows):
    """patch KuaiaiMcpServer.filter → 固定行集（调用方断言行解析 kwargs）。"""
    return patch.object(
        mcs.KuaiaiMcpServer,
        "filter",
        MagicMock(return_value=_QS(rows)),
    )


def _patch_url_check():
    """require_safe_http_url 为同步 DNS 校验——mock 成直通，避免真实 DNS。"""
    return patch.object(
        mcs, "require_safe_http_url", MagicMock(side_effect=lambda u: u)
    )


def _client_cls(get_tools_map=None, default_tools=None):
    """MultiServerMCPClient 类替身工厂。

    get_tools_map: {server_code: tools-or-exception}，按 connections key 分派；
    default_tools: 无 map 时统一返回。
    """
    cls = MagicMock(name="MultiServerMCPClient")

    def _ctor(connections, **kwargs):
        inst = MagicMock(name="MCPClient-inst")
        code = next(iter(connections))
        spec = (get_tools_map or {}).get(code)
        if isinstance(spec, BaseException):
            inst.get_tools = AsyncMock(side_effect=spec)
        elif spec is not None:
            inst.get_tools = AsyncMock(return_value=spec)
        else:
            inst.get_tools = AsyncMock(return_value=default_tools or [])
        return inst

    cls.side_effect = _ctor
    return cls


# ------------------------------------------------------------ 行解析/建连


class TestLoadAgentMcpTools:
    @pytest.mark.asyncio
    async def test_row_resolution_scoped_to_tenant_enabled(self):
        """filter 固定带 tenant/启用/未删：停用/跨租户/已删 id 由行解析
        静默过滤（依赖 DB 谓词，不逐个报错）。"""
        with (
            _patch_servers([_server_row()]) as mock_filter,
            _patch_url_check(),
            patch.object(
                mcs, "MultiServerMCPClient", _client_cls(default_tools=[])
            ),
        ):
            tools, names = await mcs.load_agent_mcp_tools(
                TENANT, [11, 22, 999]
            )
        assert tools == [] and names == set()
        mock_filter.assert_called_once_with(
            tenant_id=TENANT,
            id__in=[11, 22, 999],
            status="启用",
            deleted_at__isnull=True,
        )

    @pytest.mark.asyncio
    async def test_empty_server_ids_short_circuits(self):
        with patch.object(
            mcs.KuaiaiMcpServer, "filter", MagicMock()
        ) as mock_filter:
            tools, names = await mcs.load_agent_mcp_tools(TENANT, [])
        assert (tools, names) == ([], set())
        mock_filter.assert_not_called()

    @pytest.mark.asyncio
    async def test_connection_shape_and_bearer_header(self):
        """http→streamable_http、endpoint→url、token→Authorization Bearer。"""
        row = _server_row(token="secret-token")
        with (
            _patch_servers([row]),
            _patch_url_check(),
            patch.object(
                mcs,
                "MultiServerMCPClient",
                _client_cls(default_tools=[_lc_tool("tool_a")]),
            ) as mock_cls,
        ):
            tools, names = await mcs.load_agent_mcp_tools(TENANT, [11])
        assert names == {"tool_a"}
        conn = mock_cls.call_args.args[0]["srv-a"]
        assert conn["transport"] == "streamable_http"
        assert conn["url"] == "https://mcp-a.example.com/mcp"
        assert conn["headers"] == {
            "Authorization": "Bearer secret-token"
        }
        # interceptor 按行白名单闭包装配到 client 级
        interceptors = mock_cls.call_args.kwargs["tool_interceptors"]
        assert len(interceptors) == 1

    @pytest.mark.asyncio
    async def test_no_token_no_headers(self):
        with (
            _patch_servers([_server_row(token=None)]),
            _patch_url_check(),
            patch.object(
                mcs, "MultiServerMCPClient", _client_cls(default_tools=[])
            ) as mock_cls,
        ):
            await mcs.load_agent_mcp_tools(TENANT, [11])
        conn = mock_cls.call_args.args[0]["srv-a"]
        assert "headers" not in conn

    @pytest.mark.asyncio
    async def test_allowed_tools_filter_and_sql_names_dropped(self):
        """load 后按行 CSV 过滤：CSV 外名丢弃；SQL 黑名单名即使在 CSV 内
        也丢弃（is_tool_allowed 失败关闭）。"""
        row = _server_row(allowed_tools="tool_a,execute_sql_query")
        server_tools = [
            _lc_tool("tool_a"),
            _lc_tool("execute_sql_query"),  # CSV 内但 SQL 黑名单
            _lc_tool("not_in_csv"),  # CSV 外
        ]
        with (
            _patch_servers([row]),
            _patch_url_check(),
            patch.object(
                mcs, "MultiServerMCPClient", _client_cls(default_tools=server_tools)
            ),
        ):
            tools, names = await mcs.load_agent_mcp_tools(TENANT, [11])
        assert [t.name for t in tools] == ["tool_a"]
        assert names == {"tool_a"}

    @pytest.mark.asyncio
    async def test_single_server_failure_skipped(self):
        """单 server 建连/加载失败 → warning 跳过，不拖垮其它 server
        （对齐 ktg-ai failIfOneServerFails(false)）。"""
        rows = [
            _server_row(id=11, code="srv-a"),
            _server_row(id=12, code="srv-b"),
        ]
        cls = _client_cls(
            get_tools_map={
                "srv-a": ConnectionError("connect refused"),
                "srv-b": [_lc_tool("tool_b")],
            }
        )
        with (
            _patch_servers(rows),
            _patch_url_check(),
            patch.object(mcs, "MultiServerMCPClient", cls),
        ):
            tools, names = await mcs.load_agent_mcp_tools(TENANT, [11, 12])
        assert [t.name for t in tools] == ["tool_b"]
        assert names == {"tool_b"}

    @pytest.mark.asyncio
    async def test_illegal_endpoint_row_skipped(self):
        """endpoint 建连侧复核失败（脏数据）→ 跳过该行不炸。"""
        from infra.exceptions.exceptions import BusinessLogicError

        def _reject(_url):
            raise BusinessLogicError("出站地址非法")

        with (
            _patch_servers([_server_row(endpoint="http://169.254.169.254/x")]),
            patch.object(
                mcs, "require_safe_http_url", MagicMock(side_effect=_reject)
            ),
            patch.object(
                mcs, "MultiServerMCPClient", _client_cls(default_tools=[])
            ) as mock_cls,
        ):
            tools, names = await mcs.load_agent_mcp_tools(TENANT, [11])
        assert (tools, names) == ([], set())
        mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_registry_closed_set_name_dropped(self):
        """MCP 工具名撞 ENABLED_TOOL_NAMES 闭集名 → 丢弃（组合守卫按名
        放行会绕过 core RBAC；同名 tools + mcp_tools 后者覆盖前者）。"""
        row = _server_row(allowed_tools="query_workorder,tool_a")
        server_tools = [
            _lc_tool("query_workorder"),  # 撞注册表闭集名
            _lc_tool("tool_a"),
        ]
        with (
            _patch_servers([row]),
            _patch_url_check(),
            patch.object(
                mcs,
                "MultiServerMCPClient",
                _client_cls(default_tools=server_tools),
            ),
        ):
            tools, names = await mcs.load_agent_mcp_tools(TENANT, [11])
        assert [t.name for t in tools] == ["tool_a"]
        assert names == {"tool_a"}

    @pytest.mark.asyncio
    async def test_cross_server_duplicate_name_first_wins(self):
        """跨 server 同名工具先到先得：后者丢弃，防同名覆盖把调用静默
        改道到后加载的 server。"""
        tool_a = _lc_tool("shared_tool")
        tool_b = _lc_tool("shared_tool")
        rows = [
            _server_row(id=11, code="srv-a", allowed_tools="shared_tool"),
            _server_row(id=12, code="srv-b", allowed_tools="shared_tool"),
        ]
        cls = _client_cls(
            get_tools_map={"srv-a": [tool_a], "srv-b": [tool_b]}
        )
        with (
            _patch_servers(rows),
            _patch_url_check(),
            patch.object(mcs, "MultiServerMCPClient", cls),
        ):
            tools, names = await mcs.load_agent_mcp_tools(TENANT, [11, 12])
        assert tools == [tool_a]
        assert names == {"shared_tool"}


# ------------------------------------------------------------ interceptor


class TestMcpGuardInterceptor:
    @pytest.fixture(autouse=True)
    def _passthrough_url_check(self):
        """interceptor 每次调用复核 endpoint——mock 直通避免真实 DNS。"""
        with _patch_url_check() as mock_check:
            self.url_check_mock = mock_check
            yield

    def _interceptor(self, allowed="tool_a,tool_b"):
        return mcs._build_mcp_guard_interceptor(
            allowed, "srv-a", "https://mcp-a.example.com/mcp"
        )

    @pytest.mark.asyncio
    async def test_no_context_fails_closed(self):
        """空 ctx → 失败关闭错误结果（isError），不触 handler、无从审计，
        但日志留痕。"""
        handler = AsyncMock(return_value=_ok_result())
        with (
            patch.object(AiAuditLog, "create", new=AsyncMock()) as audit,
            patch.object(mcs, "logger", MagicMock()) as mock_logger,
        ):
            result = await self._interceptor()(
                _mcp_request("tool_a"), handler
            )
        assert isinstance(result, CallToolResult) and result.isError
        handler.assert_not_called()
        audit.assert_not_awaited()
        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_denied_tool_403_audited(self):
        """非白名单名 → 403 审计 + 错误结果，handler 不触达。"""
        token = set_ai_context(_ctx())
        try:
            handler = AsyncMock(return_value=_ok_result())
            with patch.object(
                AiAuditLog, "create", new=AsyncMock()
            ) as audit:
                result = await self._interceptor()(
                    _mcp_request("evil_tool"), handler
                )
        finally:
            reset_ai_context(token)
        assert result.isError
        handler.assert_not_called()
        audit.assert_awaited_once()
        kw = audit.await_args.kwargs
        assert kw["tenant_id"] == TENANT
        assert kw["user_id"] == USER_ID
        assert kw["route"] == "ai/mcp/evil_tool"
        assert kw["capability"] == "tool_call"
        assert kw["status_code"] == 403
        assert kw["error_message"] == "tool_not_allowed"

    @pytest.mark.asyncio
    async def test_sql_name_denied_even_if_in_csv(self):
        """SQL 黑名单名即便出现在 CSV 也被拒（复核 is_tool_allowed）。"""
        token = set_ai_context(_ctx())
        try:
            handler = AsyncMock(return_value=_ok_result())
            with patch.object(AiAuditLog, "create", new=AsyncMock()):
                result = await mcs._build_mcp_guard_interceptor(
                    "execute_sql_query",
                    "srv-a",
                    "https://mcp-a.example.com/mcp",
                )(_mcp_request("execute_sql_query"), handler)
        finally:
            reset_ai_context(token)
        assert result.isError
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_passthrough_audited_200(self):
        token = set_ai_context(_ctx())
        try:
            expected = _ok_result("done")
            handler = AsyncMock(return_value=expected)
            with patch.object(
                AiAuditLog, "create", new=AsyncMock()
            ) as audit:
                result = await self._interceptor()(
                    _mcp_request("tool_a", args={"q": "select *"}), handler
                )
        finally:
            reset_ai_context(token)
        assert result is expected
        kw = audit.await_args.kwargs
        assert kw["status_code"] == 200
        assert kw["error_message"] is None
        assert kw["route"] == "ai/mcp/tool_a"
        assert isinstance(kw["latency_ms"], int)

    @pytest.mark.asyncio
    async def test_timeout_500_error_result(self):
        """handler 超时 → 500 TimeoutError 审计 + 错误结果（不抛穿）。"""
        token = set_ai_context(_ctx())
        try:
            async def slow(_req):
                await asyncio.sleep(5)

            with (
                patch.object(mcs, "MCP_TOOL_TIMEOUT_SECONDS", 0.05),
                patch.object(
                    AiAuditLog, "create", new=AsyncMock()
                ) as audit,
            ):
                result = await self._interceptor()(
                    _mcp_request("tool_a"), slow
                )
        finally:
            reset_ai_context(token)
        assert result.isError
        kw = audit.await_args.kwargs
        assert kw["status_code"] == 500
        assert kw["error_message"] == "TimeoutError"

    @pytest.mark.asyncio
    async def test_handler_exception_500_no_leak(self):
        """handler 异常 → 500，error_message 只记异常类型名不落参数。"""
        token = set_ai_context(_ctx())
        try:
            async def boom(_req):
                raise RuntimeError("dsn=postgres://secret")

            with patch.object(
                AiAuditLog, "create", new=AsyncMock()
            ) as audit:
                result = await self._interceptor()(
                    _mcp_request("tool_a", args={"password": "p"}), boom
                )
        finally:
            reset_ai_context(token)
        assert result.isError
        kw = audit.await_args.kwargs
        assert kw["status_code"] == 500
        assert kw["error_message"] == "RuntimeError"
        # 不落参数/异常细节原文
        assert "secret" not in str(kw)
        assert "password" not in str(kw)

    @pytest.mark.asyncio
    async def test_error_call_result_audited_400(self):
        """server 回 isError → 400 tool_error（对齐 core 业务错误 4xx）。"""
        token = set_ai_context(_ctx())
        try:
            err = CallToolResult(
                content=[TextContent(type="text", text="bad")],
                isError=True,
            )
            handler = AsyncMock(return_value=err)
            with patch.object(
                AiAuditLog, "create", new=AsyncMock()
            ) as audit:
                result = await self._interceptor()(
                    _mcp_request("tool_a"), handler
                )
        finally:
            reset_ai_context(token)
        assert result is err
        assert audit.await_args.kwargs["status_code"] == 400
        assert audit.await_args.kwargs["error_message"] == "tool_error"

    @pytest.mark.asyncio
    async def test_endpoint_recheck_denied_403(self):
        """endpoint 调用期复核失败（rebind 成非法地址）→ 403 审计 +
        错误结果，handler 不触达。"""
        from infra.exceptions.exceptions import BusinessLogicError

        token = set_ai_context(_ctx())
        try:
            handler = AsyncMock(return_value=_ok_result())
            with (
                patch.object(
                    mcs,
                    "require_safe_http_url",
                    MagicMock(
                        side_effect=BusinessLogicError("出站地址非法")
                    ),
                ),
                patch.object(
                    AiAuditLog, "create", new=AsyncMock()
                ) as audit,
            ):
                result = await self._interceptor()(
                    _mcp_request("tool_a"), handler
                )
        finally:
            reset_ai_context(token)
        assert result.isError
        handler.assert_not_called()
        kw = audit.await_args.kwargs
        assert kw["status_code"] == 403
        assert kw["error_message"] == "endpoint_unsafe"
        assert kw["route"] == "ai/mcp/tool_a"

    @pytest.mark.asyncio
    async def test_endpoint_recheck_runs_per_invocation(self):
        """endpoint 复核是调用期每次执行（非仅装配期一次）。"""
        token = set_ai_context(_ctx())
        try:
            handler = AsyncMock(return_value=_ok_result())
            interceptor = self._interceptor()
            with patch.object(AiAuditLog, "create", new=AsyncMock()):
                await interceptor(_mcp_request("tool_a"), handler)
                await interceptor(_mcp_request("tool_a"), handler)
        finally:
            reset_ai_context(token)
        assert handler.await_count == 2
        assert self.url_check_mock.call_count == 2

    @pytest.mark.asyncio
    async def test_audit_route_strips_control_chars(self):
        """tool_name 含控制字符 → 审计 route 剥离后写入（防注入）。"""
        token = set_ai_context(_ctx())
        try:
            handler = AsyncMock(return_value=_ok_result())
            with patch.object(
                AiAuditLog, "create", new=AsyncMock()
            ) as audit:
                result = await self._interceptor()(
                    _mcp_request("evil\x1b\ntool"), handler
                )
        finally:
            reset_ai_context(token)
        assert result.isError
        assert audit.await_args.kwargs["route"] == "ai/mcp/eviltool"


# ------------------------------------------------------------ 组合守卫


def _mw_request(name):
    return SimpleNamespace(tool_call={"name": name, "id": "call_1"})


class TestMcpAwareToolGuard:
    @pytest.mark.asyncio
    async def test_mcp_name_passes_directly(self):
        """MCP 名 ∈ 集合 → 直连 handler（interceptor 已承担守卫）。"""
        core_guard = SimpleNamespace(
            awrap_tool_call=AsyncMock(return_value="core-result")
        )
        with patch.object(
            mcs,
            "build_tool_guard_middleware",
            MagicMock(return_value=core_guard),
        ):
            guard = mcs.build_mcp_aware_tool_guard({"mcp_tool"})
        handler = AsyncMock(return_value="mcp-result")
        result = await guard.awrap_tool_call(_mw_request("mcp_tool"), handler)
        assert result == "mcp-result"
        handler.assert_awaited_once()
        core_guard.awrap_tool_call.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_registry_name_delegates_to_core_guard(self):
        """闭集名不在 MCP 集合 → 回 core guard（RBAC/审计照旧）。"""
        core_guard = SimpleNamespace(
            awrap_tool_call=AsyncMock(return_value="core-result")
        )
        with patch.object(
            mcs,
            "build_tool_guard_middleware",
            MagicMock(return_value=core_guard),
        ):
            guard = mcs.build_mcp_aware_tool_guard({"mcp_tool"})
        handler = AsyncMock(return_value="x")
        request = _mw_request("query_workorder")
        result = await guard.awrap_tool_call(request, handler)
        assert result == "core-result"
        core_guard.awrap_tool_call.assert_awaited_once_with(
            request, handler
        )
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_names_returns_core_guard_unwrapped(self):
        core_guard = object()
        with patch.object(
            mcs,
            "build_tool_guard_middleware",
            MagicMock(return_value=core_guard),
        ):
            guard = mcs.build_mcp_aware_tool_guard(set())
        assert guard is core_guard


# ------------------------------------------------------------ assembler 并入


def _profile(**over):
    base = dict(
        id=AGENT_ID,
        tenant_id=TENANT,
        name="档案3",
        system_prompt="你是助手",
        default_model_id=42,
        enabled_tools=["query_workorder"],
        mcp_server_ids=[],
        status="启用",
        grant_mode="USER",
    )
    base.update(over)
    return SimpleNamespace(**base)


def _assemble_patches(profile, mcp_return=None):
    mocks = SimpleNamespace(
        get=AsyncMock(return_value=profile),
        grant=AsyncMock(return_value=True),
        model=AsyncMock(return_value=SimpleNamespace(model_name="m")),
        reg=MagicMock(return_value=[_lc_tool("query_workorder")]),
        mcp=AsyncMock(return_value=mcp_return or ([], set())),
        agent=MagicMock(return_value="agent-obj"),
    )
    patches = (
        patch.object(KuaiaiAgentProfile, "get_or_none", mocks.get),
        patch.object(
            agent_assembler.grant_service, "check_use_grant", mocks.grant
        ),
        patch.object(agent_assembler, "build_chat_model", mocks.model),
        patch.object(agent_assembler, "registry_to_lc_tools", mocks.reg),
        patch.object(agent_assembler, "load_agent_mcp_tools", mocks.mcp),
        patch.object(agent_assembler, "build_agent", mocks.agent),
    )
    return patches, mocks


class TestAssembleMcp:
    @pytest.mark.asyncio
    async def test_mcp_tools_merged_and_guard_composed(self):
        """profile.mcp_server_ids → load_agent_mcp_tools 并入 tools；
        middleware[0] 为组合守卫（MCP 名放行/闭集走 core）。"""
        mcp_tool = _lc_tool("mcp_weather")
        patches, mocks = _assemble_patches(
            _profile(mcp_server_ids=[11, 22]),
            mcp_return=([mcp_tool], {"mcp_weather"}),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            out = await agent_assembler.assemble(
                TENANT, _user(), False, False, AGENT_ID, agent_path=False
            )
        assert out is not None
        mocks.mcp.assert_awaited_once_with(TENANT, [11, 22])
        tools_arg = mocks.agent.call_args.args[1]
        assert [t.name for t in tools_arg] == [
            "query_workorder",
            "mcp_weather",
        ]
        guard = mocks.agent.call_args.kwargs["middleware"][0]
        # 组合守卫：MCP 名直连 handler
        handler = AsyncMock(return_value="ok")
        result = await guard.awrap_tool_call(_mw_request("mcp_weather"), handler)
        assert result == "ok"
        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_mcp_ids_skips_load(self):
        patches, mocks = _assemble_patches(_profile(mcp_server_ids=[]))
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            await agent_assembler.assemble(
                TENANT, _user(), False, False, AGENT_ID, agent_path=False
            )
        mocks.mcp.assert_not_awaited()
        tools_arg = mocks.agent.call_args.args[1]
        assert [t.name for t in tools_arg] == ["query_workorder"]

    @pytest.mark.asyncio
    async def test_empty_mcp_result_keeps_registry_tools(self):
        """load 返回空集（全部 server 失败/无白名单工具）→ 仅注册表工具
        装配，agent 正常产出。"""
        patches, mocks = _assemble_patches(
            _profile(mcp_server_ids=[11]),
            mcp_return=([], set()),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            out = await agent_assembler.assemble(
                TENANT, _user(), False, False, AGENT_ID, agent_path=False
            )
        assert out is not None
        tools_arg = mocks.agent.call_args.args[1]
        assert [t.name for t in tools_arg] == ["query_workorder"]

    @pytest.mark.asyncio
    async def test_mcp_load_exception_degrades_to_no_mcp(self):
        """load_agent_mcp_tools 外层异常（如行解析 DB 故障）→ warning
        降级按无 MCP 工具装配，不炸整次发送。"""
        patches, mocks = _assemble_patches(_profile(mcp_server_ids=[11]))
        mocks.mcp.side_effect = ConnectionError("db down")
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            out = await agent_assembler.assemble(
                TENANT, _user(), False, False, AGENT_ID, agent_path=False
            )
        assert out is not None
        tools_arg = mocks.agent.call_args.args[1]
        assert [t.name for t in tools_arg] == ["query_workorder"]
