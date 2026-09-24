"""KU-AI S4 MCP 运行面：白名单行建连 + 工具装配（KR-D11，契约 D 钉版
langchain-mcp-adapters==0.3.2）。

0.3.2 实测 API 形态（以安装包为准）：

- ``MultiServerMCPClient(connections, *, tool_interceptors=[...])``：
  connections 为 ``{server_name: {"transport": "streamable_http",
  "url": ..., "headers": {...}}}``；``await client.get_tools()`` 返回
  ``list[BaseTool]``（工具执行时按需新建 session，非长连接）；
- interceptor 为 client 级：``async def __call__(request, handler)``，
  ``request`` 是 ``MCPToolCallRequest``（name/args/server_name/headers），
  ``handler(request)`` 执行真实调用；返回 ``CallToolResult | ToolMessage``；
- 错误回 ``CallToolResult(isError=True)``：走 adapters
  ``handle_tool_errors`` 语义转成 ``ToolMessage(status="error")``——
  tool_call_id 由外层 StructuredTool 回写；裸返回 ToolMessage 会带
  占位 id 穿过 ``_format_output``，与 tool_call 失联。

- ``load_agent_mcp_tools``：档案 ``mcp_server_ids`` → 本租户 ``启用`` 未删
  白名单行；跨租户/停用/已删/不存在的 id 静默过滤（对齐 S3 knowledge_ids
  陈旧 id 惯例）；逐行建连，单 server 建连/加载失败仅 warning 跳过
  （对齐 ktg-ai ``failIfOneServerFails(false)``），不拖垮整次发送。
- 工具过滤：load 后按行 ``allowed_tools`` CSV 过滤
  （``is_tool_allowed``：SQL 黑名单 + 空名单失败关闭）；另丢弃撞
  ``ENABLED_TOOL_NAMES`` 注册表闭集名的工具（组合守卫按名放行会绕过
  core RBAC）与本批已加载同名工具（``tools + mcp_tools`` 同名时
  ToolNode 后者覆盖前者，跨 server 先到先得，防调用静默改道）。
  per-server interceptor 在调用时复核同名规则 + 每次调用前
  ``asyncio.to_thread(require_safe_http_url)`` 复核 endpoint（SSRF
  TOCTOU 收敛：adapters 每次调用新建 session 重新 DNS 解析，装配期
  校验无法覆盖 rebind；URL 级守卫仍钉不死连接期实际 IP，残余限制见
  ``_build_mcp_guard_interceptor``）。0.3.2 的
  ``MCPToolCallRequest.server_name`` 可用，但按行建 client 后同名工具
  天然绑定本行连接+本行白名单闭包——同名冲突时各按所属 server 白名单
  校验（非并集），无 name→server 错配面。
- ``build_mcp_aware_tool_guard``：MCP 工具不在 ToolRegistry，core
  ``build_tool_guard_middleware`` 会判 403——组合守卫对 MCP 名集合放行
  （调用侧权限/审计/超时已由 interceptor 承担），其余名回 core guard；
  空集合直接返回 core guard 不包装。
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, List, Optional, Set, Tuple

from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from loguru import logger
from mcp.types import CallToolResult, TextContent

from apps.kuaiai.constants import (
    ENABLED_TOOL_NAMES,
    MCP_TOOL_TIMEOUT_SECONDS,
    STATUS_ENABLED,
)
from apps.kuaiai.models.mcp import KuaiaiMcpServer
from apps.kuaiai.services.mcp_guard import (
    is_tool_allowed,
    require_http_transport,
    require_safe_http_url,
)
from core.ai.runtime.context import AiRuntimeContext, get_ai_context
from core.ai.runtime.tool_bridge import build_tool_guard_middleware


def _context_ok(ctx: Optional[AiRuntimeContext]) -> bool:
    return (
        ctx is not None
        and bool(ctx.tenant_id)
        and getattr(ctx.user, "id", None) is not None
    )


def _error_result(text: str) -> CallToolResult:
    """MCP 调用错误结果：``isError=True`` 经 adapters ``handle_tool_errors``
    转 ``ToolMessage(status="error")``，不抛穿（模型可改口重试）。"""
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        isError=True,
    )


async def _audit_mcp_call(
    *,
    ctx: AiRuntimeContext,
    tool_name: str,
    latency_ms: int,
    status_code: int,
    error: Optional[str] = None,
) -> None:
    """MCP tool 级审计（KR-D17 同口径）：route=ai/mcp/<tool>；
    error 只记异常类型名/固定标记，不落参数值与 token。

    tool_name 是模型/远程 server 可控字符串，写入前剥离控制字符
    （防审计字段注入），总长仍按 256 截断。"""
    try:
        from core.models.ai_audit_log import AiAuditLog

        safe_name = re.sub(r"[\x00-\x1f\x7f]", "", tool_name)
        await AiAuditLog.create(
            tenant_id=ctx.tenant_id,
            user_id=getattr(ctx.user, "id", None),
            route=f"ai/mcp/{safe_name}"[:256],
            capability="tool_call",
            latency_ms=latency_ms,
            status_code=status_code,
            error_message=error,
        )
    except Exception as exc:
        logger.warning(
            "MCP tool 审计写入失败 tool={} error_type={}",
            tool_name,
            type(exc).__name__,
        )


def _build_mcp_guard_interceptor(
    allowed_tools: str, server_code: str, endpoint: str
):
    """按 server 行 ``allowed_tools`` + ``endpoint`` 闭包构造调用侧守卫
    interceptor。

    职责（KR-D11/AC3/AC5）：上下文失败关闭 → 白名单/SQL 黑名单复核（403）
    → endpoint 每次调用复核（SSRF TOCTOU 收敛，403）→
    ``asyncio.wait_for`` 超时 → ``AiAuditLog`` 审计；错误一律回
    ``CallToolResult(isError=True)`` 而非抛穿。

    残余限制：URL 级守卫只能保证每次调用前 host 的当前解析结果合法，
    无法钉死连接期实际解析到的 IP（校验与 adapters 建连两次解析之间
    host 仍可能 rebind）；彻底解法需自定义 resolver / 连接层 IP 钉住，
    超出本层范围。
    """

    async def _intercept(request: Any, handler: Any):
        tool_name = str(getattr(request, "name", "") or "")
        started = time.perf_counter()

        def _elapsed_ms() -> int:
            return int((time.perf_counter() - started) * 1000)

        # ① 空租户/用户上下文 → 失败关闭（无 ctx 无从审计，但日志留痕）
        ctx = get_ai_context()
        if not _context_ok(ctx):
            logger.warning(
                "MCP tool 缺少上下文拒绝: tool={} server={}",
                tool_name,
                server_code,
            )
            return _error_result("AI 工具缺少租户/用户上下文")

        # ② 非本 server 白名单 / SQL 黑名单名 → 403 拒绝
        if not is_tool_allowed(allowed_tools, tool_name):
            await _audit_mcp_call(
                ctx=ctx,
                tool_name=tool_name,
                latency_ms=_elapsed_ms(),
                status_code=403,
                error="tool_not_allowed",
            )
            return _error_result("无权限调用该工具")

        # ③ endpoint 复核（SSRF TOCTOU 收敛）：adapters 每次调用新建
        # session 重新 DNS 解析，装配期校验无法覆盖 rebind——每次调用前
        # 重校验（同步 DNS，to_thread 离 loop；30s 超时预算内多一次 DNS
        # RTT 可接受）。校验失败按 403 拒绝 + 审计。
        try:
            await asyncio.to_thread(require_safe_http_url, endpoint)
        except Exception:
            await _audit_mcp_call(
                ctx=ctx,
                tool_name=tool_name,
                latency_ms=_elapsed_ms(),
                status_code=403,
                error="endpoint_unsafe",
            )
            logger.warning(
                "MCP tool 端点复核失败拒绝 server={} tool={}",
                server_code,
                tool_name,
            )
            return _error_result("无权限调用该工具")

        # ④ 超时 + 异常收敛：超时/异常一律 500 审计 + 错误结果，不抛穿
        try:
            result = await asyncio.wait_for(
                handler(request), MCP_TOOL_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            await _audit_mcp_call(
                ctx=ctx,
                tool_name=tool_name,
                latency_ms=_elapsed_ms(),
                status_code=500,
                error="TimeoutError",
            )
            logger.warning(
                "MCP tool 调用超时 server={} tool={}", server_code, tool_name
            )
            return _error_result(f"MCP 工具 {tool_name} 调用超时")
        except Exception as exc:
            await _audit_mcp_call(
                ctx=ctx,
                tool_name=tool_name,
                latency_ms=_elapsed_ms(),
                status_code=500,
                error=type(exc).__name__,
            )
            logger.warning(
                "MCP tool 调用异常 server={} tool={} error_type={}",
                server_code,
                tool_name,
                type(exc).__name__,
            )
            return _error_result(f"MCP 工具 {tool_name} 执行失败")

        # ⑤ 成功 200；handler 返回错误结果（isError / error ToolMessage）记 400
        status_code = 200
        error = None
        if isinstance(result, CallToolResult) and result.isError:
            status_code, error = 400, "tool_error"
        elif isinstance(result, ToolMessage) and result.status == "error":
            status_code, error = 400, "tool_error"
        await _audit_mcp_call(
            ctx=ctx,
            tool_name=tool_name,
            latency_ms=_elapsed_ms(),
            status_code=status_code,
            error=error,
        )
        return result

    return _intercept


def _server_connection(row: KuaiaiMcpServer, endpoint: str) -> dict:
    """行 → adapters ``streamable_http`` connection；token 非空 → Bearer 头。"""
    connection: dict = {"transport": "streamable_http", "url": endpoint}
    token = row.decrypt_token()
    if token:
        connection["headers"] = {"Authorization": f"Bearer {token}"}
    return connection


async def load_agent_mcp_tools(
    tenant_id: int, server_ids: List[int]
) -> Tuple[List[Any], Set[str]]:
    """档案 ``mcp_server_ids`` → (langchain tools, 工具名集合)。

    行解析失败关闭在本租户启用白名单内（``tenant_id + status=启用 +
    未删除``）；未解析出的 id 静默过滤。单 server 建连/加载失败仅
    warning 跳过。load 后按行 ``allowed_tools`` CSV 过滤工具。
    """
    tools: List[Any] = []
    names: Set[str] = set()
    if not server_ids:
        return tools, names

    rows = await KuaiaiMcpServer.filter(
        tenant_id=tenant_id,
        id__in=list(server_ids),
        status=STATUS_ENABLED,
        deleted_at__isnull=True,
    )
    for row in rows:
        try:
            require_http_transport(row.transport)
            # require_safe_http_url 为同步 DNS 校验，to_thread 离 loop；
            # 建连侧复核（保存时已校验，此处防存量脏数据/解析漂移）
            endpoint = await asyncio.to_thread(
                require_safe_http_url, row.endpoint
            )
            client = MultiServerMCPClient(
                {str(row.code): _server_connection(row, endpoint)},
                tool_interceptors=[
                    _build_mcp_guard_interceptor(
                        row.allowed_tools, str(row.code), endpoint
                    )
                ],
            )
            server_tools = await client.get_tools()
        except Exception as exc:
            logger.warning(
                "MCP server 建连/加载失败，跳过 server_id={} code={} "
                "error_type={}",
                row.id,
                row.code,
                type(exc).__name__,
            )
            continue
        for tool in server_tools:
            tool_name = str(getattr(tool, "name", "") or "")
            if not is_tool_allowed(row.allowed_tools, tool_name):
                logger.warning(
                    "MCP 工具不在白名单，丢弃 server_id={} tool={}",
                    row.id,
                    tool_name,
                )
                continue
            # 撞名丢弃：撞 ENABLED_TOOL_NAMES 闭集名会被组合守卫按名
            # 放行绕过 core RBAC；撞本批已加载名时 ToolNode 同名后者
            # 覆盖前者，调用静默打到后加载的 MCP server——先到先得。
            if tool_name in ENABLED_TOOL_NAMES or tool_name in names:
                logger.warning(
                    "MCP 工具名冲突，丢弃 server_id={} code={} tool={}",
                    row.id,
                    row.code,
                    tool_name,
                )
                continue
            tools.append(tool)
            names.add(tool_name)
    return tools, names


def build_mcp_aware_tool_guard(mcp_names: Set[str]):
    """组合工具守卫：MCP 名集合放行，其余名走 core RBAC/审计守卫。

    MCP 工具不在 ToolRegistry，``build_tool_guard_middleware`` 对未注册名
    一律 403——MCP 名必须在外层放行，其权限/审计/超时由连接级
    interceptor 承担。``mcp_names`` 为空时直接返回 core guard 不包装。
    """
    core_guard = build_tool_guard_middleware()
    if not mcp_names:
        return core_guard

    @wrap_tool_call
    async def _mcp_aware_guard(request, handler):
        tool_call = request.tool_call or {}
        tool_name = str(tool_call.get("name") or "")
        if tool_name in mcp_names:
            return await handler(request)
        return await core_guard.awrap_tool_call(request, handler)

    return _mcp_aware_guard
