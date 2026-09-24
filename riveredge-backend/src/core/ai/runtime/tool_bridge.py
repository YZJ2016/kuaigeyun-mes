"""ToolRegistry → LangChain tool 桥接 + ``wrap_tool_call`` RBAC/审计（KR-D10/D17）。

- ``registry_to_lc_tools``：把注册表的 OpenAI function definition 包成
  LangChain ``StructuredTool``；tool 体内经 ``get_ai_context()`` 取
  tenant/user（失败关闭），再调 ``ToolRegistry`` handler（manifest
  ``ai_tools`` 声明的 ``module:attr``）。handler 缺失/异常一律回
  ``ToolMessage(status="error")``，不抛穿——让模型改口而不是 500。
- ``build_tool_guard_middleware``：``wrap_tool_call`` 中按
  ``RegisteredTool.permission`` 对当前上下文用户做 RBAC，无权限回
  ``ToolMessage(status="error")``；计时并写 ``core_ai_audit_logs``
  （不落 Key/敏感参数，KR-I5）。

handler 约定：``async def handler(**args) -> str``；若其签名声明 ``ctx``
或 ``context`` 形参，桥接层会补传 ``AiRuntimeContext``（handler 内亦可
自行 ``get_ai_context()``，contextvars 在同一调用栈内可见）。
"""

from __future__ import annotations

import inspect
import time
from typing import Any, List, Optional

from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool
from loguru import logger

from core.ai.runtime.context import AiRuntimeContext, get_ai_context
from core.ai.tool_registry import RegisteredTool, ToolRegistry
from core.services.authorization.user_permission_service import (
    UserPermissionService,
)


def _registered_tool(name: str) -> Optional[RegisteredTool]:
    """取注册条目（含 permission）。ToolRegistry 无公开条目访问器，
    读包内 ``_tools`` 表（不改 tool_registry.py）。"""
    ToolRegistry.ensure_defaults()
    return ToolRegistry._tools.get(name)


def _context_ok(ctx: Optional[AiRuntimeContext]) -> bool:
    return (
        ctx is not None
        and bool(ctx.tenant_id)
        and getattr(ctx.user, "id", None) is not None
    )


def _error_message(tool_name: str, text: str, tool_call_id: str = "") -> ToolMessage:
    # tool_call_id/name 由 agent ToolNode 按调用回写；占位值仅满足 schema 必填。
    return ToolMessage(
        content=text,
        tool_call_id=tool_call_id,
        name=tool_name or None,
        status="error",
    )


def _make_lc_tool(registered: RegisteredTool) -> StructuredTool:
    fn = (registered.definition or {}).get("function") or {}
    tool_name = str(fn.get("name") or registered.name)
    description = str(fn.get("description") or tool_name)
    parameters = fn.get("parameters") or {"type": "object", "properties": {}}

    async def _invoke(**kwargs: Any) -> Any:
        ctx = get_ai_context()
        if not _context_ok(ctx):
            return _error_message(tool_name, "AI 工具缺少租户/用户上下文")
        handler = registered.handler or ToolRegistry.get_handler(tool_name)
        if handler is None:
            return _error_message(tool_name, f"工具 {tool_name} 未注册处理器")
        call_kwargs = dict(kwargs)
        try:
            params = inspect.signature(handler).parameters
            if "ctx" in params:
                call_kwargs["ctx"] = ctx
            elif "context" in params:
                call_kwargs["context"] = ctx
        except (TypeError, ValueError):
            pass
        try:
            result = handler(**call_kwargs)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            # KR-I5：不落参数值；异常细节只记类型
            logger.warning(
                "AI tool 执行异常 tool={} error_type={}",
                tool_name,
                type(exc).__name__,
            )
            return _error_message(tool_name, f"工具 {tool_name} 执行失败")
        if isinstance(result, (str, ToolMessage)):
            return result
        return str(result)

    return StructuredTool.from_function(
        coroutine=_invoke,
        name=tool_name,
        description=description,
        args_schema=parameters,
    )


def registry_to_lc_tools(names: List[str]) -> List[StructuredTool]:
    """按名取注册表 definition → LangChain tools；未注册名跳过并告警。"""
    ToolRegistry.ensure_defaults()
    tools: List[StructuredTool] = []
    for name in names or []:
        registered = ToolRegistry._tools.get(str(name))
        if registered is None:
            logger.warning("AI tool 未注册，跳过装配: {}", name)
            continue
        tools.append(_make_lc_tool(registered))
    return tools


