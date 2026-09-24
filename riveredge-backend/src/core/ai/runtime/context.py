"""AI 运行时上下文（contextvars DI 透传，设计 §6.3）。

Tool 执行与审计在 agent 调用栈内通过 ``get_ai_context()`` 取当前
tenant/user，不走函数参数层层透传；空上下文返回 ``None``，调用方失败
关闭（KR-I1–I3）。

KR-I6：taskiq job / ``astream`` 后台任务等异步辅助，必须显式拷贝上下文::

    ctx = get_ai_context()           # 父上下文快照
    async def job():
        set_ai_context(ctx)          # 后台任务内重建
        ...
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class AiRuntimeContext:
    """单次 AI 调用的身份上下文。"""

    tenant_id: int
    user: Any
    is_infra_admin: bool = False
    is_tenant_admin: bool = False
    session_id: Optional[str] = None
    agent_id: Optional[int] = None


_ai_context: ContextVar[Optional[AiRuntimeContext]] = ContextVar(
    "core_ai_runtime_context", default=None
)


def set_ai_context(ctx: AiRuntimeContext) -> Token:
    """写入当前 contextvar；返回 Token 供 ``reset_ai_context``。"""
    return _ai_context.set(ctx)


def get_ai_context() -> Optional[AiRuntimeContext]:
    """取当前上下文；未设置返回 ``None``（调用方失败关闭）。"""
    return _ai_context.get()


def reset_ai_context(token: Token) -> None:
    """按 Token 复位（请求结束 / 后台任务清理用）。"""
    _ai_context.reset(token)