def _business_ref(tool_args: Any) -> Optional[str]:
    """取工具入参中第一个 id 类业务键（如 work_order_id/record_id）。

    ``core_ai_audit_logs`` 无 detail/meta JSON 列（不加列），业务键拼进
    既有 ``route`` 文本字段便于按单据检索；只取标量值，不落复杂参数。
    """
    if not isinstance(tool_args, dict):
        return None
    for key, value in tool_args.items():
        name = str(key)
        if name != "id" and not name.endswith("_id"):
            continue
        if value is None or isinstance(value, (dict, list)):
            continue
        return f"{name}={value}"
    return None


async def _audit_tool_call(
    *,
    ctx: AiRuntimeContext,
    tool_name: str,
    latency_ms: int,
    status_code: int,
    tool_args: Any = None,
    error: Optional[str] = None,
) -> None:
    """Tool 级审计（KR-D17）：user/tenant/toolName/latency；不落 Key/敏感参数。"""
    try:
        from core.models.ai_audit_log import AiAuditLog

        route = f"ai/tool/{tool_name}"
        ref = _business_ref(tool_args)
        if ref:
            route = f"{route}?{ref}"[:256]
        await AiAuditLog.create(
            tenant_id=ctx.tenant_id,
            user_id=getattr(ctx.user, "id", None),
            route=route,
            capability="tool_call",
            latency_ms=latency_ms,
            status_code=status_code,
            error_message=error,
        )
    except Exception as exc:
        logger.warning(
            "AI tool 审计写入失败 tool={} error_type={}",
            tool_name,
            type(exc).__name__,
        )


def build_tool_guard_middleware():
    """``wrap_tool_call``：RBAC + 计时 + core_ai_audit_logs 审计。"""

    @wrap_tool_call
    async def _tool_guard(request, handler):
        tool_call = request.tool_call or {}
        tool_name = str(tool_call.get("name") or "")
        tool_call_id = str(tool_call.get("id") or "")
        started = time.perf_counter()

        ctx = get_ai_context()
        if not _context_ok(ctx):
            return _error_message(
                tool_name, "AI 工具缺少租户/用户上下文", tool_call_id
            )

        registered = _registered_tool(tool_name)
        permission = getattr(registered, "permission", None) if registered else None
        if registered is None or not permission:
            # 失败关闭：未注册或无权限码的工具一律拒绝，fail-open 即越权面
            await _audit_tool_call(
                ctx=ctx,
                tool_name=tool_name,
                latency_ms=int((time.perf_counter() - started) * 1000),
                status_code=403,
                tool_args=tool_call.get("args"),
                error="tool_unregistered" if registered is None else "permission_missing",
            )
            return _error_message(
                tool_name, "无权限调用该工具", tool_call_id
            )

        allowed = bool(ctx.is_infra_admin or ctx.is_tenant_admin)
        if not allowed:
            allowed = await UserPermissionService.has_permission(
                getattr(ctx.user, "id", 0),
                ctx.tenant_id,
                permission,
            )
        if not allowed:
            await _audit_tool_call(
                ctx=ctx,
                tool_name=tool_name,
                latency_ms=int((time.perf_counter() - started) * 1000),
                status_code=403,
                tool_args=tool_call.get("args"),
                error="permission_denied",
            )
            return _error_message(
                tool_name, "无权限调用该工具", tool_call_id
            )

        try:
            result = await handler(request)
        except Exception as exc:
            # 系统异常 → 500
            await _audit_tool_call(
                ctx=ctx,
                tool_name=tool_name,
                latency_ms=int((time.perf_counter() - started) * 1000),
                status_code=500,
                tool_args=tool_call.get("args"),
                error=type(exc).__name__,
            )
            logger.warning(
                "AI tool handler 抛穿 tool={} error_type={}",
                tool_name,
                type(exc).__name__,
            )
            return _error_message(
                tool_name, f"工具 {tool_name} 执行失败", tool_call_id
            )

        status_code = 200
        error = None
        if isinstance(result, ToolMessage) and result.status == "error":
            # 业务错误（工具返回 error ToolMessage 但执行未异常）→ 4xx 语义
            status_code = 400
            error = "tool_error"
        await _audit_tool_call(
            ctx=ctx,
            tool_name=tool_name,
            latency_ms=int((time.perf_counter() - started) * 1000),
            status_code=status_code,
            tool_args=tool_call.get("args"),
            error=error,
        )
        return result

    return _tool_guard
